#!/usr/bin/env python3
"""Small transactional, event-sourced task memory. No network/model/tool execution."""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import stat
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

VERSION = "0.1.0"
KINDS = {"evidence", "claim", "decision", "task"}
STATES = {"draft", "accepted", "retracted", "superseded", "open", "done"}
ARCHIVED = {"retracted", "superseded"}
COMPLETION = {"unknown", "claimed", "executed", "verified"}
ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,79}$")

class MissingEvidence(ValueError):
    """Only an actual missing file, never a permission or other I/O failure."""

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

def replay(con):
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
            meta["relocation_missing_history"] = data.get("missing_history", [])
        else:
            raise ValueError("Unknown event type; preserve DB, inspect compatible version.")
    if not meta:
        raise ValueError("Missing initialization event.")
    return nodes, meta, focus, cursor

def append(con, kind, payload):
    con.execute("INSERT INTO events(at, kind, payload) VALUES(?,?,?)",
                (datetime.now(timezone.utc).isoformat(), kind, dump(payload)))

def local_file(project, relative):
    path = Path(relative)
    if path.is_absolute():
        raise ValueError("files paths must be relative to project.")
    resolved = (Path(project) / path).resolve()
    if not resolved.is_relative_to(Path(project).resolve()):
        raise ValueError("files path escapes project.")
    try:
        mode = resolved.stat().st_mode
    except FileNotFoundError as exc:
        raise MissingEvidence("Evidence file missing: " + relative) from exc
    if not stat.S_ISREG(mode):
        raise ValueError("Evidence path is not a regular file: " + relative)
    return resolved

def completion_issues(node):
    stage = node.get("completion", "claimed")
    issues = []
    if stage != "verified":
        issues.append("task completion is " + str(stage) + "; not verified")
    val = node.get("validation", {})
    if not isinstance(val, dict) or any(not isinstance(val.get(f), str) or not val[f].strip()
                                       for f in ("method", "result", "limits")):
        issues.append("task lacks scoped validation.method/result/limits")
    if not node.get("files") and not node.get("depends_on"):
        issues.append("task lacks a bound result or supporting dependency")
    return issues

def dependency_closure(nodes, ids):
    selected, todo = set(), list(ids)
    while todo:
        key = todo.pop()
        if key not in selected:
            if key not in nodes:
                raise ValueError("Unknown referenced id: " + key)
            selected.add(key)
            todo.extend(nodes[key].get("depends_on", []))
    return selected

def negative_refs(node):
    value = node.get("rejected_ids", [])
    if not isinstance(value, list):
        return [], True
    return [x for x in value if isinstance(x, str)], any(not isinstance(x, str) for x in value)

def related_ids(nodes, ids):
    selected, pending = set(), list(ids)
    while pending:
        key = pending.pop()
        if key in selected:
            continue
        selected.add(key)
        if key in nodes:
            pending.extend(nodes[key].get("depends_on", []))
            pending.extend(negative_refs(nodes[key])[0])
    return selected

def effective(nodes, meta, strict=False):
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
        if node["kind"] == "task" and node["status"] == "done":
            if node.get("completion") == "unknown":
                reasons.append("unknown execution outcome cannot be completed; verify result first")
            if strict:
                reasons.extend(completion_issues(node))
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

