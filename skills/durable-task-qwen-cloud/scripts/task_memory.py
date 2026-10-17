#!/usr/bin/env python3
"""Small transactional, event-sourced task memory. No network/model/tool execution."""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

VERSION = "qwen-cloud-0.1.0"
KINDS = {"evidence", "claim", "decision", "task"}
STATES = {"draft", "accepted", "retracted", "superseded", "open", "done"}
ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,79}$")

def dump(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)

def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def digest(path):
    with Path(path).open("rb") as handle:
        h = hashlib.sha256()
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def atomic_text(path, content):
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".memory-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

@contextmanager
def connection(root):
    path = Path(root) / "memory.sqlite3"
    if not path.is_file():
        raise ValueError("Memory not initialized; run init first.")
    con = sqlite3.connect(path, timeout=10)
    con.execute("PRAGMA synchronous=FULL")
    try:
        with con:
            yield con
    finally:
        con.close()

def replay(con, root):
    nodes, meta, focus = {}, {}, None
    cursor = 0
    for seq, kind, payload in con.execute("SELECT seq, kind, payload FROM events ORDER BY seq"):
        data = json.loads(payload)
        cursor = seq
        if kind == "init":
            meta = data
        elif kind == "put":
            nodes[data["id"]] = data
        elif kind == "focus":
            focus = data
        elif kind == "relocate":
            meta["project"] = data["project"]
            if "project_from_ledger" in data:
                meta["project_from_ledger"] = data["project_from_ledger"]
            else:
                meta.pop("project_from_ledger", None)
        else:
            raise ValueError("Unknown event type; preserve DB, inspect compatible version.")
    if not meta:
        raise ValueError("Missing initialization event.")
    if "project_from_ledger" in meta:
        meta["project"] = str((Path(root) / meta["project_from_ledger"]).resolve())
    return nodes, meta, focus, cursor

def append(con, kind, payload):
    con.execute("INSERT INTO events(at, kind, payload) VALUES(?,?,?)",
                (datetime.now(timezone.utc).isoformat(), kind, dump(payload)))

def layout(root, project):
    project = Path(project).resolve()
    if not Path(root).resolve().is_relative_to(project):
        raise ValueError("Ledger must be inside project for portable recovery.")
    return os.path.relpath(project, root).replace("\\", "/")

def local_file(project, relative):
    path = Path(relative)
    if path.is_absolute():
        raise ValueError("files paths must be relative to project.")
    resolved = (Path(project) / path).resolve()
    if not resolved.is_relative_to(Path(project).resolve()):
        raise ValueError("files path escapes project.")
    if not resolved.is_file():
        raise ValueError("Evidence file missing: " + relative)
    return resolved

def effective(nodes, meta):
    results = {}
    visiting = set()
    def inspect(key):
        if key in results:
            return results[key]
        if key in visiting:
            raise ValueError("Dependency cycle: " + key)
        visiting.add(key)
        node = nodes[key]
        reasons = []
        for item in node.get("files", []):
            try:
                if digest(local_file(meta["project"], item["path"])) != item["sha256"]:
                    reasons.append("changed file: " + item["path"])
            except (OSError, ValueError):
                reasons.append("missing/unreadable/outside-project file: " + item["path"])
        for dep in node.get("depends_on", []):
            if dep not in nodes:
                reasons.append("missing dependency: " + dep)
                continue
            state, _ = inspect(dep)
            if state not in {"accepted", "done"}:
                reasons.append("unusable dependency: " + dep + " (" + state + ")")
            if node.get("dep_revisions", {}).get(dep) != nodes[dep]["revision"]:
                reasons.append("revised dependency: " + dep)
        state = node["status"]
        if reasons and state not in {"retracted", "superseded"}:
            state = "needs-review"
        visiting.remove(key)
        results[key] = (state, reasons)
        return results[key]
    for key in nodes:
        inspect(key)
    return results

