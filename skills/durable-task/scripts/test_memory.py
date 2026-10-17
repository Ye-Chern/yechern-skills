import json, shutil, subprocess, sys, tempfile
from contextlib import closing
from pathlib import Path
SCRIPT = Path(__file__).parent / "task_memory.py"
checks = []
def check(name, result):
    if not result:
        raise AssertionError(name)
    checks.append(name)
with tempfile.TemporaryDirectory(prefix="durable-memory-") as temp:
    project = Path(temp)
    root = project / "memory"
    (project / "contract.md").write_text("Goal: investigate. Done: observable validation. Scope: temporary data only.", encoding="utf-8")
    (project / "source.txt").write_text("observed alpha", encoding="utf-8")
    def run(command, expected=0, **args):
        argv = [sys.executable, str(SCRIPT), command, "--root", str(root)]
        for k,v in args.items():
            argv += ["--" + k.replace("_","-"), str(v)]
        output = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8")
        if output.returncode != expected:
            raise AssertionError((command, output.returncode, output.stdout, output.stderr))
        return output.stdout
    def put(node, expected=0, revision=0):
        path = project / "node.json"
        path.write_text(json.dumps(node), encoding="utf-8")
        return run("put", expected=expected, file=path, expected_revision=revision)
    def node(id, kind, status, deps=(), files=()):
        return dict(id=id, kind=kind, title=id+" content", status=status, scope="temporary source only",
                    rationale="necessary premise for test decision", depends_on=list(deps), files=list(files),
                    validation=dict(method="read exact source", result="alpha observed", limits="no semantic proof"))
    run("init", project=project, contract=project/"contract.md")
    check("initialization refuses overwrite", "ERROR" in subprocess.run(
        [sys.executable,str(SCRIPT),"init","--root",str(root),"--project",str(project),"--contract",str(project/"contract.md")],
        capture_output=True,text=True,encoding="utf-8").stderr)
    put(node("E","evidence","accepted",files=["source.txt"]))
    put(node("C","claim","accepted",deps=["E"]))
    put(node("D","decision","accepted",deps=["C"]))
    put(node("T","task","open",deps=["D"]))
    focus = project/"focus.json"
    focus.write_text(json.dumps(dict(ids=["T"],next_action="inspect next boundary",do_not_repeat=["avoid old threshold"])),encoding="utf-8")
    run("focus",file=focus)
    check("fresh independent process reconstructs focus and dependencies", all(x in run("resume") for x in ["E@1","C@1","D@1","T@1"]))
    (root/"CAPSULE.md").write_text("FAKE ALL DONE",encoding="utf-8")
    check("corrupted view is rebuilt from ledger", "FAKE ALL DONE" not in run("resume"))
    (project/"source.txt").write_text("observed beta",encoding="utf-8")
    changed = json.loads(run("audit",expected=2))
    check("file drift propagates through all descendants", set(changed["review"])=={"E","C","D","T"})
    put(node("E","evidence","accepted",files=["source.txt"]),revision=1)
    changed = json.loads(run("audit",expected=2))
    check("revalidated parent does not revive old claims", set(changed["review"])=={"C","D","T"})
    put(node("C","claim","accepted",deps=["E"]),revision=1)
    put(node("D","decision","accepted",deps=["C"]),revision=1)
    put(node("T","task","open",deps=["D"]),revision=1)
    check("explicit descendant revalidation clears review", not json.loads(run("audit"))["review"])
    # Reproduce a >6000-character focus that succeeds with an explicit budget,
    # then resume in a fresh process without that budget. Retry the actual hint.
    long_focus = project / "长前沿 input.json"
    long_focus.write_text(json.dumps(dict(ids=["T"], next_action="保留完整约束 " * 1100)), encoding="utf-8")
    before_view = (root / "CAPSULE.md").read_bytes()
    run("export", file=project / "before-focus.jsonl")
    failure = subprocess.run([sys.executable, str(SCRIPT), "focus", "--root", str(root),
                              "--file", str(long_focus)], capture_output=True, text=True, encoding="utf-8")
    run("export", file=project / "after-focus.jsonl")
    check("oversized focus leaves ledger and previous capsule unchanged",
          failure.returncode==1 and (root/"CAPSULE.md").read_bytes()==before_view
          and (project/"before-focus.jsonl").read_bytes()==(project/"after-focus.jsonl").read_bytes())
    retry_focus = json.loads(failure.stderr.split("Retry argv: ", 1)[1].strip())
    retry_result = subprocess.run(retry_focus, capture_output=True, text=True, encoding="utf-8")
    check("focus hint replays the pending focus including Unicode path with spaces",
          retry_result.returncode==0 and "保留完整约束 " * 1100 in (root/"CAPSULE.md").read_text(encoding="utf-8"))
    frozen_long_view = (root/"CAPSULE.md").read_bytes()
    check("successful explicit focus budget is reused by default resume", "保留完整约束 " * 1100 in run("resume"))
    failure = subprocess.run([sys.executable, str(SCRIPT), "resume", "--root", str(root), "--chars", "6000"],
                             capture_output=True, text=True, encoding="utf-8")
    retry_resume = json.loads(failure.stderr.split("Retry argv: ", 1)[1].strip())
    check("explicit smaller resume still refuses truncation and preserves last good capsule",
          failure.returncode==1 and (root/"CAPSULE.md").read_bytes()==frozen_long_view)
    retry_result = subprocess.run(retry_resume, capture_output=True, text=True, encoding="utf-8")
    check("resume hint reconstructs the complete long focus in a fresh process",
          retry_result.returncode==0 and "保留完整约束 " * 1100 in retry_result.stdout)
    run("focus", file=focus)
    put(node("E","evidence","retracted",files=["source.txt"]),revision=2)
    check("retraction invalidates descendants", set(json.loads(run("audit",expected=2))["review"])=={"C","D","T"})
    put(node("X","claim","accepted",deps=["E"]),expected=1)
    check("accepted claim cannot depend on retraction", "X" not in run("list"))
    put(node("E","evidence","accepted",files=["source.txt"]),expected=1,revision=1)
    check("stale writer cannot replace newer revision", json.loads(run("show",id="E"))["node"]["revision"]==3)
    put(node("E","evidence","draft",deps=["T"],files=["source.txt"]),expected=1,revision=3)
    check("cycle is rejected", json.loads(run("show",id="E"))["node"]["revision"]==3)
    put(node("Escape","evidence","accepted",files=["../outside.txt"]),expected=1)
    check("outside-project path is rejected", "Escape" not in run("list"))
    bad = node("NoMethod","evidence","accepted",files=["source.txt"]); bad.pop("validation")
    put(bad,expected=1)
    check("unsupported accepted evidence rejected", "NoMethod" not in run("list"))
    check("bounded resume fails instead of truncating", "budget" in subprocess.run(
        [sys.executable,str(SCRIPT),"resume","--root",str(root),"--chars","20"],capture_output=True,text=True,encoding="utf-8").stderr)
    run("export",file=project/"events.jsonl")
    events = [json.loads(row) for row in (project/"events.jsonl").read_text(encoding="utf-8").splitlines()]
    check("old reasons and revisions retained in export", [e["payload"]["revision"] for e in events if e["kind"]=="put" and e["payload"]["id"]=="E"]==[1,2,3])
    run("backup",file=project/"backup.sqlite3")
    check("consistent database snapshot exists", (project/"backup.sqlite3").stat().st_size>0)
    import sqlite3
    with closing(sqlite3.connect(root/"memory.sqlite3")) as con:
        try:
            con.execute("DELETE FROM events")
            raise AssertionError("append-only not enforced")
        except sqlite3.IntegrityError:
            pass
    check("database prohibits deleting history", True)
    migrated = project / "relocated"
    migrated.mkdir()
    result = run("relocate",expected=1,project=migrated)
    check("relocation rejects missing evidence", json.loads(run("show",id="E"))["node"]["revision"]==3)
    shutil.copy2(project/"source.txt",migrated/"source.txt")
    run("relocate",project=migrated)
    check("relocation binds checked target rather than old directory", str(migrated.resolve()) in run("resume"))
    run("relocate",project=project)
    put(node("Active","evidence","accepted",files=["source.txt"]))
    (project/"source.txt").unlink()
    check("missing file flagged", any("missing" in r for rs in json.loads(run("audit",expected=2))["review"].values() for r in rs))
print(json.dumps({"passed":len(checks),"checks":checks},ensure_ascii=False,indent=2))
