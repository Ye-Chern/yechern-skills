#!/usr/bin/env python3
"""User-selected wall-clock budget. This helper does not register host completion events."""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import time
from task_memory import atomic_text

def status(data, now):
    left = data["deadline_epoch"] - now
    return {"now_utc": datetime.fromtimestamp(now, timezone.utc).isoformat(),
            "deadline_utc": datetime.fromtimestamp(data["deadline_epoch"], timezone.utc).isoformat(),
            "remaining_seconds": round(max(0, left), 1),
            "phase": "expired" if left <= 0 else "deliver" if left <= data["reserve_seconds"] else "work",
            "can_wake_model": False,
            "action": "do one meaningful task block" if left > data["reserve_seconds"] else "stop new searches; save state, verify recovery ZIP, publish artifacts"}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["start", "status", "wait"])
    p.add_argument("--file", type=Path, required=True)
    p.add_argument("--minutes", type=float)
    p.add_argument("--reserve-minutes", type=float, default=5)
    p.add_argument("--seconds", type=float, default=30)
    a = p.parse_args()
    if a.command == "start":
        if a.file.exists():
            raise ValueError("Budget exists; preserve the original deadline, or start an explicitly new window using a new filename")
        if a.minutes is None or not math.isfinite(a.minutes) or a.minutes <= 0:
            raise ValueError("Use a positive finite user-selected --minutes")
        if not math.isfinite(a.reserve_minutes) or not 0 < a.reserve_minutes <= a.minutes:
            raise ValueError("Reserve must be positive and no greater than total minutes")
        now = time.time()
        data = {"start_epoch": now, "deadline_epoch": now + a.minutes * 60,
                "reserve_seconds": a.reserve_minutes * 60, "elapsed_basis": "UTC wall time; includes downtime"}
        a.file.parent.mkdir(parents=True, exist_ok=True)
        atomic_text(a.file, json.dumps(data, indent=2) + "\n")
    else:
        data = json.loads(a.file.read_text(encoding="utf-8-sig"))
        if a.command == "wait":
            if not math.isfinite(a.seconds) or not 0 <= a.seconds <= 60:
                raise ValueError("Foreground probe waits at most 60 seconds; do not use sleeps to fill a work budget")
            time.sleep(min(a.seconds, max(0, data["deadline_epoch"] - time.time())))
    print(json.dumps(status(data, time.time()), ensure_ascii=False))

if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError) as e:
        print("ERROR: " + str(e), file=sys.stderr)
        sys.exit(1)