def validate_node(node, nodes, meta, expected):
    if not isinstance(node, dict):
        raise ValueError("Node must be an object.")
    for field in ("id", "kind", "title", "status", "scope", "rationale"):
        if not isinstance(node.get(field), str) or not node[field].strip():
            raise ValueError("Nonempty string required: " + field)
    key = node["id"]
    if not ID.fullmatch(key) or node["kind"] not in KINDS or node["status"] not in STATES:
        raise ValueError("Invalid id, kind or status.")
    old = nodes.get(key)
    if expected != (old["revision"] if old else 0):
        raise ValueError("Revision conflict; show latest node before updating.")
    if old and old["kind"] != node["kind"]:
        raise ValueError("Node kind is immutable; create a new id.")
    if (node["kind"] == "task") != (node["status"] in {"open", "done"}):
        raise ValueError("Tasks use open/done; other kinds use draft/accepted/retracted/superseded.")
    deps = node.setdefault("depends_on", [])
    if not isinstance(deps, list) or any(not isinstance(x, str) for x in deps):
        raise ValueError("depends_on must be a list of ids.")
    if len(set(deps)) != len(deps) or key in deps or any(x not in nodes for x in deps):
        raise ValueError("Unknown, duplicate or self dependency.")
    # Reject cycles even when an updated node introduces one.
    def reaches(current, target, seen):
        if current == target:
            return True
        if current in seen:
            return False
        seen.add(current)
        return any(reaches(d, target, seen) for d in nodes[current].get("depends_on", []))
    if any(reaches(d, key, set()) for d in deps):
        raise ValueError("Dependency cycle.")
    file_inputs = node.get("files", [])
    if not isinstance(file_inputs, list) or any(not isinstance(x, str) for x in file_inputs):
        raise ValueError("files must be relative path strings; hashes are captured by this tool.")
    ledger = Path(meta["runtime_ledger"])
    views = {ledger / n for n in ("memory.sqlite3", "CAPSULE.md", "RECOVERY_INDEX.md", "FOCUS.json", "START.md")}
    if any(local_file(meta["project"], x) in views for x in file_inputs):
        raise ValueError("Do not bind live ledger or generated recovery views; freeze a separate result.")
    node["files"] = [{"path": x, "sha256": digest(local_file(meta["project"], x))}
                     for x in file_inputs]
    node["revision"] = expected + 1
    node["dep_revisions"] = {x: nodes[x]["revision"] for x in deps}
    if node["status"] in {"accepted", "done"}:
        states = effective(nodes, meta)
        if any(states[d][0] not in {"accepted", "done"} for d in deps):
            raise ValueError("Cannot accept/complete a node with unusable dependencies.")
    if node["kind"] in {"evidence", "claim"} and node["status"] == "accepted":
        val = node.get("validation", {})
        if not isinstance(val, dict) or any(not isinstance(val.get(f), str) or not val[f].strip()
                                           for f in ("method", "result", "limits")):
            raise ValueError("Accepted evidence/claim needs validation.method/result/limits.")
        if node["kind"] == "evidence" and not node["files"]:
            raise ValueError("Accepted evidence needs a local, reproducible source/result file.")
        if node["kind"] == "claim" and not any(nodes[d]["kind"] in {"evidence", "claim"} for d in deps):
            raise ValueError("Accepted claim needs an evidence/claim dependency.")
    return node

def review_order(nodes, states):
    ordered, seen = [], set()
    def visit(k):
        if k in seen:
            return
        seen.add(k)
        for d in nodes[k].get("depends_on", []):
            visit(d)
        if states[k][0] == "needs-review":
            ordered.append(k)
    for k in nodes:
        visit(k)
    return ordered

