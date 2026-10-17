#!/usr/bin/env python3
"""Finite checkpoint timer. Model continuation requires a real host completion event."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
import uuid
from task_memory import atomic_text

sys.stdout.reconfigure(encoding="utf-8")

def utc(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()

def digest(data):
    return hashlib.sha256(data).hexdigest()

def load_budget(path):
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8-sig"))
    deadline, reserve = data["deadline_epoch"], data["reserve_seconds"]
    if not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in (deadline, reserve)) or reserve <= 0:
        raise ValueError("Invalid budget deadline/reserve")
    return data, digest(raw)

def arm(record, budget, seconds):
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("Use a positive finite interval")
    record, budget = record.resolve(), budget.resolve()
    data, fingerprint = load_budget(budget)
    now = time.time()
    deliver_at = data["deadline_epoch"] - data["reserve_seconds"]
    if now >= deliver_at:
        raise ValueError("Budget is already in delivery/expired; save and deliver, do not arm")
    target = min(now + seconds, deliver_at)
    payload = {"format": "qwen-checkpoint-timer-v1", "id": uuid.uuid4().hex,
               "armed_epoch": now, "armed_utc": utc(now), "target_epoch": target,
               "target_utc": utc(target), "budget_relative_path": Path(os.path.relpath(budget, record.parent)).as_posix(),
               "budget_sha256": fingerprint, "deadline_epoch": data["deadline_epoch"],
               "reserve_seconds": data["reserve_seconds"], "host_job_id": "record the actual host launch ID separately",
               "model_wakeup": "requires host-managed completion notification; this process does not send model messages"}
    record.parent.mkdir(parents=True, exist_ok=True)
    # A new record per tick; never extend an existing tick by retrying arm.
    with record.open("x", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload

def read_record(record):
    data = json.loads(record.read_text(encoding="utf-8-sig"))
    if data["format"] != "qwen-checkpoint-timer-v1":
        raise ValueError("Unsupported timer record")
    budget, fingerprint = load_budget((record.parent / data["budget_relative_path"]).resolve())
    if fingerprint != data["budget_sha256"]:
        raise ValueError("Budget changed; do not silently reset or extend the timer")
    target = data["target_epoch"]
    if not isinstance(target, (int, float)) or not math.isfinite(target) or not data["armed_epoch"] <= target <= budget["deadline_epoch"] - budget["reserve_seconds"]:
        raise ValueError("Invalid timer target")
    return data

def sibling(record, suffix):
    return record.with_name(record.name + suffix)

def wait(record, max_seconds):
    if not math.isfinite(max_seconds) or not 0 < max_seconds <= 240:
        raise ValueError("Use a wait slice > 0 and <= 240 seconds within the actual tool timeout")
    stop = time.monotonic() + max_seconds
    while True:
        data = read_record(record)
        result = sibling(record, ".result.json")
        if result.exists():
            return json.loads(result.read_text(encoding="utf-8"))
        cancel_file = sibling(record, ".cancel")
        if cancel_file.exists():
            if cancel_file.read_text(encoding="utf-8") != data["id"]:
                raise ValueError("Cancel marker does not match timer ID")
            return {"id": data["id"], "phase": "cancelled", "rearm": False}
        now = time.time()
        if now >= data["target_epoch"]:
            payload = {"id": data["id"], "phase": "deliver" if now >= data["deadline_epoch"] - data["reserve_seconds"] else "checkpoint",
                       "observed_epoch": now, "observed_utc": utc(now), "target_utc": data["target_utc"],
                       "rearm": "main agent must inspect task/budget; never automatically",
                       "model_wakeup": "host completion event required"}
            try:
                with result.open("x", encoding="utf-8", newline="\n") as f:
                    f.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            except FileExistsError:
                return json.loads(result.read_text(encoding="utf-8"))
            return payload
        left = stop - time.monotonic()
        if left <= 0:
            return {"id": data["id"], "phase": "pending", "remaining_seconds": round(data["target_epoch"] - now, 3),
                    "action": "same watcher waits another slice on this record; do not re-arm"}
        time.sleep(min(5, left, data["target_epoch"] - now))

def cancel(record):
    data = read_record(record)
    flag = sibling(record, ".cancel")
    if flag.exists():
        if flag.read_text(encoding="utf-8") != data["id"]:
            raise ValueError("Cancel marker does not match timer ID")
    else:
        atomic_text(flag, data["id"])
    return {"id": data["id"], "phase": "cancel_requested", "rearm": False}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["arm", "wait", "cancel"])
    p.add_argument("--record", type=Path, required=True)
    p.add_argument("--budget", type=Path)
    p.add_argument("--interval-seconds", type=float, default=1200)
    p.add_argument("--max-seconds", type=float, default=60)
    a = p.parse_args()
    if a.command == "arm":
        if a.budget is None:
            raise ValueError("arm requires --budget")
        value = arm(a.record, a.budget, a.interval_seconds)
    elif a.command == "wait":
        value = wait(a.record, a.max_seconds)
    else:
        value = cancel(a.record)
    print(json.dumps(value, ensure_ascii=False))

if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError) as e:
        print("ERROR: " + str(e), file=sys.stderr)
        sys.exit(1)
