"""Behavioral tests for the local Qwen Cloud durable-task scripts.

All project mutation is confined to TemporaryDirectory roots. No network, model,
phone, or long wait is used. Run: python -m unittest discover -s tests -v
"""
import hashlib
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile

PACKAGE = Path(__file__).resolve().parents[1]
SCRIPTS = PACKAGE / "scripts"
MEMORY = SCRIPTS / "task_memory.py"
BUNDLE = SCRIPTS / "cloud_bundle.py"
BUDGET = SCRIPTS / "work_budget.py"
PYTHON = sys.executable


def invoke(script, *args, expected=0):
    result = subprocess.run([PYTHON, str(script), *map(str, args)],
                            capture_output=True, text=True, encoding="utf-8",
                            timeout=20)
    if result.returncode != expected:
        raise AssertionError(
            f"{script.name} expected rc={expected}, got {result.returncode}\n"
            f"stdout={result.stdout}\nstderr={result.stderr}")
    return result


def mem(command, root, expected=0, **kwargs):
    args = [command, "--root", root]
    for key, value in kwargs.items():
        args += ["--" + key.replace("_", "-"), value]
    return invoke(MEMORY, *args, expected=expected)


def put(project, root, node, expected=0, revision=0):
    payload = project.parent / ("node-" + node["id"] + ".json")
    payload.write_text(json.dumps(node, ensure_ascii=False), encoding="utf-8")
    return mem("put", root, expected=expected, file=payload,
               expected_revision=str(revision))


def node(identifier, kind, status, *, deps=(), files=(), scope="test scope", rationale="test rationale"):
    value = {"id": identifier, "kind": kind, "title": identifier,
             "status": status, "scope": scope, "rationale": rationale,
             "depends_on": list(deps), "files": list(files)}
    if kind in {"evidence", "claim"} and status == "accepted":
        value["validation"] = {"method": "read exact test fixture",
                               "result": "expected bytes observed",
                               "limits": "behavior test only"}
    return value


def init_project(base, name="project"):
    project = base / name
    project.mkdir(parents=True)
    contract = project / "CONTRACT.md"
    contract.write_text("Goal: exercise recovery behavior.\n", encoding="utf-8")
    root = project / "task-memory" / "case"
    mem("init", root, project=project, contract=contract)
    return project, root


def rows(db_path):
    with closing(sqlite3.connect(db_path)) as con:
        return con.execute("SELECT seq, kind, payload FROM events ORDER BY seq").fetchall()