def capsule(nodes, meta, focus, cursor, root, budget):
    states = effective(nodes, meta)
    selected, todo = set(), list(focus["ids"] if focus else [])
    while todo:
        k = todo.pop()
        if k not in selected:
            selected.add(k)
            todo.extend(nodes[k].get("depends_on", []))
    # Full details stay addressable; entry never repeats every scope/rationale.
    index = ["# Recovery index", "", "Ledger cursor: " + str(cursor),
             "Review order (upstream first; revalidate, never auto-refresh): " + ", ".join(review_order(nodes, states)), ""]
    for k, n in sorted(nodes.items()):
        st, why = states[k]
        index += [f"## {k}@{n['revision']} [{n['kind']}/{st}] {n['title']}",
                  "scope: " + n["scope"], "depends_on: " + ", ".join(n.get("depends_on", [])),
                  "review: " + "; ".join(why), ""]
    atomic_text(Path(root) / "RECOVERY_INDEX.md", "\n".join(index))
    if focus:
        atomic_text(Path(root) / "FOCUS.json", json.dumps(focus, ensure_ascii=False, indent=2) + "\n")
    lines = ["# Current recovery capsule", "", "Ledger cursor: " + str(cursor),
             "Ledger: " + str(root), "Project: " + meta["project"],
             "Read CONTRACT.md before acting; inspect current evidence using show --id ID.", ""]
    if focus:
        lines += ["Next action: " + focus["next_action"],
                  "Open questions: " + dump(focus.get("open_questions", [])),
                  "Do not repeat: " + dump(focus.get("do_not_repeat", [])),
                  "Jobs: " + dump(focus.get("waiting_on", [])), "", "## Focus/dependencies"]
        keys = sorted(selected)
        for k in keys[:8]:
            n = nodes[k]
            lines += [f"- {k}@{n['revision']} [{n['kind']}/{states[k][0]}]"]
        if len(keys) > 8:
            lines += [f"Full closure: {len(keys)} nodes; remaining IDs in RECOVERY_INDEX.md. This entry is a route, not complete evidence."]
    else:
        lines += ["No focus; read contract and index before selecting work."]
    hazards = [k for k, (st, _) in states.items() if st in {"needs-review", "retracted", "superseded"}]
    lines += ["", f"Hazards/exclusions: {len(hazards)}; " + ", ".join(hazards[:8]),
              "All statuses and review order: RECOVERY_INDEX.md; full frontier/jobs: FOCUS.json.",
              "Hashes check bytes/declared dependencies only. Job records do not prove a process is alive."]
    content = "\n".join(lines) + "\n"
    if len(content) > budget:
        # Save a usable route even if user supplies a very long frontier. No omitted constraints are represented as read.
        route = "\n".join(lines[:7] + ["Detailed frontier exceeds entry budget; read FOCUS.json (all fields) before acting.",
                   f"Hazards/exclusions: {len(hazards)}; read RECOVERY_INDEX.md, then show relevant IDs."])+"\n"
        if len(route) > budget:
            raise ValueError(f"Recovery route needs {len(route)} characters; budget {budget}. Use resume --chars {len(route)}.")
        content = route
    atomic_text(Path(root) / "CAPSULE.md", content)
    return content

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "put", "focus", "resume", "show", "list", "audit", "export", "backup", "relocate"])
    parser.add_argument("--root", required=True)
    parser.add_argument("--project")
    parser.add_argument("--profile", default="qwen-cloud")
    parser.add_argument("--contract")
    parser.add_argument("--file")
    parser.add_argument("--id")
    parser.add_argument("--expected-revision", type=int, default=0)
    parser.add_argument("--chars", type=int, default=2400)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if args.command == "init":
        if not args.project or not args.contract:
            raise ValueError("init needs --project and --contract.")
        project = Path(args.project).resolve()
        if not project.is_dir():
            raise ValueError("Project directory missing.")
        portable = layout(root, project)
        contract = Path(args.contract).read_text(encoding="utf-8-sig")
        if not contract.strip():
            raise ValueError("Contract cannot be empty.")
        root.mkdir(parents=True, exist_ok=True)
        if any((root / name).exists() for name in ("memory.sqlite3", "CONTRACT.md", "START.md")):
            raise ValueError("Existing memory/entry; do not overwrite.")
        con = sqlite3.connect(root / "memory.sqlite3", timeout=10)
        with con:
            con.execute("CREATE TABLE events(seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL)")
            con.execute("CREATE TRIGGER no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'append-only'); END")
            con.execute("CREATE TRIGGER no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'append-only'); END")
            append(con, "init", {"project": str(project), "project_from_ledger": portable, "profile": args.profile, "tool_version": VERSION})
        con.close()
        atomic_text(root / "CONTRACT.md", contract)
        atomic_text(root / "START.md", "# Recovery entry\n\nUse the uploaded skill scripts/task_memory.py resume --root this-directory. This ledger resolves project relative to itself; copy the entire project keeping layout. Read CONTRACT.md, then regenerated CAPSULE.md, FOCUS.json if routed, then show evidence IDs. Legacy absolute-path ledgers require explicit relocate --project before any read.\n\nmemory.sqlite3 is the event ledger. CAPSULE.md and exports are regenerable views. Never infer current status from an old view.\n")
        print("Initialized " + str(root))
        return
    with connection(root) as con:
        if args.command in {"put", "focus", "relocate"}:
            # Serialize read/check/write together, so optimistic revision checks are meaningful.
            con.execute("BEGIN IMMEDIATE")
        nodes, meta, focus, cursor = replay(con, root)
        meta["runtime_ledger"] = str(root)
        if "project_from_ledger" not in meta and args.command != "relocate":
            raise ValueError("Legacy absolute-path ledger: refusing old project. Use relocate --root HERE --project COPIED_PROJECT first.")
        if args.command == "put":
            node = validate_node(read_json(args.file), nodes, meta, args.expected_revision)
            append(con, "put", node)
            print(dump({"id": node["id"], "revision": node["revision"]}))
        elif args.command == "focus":
            data = read_json(args.file)
            if not isinstance(data, dict) or not isinstance(data.get("ids"), list) or not data["ids"]:
                raise ValueError("focus.ids must be a nonempty list.")
            if any(not isinstance(x, str) or x not in nodes for x in data["ids"]):
                raise ValueError("Unknown focus id.")
            if not isinstance(data.get("next_action"), str) or not data["next_action"].strip():
                raise ValueError("focus.next_action required.")
            for key in ("open_questions", "do_not_repeat", "waiting_on"):
                if not isinstance(data.get(key, []), list) or any(not isinstance(x, str) for x in data.get(key, [])):
                    raise ValueError(key + " must be a string list.")
            # Commit truth first. Views are regenerable even if the filesystem/budget fails.
            append(con, "focus", data)
            con.commit()
            try:
                capsule(nodes, meta, data, cursor + 1, root, args.chars)
                print("Focus committed; views generated. Run resume before reuse.")
            except (ValueError, OSError) as exc:
                print("Focus COMMITTED; views pending: " + str(exc) + "; run resume.", file=sys.stderr)
        elif args.command == "resume":
            print(capsule(nodes, meta, focus, cursor, root, args.chars), end="")
        elif args.command == "relocate":
            if not args.project or not Path(args.project).resolve().is_dir():
                raise ValueError("relocate needs an existing --project directory.")
            project = str(Path(args.project).resolve())
            portable = layout(root, Path(project))
            for node in nodes.values():
                # Retired nodes remain unusable history; their old byte bindings may
                # intentionally refer to a prior version of a currently edited file.
                if node["status"] in {"retracted", "superseded"}:
                    continue
                for item in node.get("files", []):
                    if digest(local_file(project, item["path"])) != item["sha256"]:
                        raise ValueError("Relocation evidence mismatch: " + item["path"])
            append(con, "relocate", {"previous_project": meta["project"], "project": project, "project_from_ledger": portable})
            print("Relocated after checking all recorded files; run resume.")
        elif args.command == "show":
            if args.id not in nodes:
                raise ValueError("Unknown id.")
            state, reasons = effective(nodes, meta)[args.id]
            print(json.dumps({"node": nodes[args.id], "effective_status": state,
                              "review_reasons": reasons}, ensure_ascii=False, indent=2))
        elif args.command == "list":
            states = effective(nodes, meta)
            print(dump([{"id": k, "revision": n["revision"], "kind": n["kind"],
                         "status": states[k][0], "title": n["title"]} for k, n in sorted(nodes.items())]))
        elif args.command == "audit":
            states = effective(nodes, meta)
            issues = {k: reasons for k, (s, reasons) in states.items() if reasons and s == "needs-review"}
            print(dump({"ledger": str(root), "project": meta["project"], "node_count": len(nodes), "review": issues, "review_order": review_order(nodes, states)}))
            if issues:
                sys.exit(2)
        elif args.command == "export":
            rows = [{"seq": s, "at": a, "kind": k, "payload": json.loads(p)}
                    for s, a, k, p in con.execute("SELECT seq,at,kind,payload FROM events ORDER BY seq")]
            if not args.file:
                raise ValueError("export needs --file output path.")
            atomic_text(Path(args.file).resolve(), "\n".join(dump(r) for r in rows) + "\n")
            print("Exported " + str(len(rows)) + " events.")
        elif args.command == "backup":
            if not args.file:
                raise ValueError("backup needs --file output path.")
            target = Path(args.file).resolve()
            if target.exists():
                raise ValueError("Backup exists; choose a fresh path.")
            # SQLite backup API gives a consistent snapshot even with active readers/writers.
            destination = sqlite3.connect(target)
            try:
                with destination:
                    con.backup(destination)
            finally:
                destination.close()
            print("Backup " + str(target))

if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        sys.exit(1)