def validate_node(node, nodes, meta, expected, strict=False):
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
    if "completion" in node:
        if node["kind"] != "task" or node["completion"] not in COMPLETION:
            raise ValueError("completion is a task-only unknown/claimed/executed/verified label.")
        if node["status"] == "done" and node["completion"] == "unknown":
            raise ValueError("Unknown execution outcome cannot be done; verify result before retrying.")
    deps = node.setdefault("depends_on", [])
    if not isinstance(deps, list) or any(not isinstance(x, str) for x in deps):
        raise ValueError("depends_on must be a list of ids.")
    if len(set(deps)) != len(deps) or key in deps or any(x not in nodes for x in deps):
        raise ValueError("Unknown, duplicate or self dependency.")
    rejected = node.get("rejected_ids", [])
    if (not isinstance(rejected, list) or any(not isinstance(x, str) for x in rejected)
            or len(set(rejected)) != len(rejected) or key in rejected
            or any(x not in nodes for x in rejected) or set(rejected) & set(deps)):
        raise ValueError("rejected_ids must be known, distinct negative references, separate from dependencies.")
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
    node["files"] = [{"path": x, "sha256": digest(local_file(meta["project"], x))}
                     for x in file_inputs]
    node["revision"] = expected + 1
    node["dep_revisions"] = {x: nodes[x]["revision"] for x in deps}
    if node["status"] in {"accepted", "done"}:
        states = effective(nodes, meta, strict=strict)
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
    if node["kind"] == "task" and node["status"] == "done":
        if strict or node.get("completion") == "verified":
            issues = completion_issues(node)
            if issues:
                raise ValueError("; ".join(issues))
    return node

def capsule(nodes, meta, focus, cursor, root, budget, retry_argv=None):
    states = effective(nodes, meta)
    lines = ["# Current recovery capsule", "", "Ledger cursor: " + str(cursor),
             "Project: " + meta["project"], "Profile: " + meta["profile"],
             "Contract: CONTRACT.md (read before action; do not infer missing constraints)", ""]
    selected = set()
    if focus is None:
        lines += ["No focus recorded. Inspect contract and records before choosing work."]
    else:
        lines += ["Next action: " + focus["next_action"], "",
                  "Open questions: " + dump(focus.get("open_questions", [])),
                  "Do not repeat: " + dump(focus.get("do_not_repeat", [])), "", "## Focus and dependencies"]
        selected = dependency_closure(nodes, focus["ids"])
        for key in sorted(selected):
            n = nodes[key]
            state, reasons = states[key]
            lines += [f"- {key}@{n['revision']} [{n['kind']}/{state}] {n['title']}",
                      "  scope: " + n["scope"],
                      "  depends_on: " + ", ".join(n.get("depends_on", []))]
            if reasons:
                lines += ["  REVIEW: " + "; ".join(reasons)]
            if n["kind"] == "task" and (n["status"] == "done" or "completion" in n):
                lines += ["  completion: " + str(n.get("completion", "claimed"))]
        exclusions = related_ids(nodes, selected) - selected
        for key in sorted(selected | exclusions):
            if key in nodes and negative_refs(nodes[key])[1]:
                lines += ["REVIEW: invalid legacy rejected_ids on " + key + "; inspect show before reuse."]
        for key in sorted(exclusions - selected):
            if key not in nodes:
                # Old ledgers allowed arbitrary extra fields. Never silently hide a broken reference.
                lines += ["REVIEW: missing negative reference " + key]
                continue
            n = nodes[key]
            state, reasons = states[key]
            lines += [f"- HISTORICAL REFERENCE {key}@{n['revision']} [{state}] {n['title']}",
                      "  scope: " + n["scope"], "  REVIEW: " + "; ".join(reasons)]
        selected.update(exclusions)
    counts = {}
    for key, (state, _) in states.items():
        if key not in selected and state in {"needs-review", "retracted", "superseded"}:
            counts[state] = counts.get(state, 0) + 1
    if counts:
        lines += ["", "## Outside-focus risks (summary only)", dump(counts),
                  "Query: list --status STATUS --limit 20; then show --id ID before reuse."]
    lines += ["", "Details: show --id ID; discovery: list; current integrity: audit.",
              "This is a regenerable view; DB holds history. Hashes do not prove semantics."]
    content = "\n".join(lines) + "\n"
    if len(content) > budget:
        retry = retry_argv or [sys.executable, str(Path(__file__).resolve()),
                               "resume", "--root", str(Path(root).resolve())]
        raise ValueError(f"Capsule needs {len(content)} characters; budget {budget}. "
                         "Narrow focus or explicitly increase budget; no silent truncation.\n"
                         "Retry argv: " + dump(retry + ["--chars", str(len(content))]))
    return content