class CloudBehaviorTests(unittest.TestCase):
    def test_portable_copy_detects_corruption_then_relocates_copy(self):
        with tempfile.TemporaryDirectory(prefix="qwen-portable-") as raw:
            base = Path(raw)
            original, root = init_project(base)
            source = original / "evidence.txt"
            source.write_bytes(b"original evidence bytes\x00\xff")
            put(original, root, node("E", "evidence", "accepted", files=["evidence.txt"]))

            replica = base / "replica"
            shutil.copytree(original, replica)
            copied_root = replica / "task-memory" / "case"
            copied_source = replica / "evidence.txt"
            copied_source.write_bytes(b"deliberately corrupted copy")
            drift = mem("audit", copied_root, expected=2)
            self.assertIn("evidence.txt", json.loads(drift.stdout)["review"]["E"][0])
            before_original = mem("audit", root)
            self.assertEqual(json.loads(before_original.stdout)["review"], {})
            failed_relocate = mem("relocate", copied_root, expected=1, project=replica)
            self.assertIn("Relocation evidence mismatch", failed_relocate.stderr)
            self.assertEqual(json.loads(mem("show", root, id="E").stdout)["node"]["revision"], 1)

            shutil.copyfile(source, copied_source)
            mem("relocate", copied_root, project=replica)
            recovered = mem("resume", copied_root).stdout
            self.assertIn(str(replica), recovered)
            self.assertEqual(json.loads(mem("audit", copied_root).stdout)["review"], {})
            self.assertEqual(source.read_bytes(), copied_source.read_bytes())

    def test_legacy_absolute_root_refuses_reads_until_checked_relocation(self):
        with tempfile.TemporaryDirectory(prefix="qwen-legacy-") as raw:
            base = Path(raw)
            old = base / "old-project"
            old.mkdir()
            (old / "evidence.txt").write_bytes(b"legacy bytes")
            replica = base / "copied-project"
            shutil.copytree(old, replica)
            root = replica / "memory"
            root.mkdir()
            digest = hashlib.sha256((old / "evidence.txt").read_bytes()).hexdigest()
            init_payload = {"project": str(old), "profile": "legacy", "tool_version": "test"}
            evidence = node("LEGACY", "evidence", "accepted", files=[])
            evidence["files"] = [{"path": "evidence.txt", "sha256": digest}]
            evidence["revision"] = 1
            evidence["dep_revisions"] = {}
            with closing(sqlite3.connect(root / "memory.sqlite3")) as con:
                with con:
                    con.execute("CREATE TABLE events(seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL)")
                    con.execute("INSERT INTO events(at,kind,payload) VALUES(?,?,?)", ("2026-01-01T00:00:00+00:00", "init", json.dumps(init_payload)))
                    con.execute("INSERT INTO events(at,kind,payload) VALUES(?,?,?)", ("2026-01-01T00:00:01+00:00", "put", json.dumps(evidence)))
            rejected = mem("list", root, expected=1)
            self.assertIn("Legacy absolute-path ledger", rejected.stderr)
            bad_copy = replica / "evidence.txt"
            bad_copy.write_bytes(b"bad replica")
            refused = mem("relocate", root, expected=1, project=replica)
            self.assertIn("Relocation evidence mismatch", refused.stderr)
            bad_copy.write_bytes((old / "evidence.txt").read_bytes())
            mem("relocate", root, project=replica)
            self.assertEqual(json.loads(mem("show", root, id="LEGACY").stdout)["effective_status"], "accepted")
            self.assertIn(str(replica), mem("resume", root).stdout)

    def test_retraction_and_upstream_repair_never_auto_revive_descendants(self):
        with tempfile.TemporaryDirectory(prefix="qwen-cascade-") as raw:
            base = Path(raw)
            project, root = init_project(base)
            (project / "evidence.txt").write_text("first", encoding="utf-8")
            put(project, root, node("E", "evidence", "accepted", files=["evidence.txt"]))
            put(project, root, node("C", "claim", "accepted", deps=["E"]))
            put(project, root, node("D", "decision", "accepted", deps=["C"]))

            put(project, root, node("E", "evidence", "retracted", files=["evidence.txt"]), revision=1)
            states = {x["id"]: x["status"] for x in json.loads(mem("list", root).stdout)}
            self.assertEqual(states, {"C": "needs-review", "D": "needs-review", "E": "retracted"})

            put(project, root, node("E", "evidence", "accepted", files=["evidence.txt"]), revision=2)
            states = {x["id"]: x["status"] for x in json.loads(mem("list", root).stdout)}
            self.assertEqual(states, {"C": "needs-review", "D": "needs-review", "E": "accepted"})
            self.assertIn("revised dependency", json.loads(mem("show", root, id="C").stdout)["review_reasons"][0])
            put(project, root, node("C", "claim", "accepted", deps=["E"]), revision=1)
            self.assertEqual(json.loads(mem("list", root).stdout)[1]["status"], "needs-review")
            put(project, root, node("D", "decision", "accepted", deps=["C"]), revision=1)
            self.assertEqual(json.loads(mem("audit", root).stdout)["review"], {})

    def test_retired_bindings_may_be_missing_on_copy_but_stay_retired(self):
        with tempfile.TemporaryDirectory(prefix="qwen-retired-copy-") as raw:
            base = Path(raw)
            project, root = init_project(base)
            (project / "retracted.txt").write_bytes(b"old retracted evidence")
            (project / "superseded.txt").write_bytes(b"old superseded evidence")
            (project / "active.txt").write_bytes(b"current active evidence")
            put(project, root, node("ER", "evidence", "accepted", files=["retracted.txt"]))
            put(project, root, node("CR", "claim", "accepted", deps=["ER"]))
            put(project, root, node("ER", "evidence", "retracted", files=["retracted.txt"]), revision=1)
            put(project, root, node("ES", "evidence", "accepted", files=["superseded.txt"]))
            put(project, root, node("CS", "claim", "accepted", deps=["ES"]))
            put(project, root, node("ES", "evidence", "superseded", files=["superseded.txt"]), revision=1)
            put(project, root, node("EA", "evidence", "accepted", files=["active.txt"]))

            replica = base / "replica"
            shutil.copytree(project, replica)
            copied_root = replica / "task-memory" / "case"
            (replica / "retracted.txt").unlink()
            (replica / "superseded.txt").unlink()
            mem("relocate", copied_root, project=replica)

            states = {item["id"]: item["status"] for item in json.loads(mem("list", copied_root).stdout)}
            self.assertEqual(states["ER"], "retracted")
            self.assertEqual(states["ES"], "superseded")
            self.assertEqual(states["CR"], "needs-review")
            self.assertEqual(states["CS"], "needs-review")
            self.assertEqual(states["EA"], "accepted")
            er = json.loads(mem("show", copied_root, id="ER").stdout)["node"]
            es = json.loads(mem("show", copied_root, id="ES").stdout)["node"]
            self.assertEqual(er["files"][0]["sha256"], hashlib.sha256(b"old retracted evidence").hexdigest())
            self.assertEqual(es["files"][0]["sha256"], hashlib.sha256(b"old superseded evidence").hexdigest())
            rejected_claim = put(replica, copied_root, node("BAD", "claim", "accepted", deps=["ER", "ES"]), expected=1)
            self.assertIn("Cannot accept/complete", rejected_claim.stderr)
            listed = json.loads(mem("list", copied_root).stdout)
            self.assertNotIn("BAD", {item["id"] for item in listed})
            self.assertFalse((replica / "retracted.txt").exists())
            self.assertFalse((replica / "superseded.txt").exists())
            self.assertTrue((project / "retracted.txt").is_file())
            self.assertTrue((project / "superseded.txt").is_file())

    def test_active_missing_binding_still_blocks_relocation(self):
        with tempfile.TemporaryDirectory(prefix="qwen-active-missing-") as raw:
            base = Path(raw)
            project, root = init_project(base)
            (project / "active.txt").write_bytes(b"required active evidence")
            put(project, root, node("EA", "evidence", "accepted", files=["active.txt"]))
            replica = base / "replica"
            shutil.copytree(project, replica)
            copied_root = replica / "task-memory" / "case"
            (replica / "active.txt").unlink()
            before = len(rows(copied_root / "memory.sqlite3"))
            refused = mem("relocate", copied_root, expected=1, project=replica)
            self.assertIn("active.txt", refused.stderr)
            self.assertIn("missing", refused.stderr.lower())
            after = len(rows(copied_root / "memory.sqlite3"))
            self.assertEqual(after, before)
            self.assertEqual(json.loads(mem("show", copied_root, id="EA").stdout)["effective_status"], "needs-review")
            self.assertTrue((project / "active.txt").is_file())

    def test_long_scope_and_focus_keep_full_route_outside_short_capsule(self):
        with tempfile.TemporaryDirectory(prefix="qwen-route-") as raw:
            base = Path(raw)
            project, root = init_project(base)
            (project / "evidence.txt").write_text("x", encoding="utf-8")
            long_scope = "SCOPE-BEGIN-" + ("scope detail; " * 900) + "-SCOPE-END"
            put(project, root, node("E", "evidence", "accepted", files=["evidence.txt"], scope=long_scope))
            long_action = "ACTION-BEGIN-" + ("resume from checkpoint; " * 250) + "-ACTION-END"
            long_question = "QUESTION-BEGIN-" + ("what remains? " * 150) + "-QUESTION-END"
            long_wait = "JOB-BEGIN-" + ("pending block; " * 150) + "-JOB-END"
            focus = base / "focus.json"
            focus.write_text(json.dumps({"ids": ["E"], "next_action": long_action,
                                         "open_questions": [long_question],
                                         "do_not_repeat": ["avoid rerunning committed blocks"],
                                         "waiting_on": [long_wait]}, ensure_ascii=False), encoding="utf-8")
            mem("focus", root, file=focus, chars="900")
            route = mem("resume", root, chars="900").stdout
            self.assertLessEqual(len(route), 900)
            self.assertIn("read FOCUS.json", route)
            self.assertIn("RECOVERY_INDEX.md", route)
            saved_focus = json.loads((root / "FOCUS.json").read_text(encoding="utf-8"))
            self.assertEqual(saved_focus["next_action"], long_action)
            self.assertEqual(saved_focus["open_questions"], [long_question])
            self.assertEqual(saved_focus["waiting_on"], [long_wait])
            index = (root / "RECOVERY_INDEX.md").read_text(encoding="utf-8")
            self.assertIn("SCOPE-BEGIN-", index)
            self.assertIn("-SCOPE-END", index)
            shown = json.loads(mem("show", root, id="E").stdout)
            self.assertEqual(shown["node"]["scope"], long_scope)

    def test_focus_event_commits_when_view_generation_fails(self):
        with tempfile.TemporaryDirectory(prefix="qwen-focus-failure-") as raw:
            base = Path(raw)
            project, root = init_project(base)
            (project / "evidence.txt").write_text("x", encoding="utf-8")
            put(project, root, node("E", "evidence", "accepted", files=["evidence.txt"]))
            focus = base / "tiny-focus.json"
            focus.write_text(json.dumps({"ids": ["E"], "next_action": "continue",
                                         "open_questions": [], "do_not_repeat": [], "waiting_on": []}), encoding="utf-8")
            failed_view = mem("focus", root, file=focus, chars="20")
            self.assertIn("Focus COMMITTED; views pending", failed_view.stderr)
            events = rows(root / "memory.sqlite3")
            self.assertEqual(events[-1][1], "focus")
            self.assertEqual(json.loads(events[-1][2])["next_action"], "continue")
            resumed = mem("resume", root, chars="1200").stdout
            self.assertIn("Next action: continue", resumed)
            self.assertEqual(int((root / "CAPSULE.md").read_text(encoding="utf-8").splitlines()[2].split(": ")[1]), len(events))

    def test_bundle_rebuilds_views_checks_cursor_and_roundtrips_bytes(self):
        with tempfile.TemporaryDirectory(prefix="qwen-bundle-") as raw:
            base = Path(raw)
            project, root = init_project(base)
            (project / "evidence.txt").write_bytes(b"source\x00\xff")
            put(project, root, node("E", "evidence", "accepted", files=["evidence.txt"]))
            focus = base / "focus.json"
            focus.write_text(json.dumps({"ids": ["E"], "next_action": "resume actual work",
                                         "open_questions": [], "do_not_repeat": [], "waiting_on": []}), encoding="utf-8")
            mem("focus", root, file=focus)
            (root / "CAPSULE.md").write_text("STALE SENTINEL", encoding="utf-8")
            (root / "EVENTS.jsonl").write_text("STALE EXPORT", encoding="utf-8")

            archive = base / "recovery.zip"
            result = invoke(BUNDLE, "pack", "--project", project, "--ledger", root, "--output", archive)
            packed = json.loads(result.stdout)
            verified = json.loads(invoke(BUNDLE, "verify", "--zip", archive).stdout)
            self.assertTrue(archive.is_file())
            with zipfile.ZipFile(archive) as z:
                manifest = json.loads(z.read("BUNDLE_MANIFEST.json"))
                self.assertEqual(manifest["cursor"], packed["cursor"])
                self.assertEqual(manifest["cursor"], verified["cursor"])
                ledger_member = manifest["ledger"] + "/memory.sqlite3"
                staged_db = sqlite3.connect(":memory:")
                staged_db.deserialize(z.read(ledger_member))
                max_seq = staged_db.execute("select max(seq) from events").fetchone()[0]
                staged_db.close()
                self.assertEqual(max_seq, manifest["cursor"])
                capsule = z.read(manifest["ledger"] + "/CAPSULE.md").decode("utf-8")
                self.assertNotIn("STALE SENTINEL", capsule)
                self.assertIn(f"Ledger cursor: {manifest['cursor']}", capsule)
                export = z.read(manifest["ledger"] + "/EVENTS.jsonl").decode("utf-8").splitlines()
                exported = [json.loads(line) for line in export]
                self.assertEqual(exported[-1]["seq"], manifest["cursor"])
                self.assertEqual(len(exported), manifest["cursor"])

            target = base / "unpacked"
            invoke(BUNDLE, "unpack", "--zip", archive, "--target", target)
            with zipfile.ZipFile(archive) as z:
                for name, record in manifest["files"].items():
                    rel = Path(*name.removeprefix("project/").split("/"))
                    actual = (target / "project" / rel).read_bytes()
                    self.assertEqual(len(actual), record["bytes"], name)
                    self.assertEqual(hashlib.sha256(actual).hexdigest(), record["sha256"], name)
            self.assertEqual((target / "project" / "evidence.txt").read_bytes(), b"source\x00\xff")
            before = (target / "project" / "evidence.txt").read_bytes()
            refused = invoke(BUNDLE, "unpack", "--zip", archive, "--target", target, expected=1)
            self.assertIn("new directory", refused.stderr)
            self.assertEqual((target / "project" / "evidence.txt").read_bytes(), before)

    def test_review_bundle_requires_explicit_opt_in(self):
        with tempfile.TemporaryDirectory(prefix="qwen-review-bundle-") as raw:
            base = Path(raw)
            project, root = init_project(base)
            evidence = project / "evidence.txt"
            evidence.write_text("version one", encoding="utf-8")
            put(project, root, node("E", "evidence", "accepted", files=["evidence.txt"]))
            evidence.write_text("version two", encoding="utf-8")
            refused_zip = base / "must-not-exist.zip"
            rejected = invoke(BUNDLE, "pack", "--project", project, "--ledger", root,
                              "--output", refused_zip, expected=1)
            self.assertIn("needs review", rejected.stderr)
            self.assertFalse(refused_zip.exists())

            allowed_zip = base / "unfinished-recovery.zip"
            result = invoke(BUNDLE, "pack", "--project", project, "--ledger", root,
                            "--output", allowed_zip, "--allow-review")
            payload = json.loads(result.stdout)
            self.assertEqual(payload["review_ids"], ["E"])
            with zipfile.ZipFile(allowed_zip) as z:
                manifest = json.loads(z.read("BUNDLE_MANIFEST.json"))
            self.assertEqual(manifest["type"], "recovery")
            self.assertEqual(manifest["byte_review"], {"E": ["changed file: evidence.txt"]})

    def test_expired_budget_cannot_be_renewed_in_place(self):
        with tempfile.TemporaryDirectory(prefix="qwen-budget-") as raw:
            base = Path(raw)
            budget_file = base / "window.json"
            expired = {"start_epoch": 100.0, "deadline_epoch": 101.0,
                       "reserve_seconds": 10.0, "elapsed_basis": "UTC wall time; includes downtime"}
            original = json.dumps(expired, indent=2) + "\n"
            budget_file.write_text(original, encoding="utf-8")
            status = json.loads(invoke(BUDGET, "status", "--file", budget_file).stdout)
            self.assertEqual(status["phase"], "expired")
            self.assertEqual(status["remaining_seconds"], 0)
            self.assertFalse(status["can_wake_model"])
            refused = invoke(BUDGET, "start", "--file", budget_file,
                             "--minutes", "10", expected=1)
            self.assertIn("Budget exists", refused.stderr)
            self.assertEqual(budget_file.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main(verbosity=2)