def budget_for(explicit, focus):
    budget = explicit if explicit is not None else (focus or {}).get("capsule_chars", 6000)
    if type(budget) is not int or budget <= 0:
        raise ValueError("Character budget must be a positive integer; override with --chars.")
    return budget

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "put", "focus", "resume", "show", "list", "audit", "export", "backup", "relocate"])
    parser.add_argument("--root", required=True)
    parser.add_argument("--project")
    parser.add_argument("--profile", default="codex")
    parser.add_argument("--contract")
    parser.add_argument("--file")
    parser.add_argument("--id")
    parser.add_argument("--expected-revision", type=int)
    parser.add_argument("--chars", type=int)
    parser.add_argument("--editable", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--allow-missing-history", action="store_true")
    parser.add_argument("--status", choices=sorted(STATES | {"needs-review"}))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--offset", type=int, default=0)
    args = parser.parse_args()
    if args.editable and args.command != "show" or args.strict and args.command not in {"put", "audit"}:
        parser.error("--editable is for show; --strict is for put/audit.")
    if args.allow_missing_history and args.command != "relocate":
        parser.error("--allow-missing-history is for relocate only.")
    if (args.status or args.limit is not None or args.offset) and args.command != "list":
        parser.error("--status/--limit/--offset are for list only.")
    if args.offset < 0 or args.limit is not None and args.limit <= 0:
        parser.error("offset must be nonnegative; limit must be positive.")
    root = Path(args.root).resolve()
    if args.command == "init":
        if not args.project or not args.contract:
            raise ValueError("init needs --project and --contract.")
        project = Path(args.project).resolve()
        if not project.is_dir():
            raise ValueError("Project directory missing.")
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
            append(con, "init", {"project": str(project), "profile": args.profile, "tool_version": VERSION})
        con.close()
        atomic_text(root / "CONTRACT.md", contract)
        atomic_text(root / "START.md", "# Recovery entry\n\nRun task_memory.py resume --root this-directory. Read CONTRACT.md, then the regenerated CAPSULE.md; show focus IDs and evidence as needed.\n\nmemory.sqlite3 is the event ledger. CAPSULE.md and exports are regenerable views. Never infer current status from an old view.\n")
        print("Initialized " + str(root))
        return
    pending_view, view_cursor = None, None
    with connection(root) as con:
        if args.command in {"put", "focus", "relocate"} or args.command == "resume" and args.chars is not None:
            # Serialize read/check/write together, so optimistic revision checks are meaningful.
            con.execute("BEGIN IMMEDIATE")
        nodes, meta, focus, cursor = replay(con)
        if args.command == "put":
            data = read_json(args.file)
            if not isinstance(data, dict):
                raise ValueError("Node must be an object.")
            hint = data.pop("expected_revision", None)
            if hint is not None and (type(hint) is not int or hint < 0):
                raise ValueError("expected_revision must be a nonnegative integer.")
            if hint is not None and args.expected_revision is not None and hint != args.expected_revision:
                raise ValueError("CLI and editable expected_revision conflict.")
            expected = args.expected_revision if args.expected_revision is not None else hint or 0
            node = validate_node(data, nodes, meta, expected, strict=args.strict)
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
            for key in ("open_questions", "do_not_repeat"):
                if not isinstance(data.get(key, []), list) or any(not isinstance(x, str) for x in data.get(key, [])):
                    raise ValueError(key + " must be a string list.")
            budget = budget_for(args.chars, focus)
            data.pop("capsule_chars", None)
            if args.chars is not None or focus and "capsule_chars" in focus:
                data["capsule_chars"] = budget
            # Preflight without publishing a view. Commit the ledger before file publication.
            pending_view = capsule(nodes, meta, data, cursor + 1, root, budget,
                    retry_argv=[sys.executable, str(Path(__file__).resolve()), "focus",
                                "--root", str(root), "--file", str(Path(args.file).resolve())])
            append(con, "focus", data)
            view_cursor = cursor + 1
        elif args.command == "resume":
            budget = budget_for(args.chars, focus)
            save_budget = focus is not None and args.chars is not None and focus.get("capsule_chars") != budget
            view_cursor = cursor + int(save_budget)
            pending_view = capsule(nodes, meta, focus, view_cursor, root, budget)
            if save_budget:
                append(con, "focus", dict(focus, capsule_chars=budget))
        elif args.command == "relocate":
            if not args.project or not Path(args.project).resolve().is_dir():
                raise ValueError("relocate needs an existing --project directory.")
            project = str(Path(args.project).resolve())
            protected = dependency_closure(nodes, [k for k, n in nodes.items() if n["status"] not in ARCHIVED])
            if focus:
                protected.update(dependency_closure(nodes, focus["ids"]))
            protected = related_ids(nodes, protected)
            if args.allow_missing_history and any(k not in nodes or negative_refs(nodes[k])[1] for k in protected):
                raise ValueError("Cannot establish unrelated history: inspect broken legacy references first.")
            missing = []
            for node in nodes.values():
                for item in node.get("files", []):
                    try:
                        source = local_file(project, item["path"])
                    except MissingEvidence:
                        if (args.allow_missing_history and node["status"] in ARCHIVED
                                and node["id"] not in protected):
                            missing.append(dict(id=node["id"], revision=node["revision"], **item))
                            continue
                        raise
                    if digest(source) != item["sha256"]:
                        raise ValueError("Relocation evidence mismatch: " + item["path"])
            append(con, "relocate", {"previous_project": meta["project"], "project": project,
                                     "missing_history": missing})
            print(dump({"relocated": project, "missing_history": missing, "next": "run resume"}))
        elif args.command == "show":
            if args.id not in nodes:
                raise ValueError("Unknown id.")
            node = nodes[args.id]
            if args.editable:
                data = {k: v for k, v in node.items() if k not in {"revision", "dep_revisions", "files"}}
                data.update(files=[f["path"] for f in node.get("files", [])], expected_revision=node["revision"])
            else:
                state, reasons = effective(nodes, meta)[args.id]
                data = dict(node=node, effective_status=state, review_reasons=reasons)
                if node["kind"] == "task" and node["status"] == "done":
                    data["completion_status"] = node.get("completion", "claimed")
            print(json.dumps(data, ensure_ascii=False, indent=2))
        elif args.command == "list":
            states = effective(nodes, meta)
            items = [{"id": k, "revision": n["revision"], "kind": n["kind"],
                      "status": states[k][0], "title": n["title"]} for k, n in sorted(nodes.items())
                     if args.status is None or states[k][0] == args.status]
            if args.limit is not None or args.offset:
                end = len(items) if args.limit is None else args.offset + args.limit
                print(dump(dict(total=len(items), offset=args.offset,
                                next_offset=end if end < len(items) else None, items=items[args.offset:end])))
            else:
                print(dump(items))
        elif args.command == "audit":
            states = effective(nodes, meta, strict=args.strict)
            issues = {k: reasons for k, (s, reasons) in states.items() if reasons and s == "needs-review"}
            print(dump({"node_count": len(nodes), "review": issues,
                        "relocation_missing_history": meta.get("relocation_missing_history", [])}))
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
    if pending_view is not None:
        try:
            atomic_text(root / "CAPSULE.md", pending_view)
        except OSError as exc:
            raise ValueError(f"Ledger committed/read at cursor {view_cursor}, but CAPSULE publication failed; "
                             f"run resume to rebuild (do not repeat the mutation): {exc}") from exc
        if args.command == "resume":
            print(pending_view, end="")
        else:
            print("Focus committed and view published; run resume before reuse.")

if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        sys.exit(1)
