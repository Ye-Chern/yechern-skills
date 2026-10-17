#!/usr/bin/env python3
"""Portable project ZIP with verified file inventory. No network or model calls."""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import zipfile

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
MANIFEST = "BUNDLE_MANIFEST.json"
MEMORY = Path(__file__).with_name("task_memory.py")

def sha(data):
    return hashlib.sha256(data).hexdigest()

def safe_name(name):
    p = PurePosixPath(name)
    if not name or "\\" in name or ":" in name or p.is_absolute() or ".." in p.parts or str(p) != name:
        raise ValueError("Unsafe archive path: " + name)
    return p

def verify(archive):
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        if len(set(n.casefold() for n in names)) != len(names):
            raise ValueError("Duplicate/case-colliding archive paths")
        for n in names:
            safe_name(n)
            info = z.getinfo(n)
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Symlink in archive: " + n)
        manifest = json.loads(z.read(MANIFEST))
        if manifest.get("format") != "qwen-task-bundle-v1":
            raise ValueError("Unsupported bundle format")
        files = manifest["files"]
        if manifest.get("project") != "project" or not manifest.get("ledger", "").startswith("project/"):
            raise ValueError("Invalid bundle layout")
        safe_name(manifest["ledger"])
        if manifest["ledger"] + "/memory.sqlite3" not in files:
            raise ValueError("Bundle lacks declared ledger")
        if set(names) != set(files) | {MANIFEST}:
            raise ValueError("Inventory does not match archive entries")
        for n, expected in files.items():
            data = z.read(n)
            if len(data) != expected["bytes"] or sha(data) != expected["sha256"]:
                raise ValueError("Bundle byte mismatch: " + n)
        return manifest

def memory(command, ledger, **kwargs):
    argv = [sys.executable, str(MEMORY), command, "--root", str(ledger)]
    for k, v in kwargs.items():
        argv += ["--" + k.replace("_", "-"), str(v)]
    r = subprocess.run(argv, capture_output=True, encoding="utf-8")
    if r.returncode not in ({0, 2} if command == "audit" else {0}):
        raise ValueError("Memory " + command + " failed: " + r.stderr)
    return r

def pack(project, ledger, output, allow_review):
    project, ledger, output = project.resolve(), ledger.resolve(), output.resolve()
    if not project.is_dir() or not ledger.is_relative_to(project):
        raise ValueError("Project must exist and ledger must be inside it")
    if output.is_relative_to(project) or output.exists():
        raise ValueError("Choose a fresh output ZIP outside project (avoid self-inclusion)")
    if not (ledger / "memory.sqlite3").is_file() or (ledger / "memory.sqlite3").stat().st_size == 0:
        raise ValueError("Explicit ledger is missing or empty; do not auto-select another")
    # Caller pauses writers. Copy exact bytes; backup DB consistently; validate copied project,
    # never the original. Regenerate stale views only in this isolated copy.
    with tempfile.TemporaryDirectory(prefix="qwen-bundle-") as tmp:
        stage = Path(tmp) / "project"
        stage.mkdir()
        rel = ledger.relative_to(project)
        source_files = []
        for f in sorted(project.rglob("*")):
            if f.is_symlink():
                raise ValueError("Symlink in project; resolve explicitly before packaging: " + str(f))
            if not f.is_file() or "__pycache__" in f.parts or f.suffix == ".pyc" or f.name.startswith(".memory-"):
                continue
            if f.name.endswith(("-journal", "-wal", "-shm")):
                continue
            target = stage / f.relative_to(project)
            target.parent.mkdir(parents=True, exist_ok=True)
            if f == ledger / "memory.sqlite3":
                with closing(sqlite3.connect(f.as_uri() + "?mode=ro", uri=True)) as src:
                    dst = sqlite3.connect(target)
                    try:
                        src.backup(dst)
                    finally:
                        dst.close()
            else:
                data = f.read_bytes()
                target.write_bytes(data)
                source_files.append((f, sha(data)))
        copied_ledger = stage / rel
        memory("resume", copied_ledger)
        memory("export", copied_ledger, file=copied_ledger / "EVENTS.jsonl")
        checked = memory("audit", copied_ledger)
        report = json.loads(checked.stdout)
        if checked.returncode == 2 and not allow_review:
            raise ValueError("Copied project needs review; fix or use --allow-review for an explicitly unfinished recovery package")
        db = sqlite3.connect(copied_ledger / "memory.sqlite3")
        try:
            cursor = db.execute("SELECT coalesce(max(seq),0) FROM events").fetchone()[0]
            integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            db.close()
        if integrity != "ok":
            raise ValueError("SQLite integrity failure")
        # Do not publish a file copy if its source changed while we were taking it.
        if any(not f.is_file() or sha(f.read_bytes()) != h for f, h in source_files):
            raise ValueError("Source files changed during packaging; pause writers and retry")
        source_db = sqlite3.connect((ledger / "memory.sqlite3").as_uri() + "?mode=ro", uri=True)
        try:
            if source_db.execute("SELECT coalesce(max(seq),0) FROM events").fetchone()[0] != cursor:
                raise ValueError("Ledger changed during packaging; pause writers and retry")
        finally:
            source_db.close()
        records = {}
        for f in sorted(stage.rglob("*")):
            if f.is_file():
                data = f.read_bytes()
                n = "project/" + f.relative_to(stage).as_posix()
                safe_name(n)
                records[n] = {"bytes": len(data), "sha256": sha(data)}
        manifest = {"format": "qwen-task-bundle-v1", "type": "recovery",
                    "project": "project", "ledger": "project/" + rel.as_posix(),
                    "cursor": cursor, "byte_review": report["review"],
                    "semantic_validation": "Not performed by bundle tool",
                    "publication": "local ZIP only; use the actual Qoder artifact tool separately",
                    "files": records}
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(output.name + ".tmp")
        if temporary.exists():
            raise ValueError("Temporary output already exists")
        try:
            with zipfile.ZipFile(temporary, "x", zipfile.ZIP_DEFLATED) as z:
                for n in records:
                    z.write(stage / PurePosixPath(n).relative_to("project"), n)
                z.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))
            verify(temporary)
            # Exclusive creation avoids replacing a user artifact even if a concurrent writer appeared.
            with output.open("xb") as dest, temporary.open("rb") as src:
                shutil.copyfileobj(src, dest)
        finally:
            if temporary.exists():
                temporary.unlink()
    print(json.dumps({"zip": str(output), "files": len(records), "cursor": cursor,
                      "review_ids": list(report["review"]), "artifact_uploaded": False}, ensure_ascii=False))

def unpack(archive, target):
    manifest = verify(archive)
    target = target.resolve()
    if target.exists():
        raise ValueError("Unpack target must be a new directory; never overwrite user files")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="qwen-unpack-", dir=target.parent) as tmp:
        stage = Path(tmp) / "payload"
        stage.mkdir()
        with zipfile.ZipFile(archive) as z:
            for n in z.namelist():
                dest = stage.joinpath(*safe_name(n).parts)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(z.read(n))
        # Same parent/filesystem; all content verified before publishing the new directory.
        if target.exists():
            raise ValueError("Target appeared while unpacking; refusing overwrite")
        os.rename(stage, target)
    print(json.dumps({"project": str(target / manifest["project"]),
                      "ledger": str(target / manifest["ledger"]), "cursor": manifest["cursor"],
                      "next": "Run task_memory.py resume at this copied ledger, then read CONTRACT.md and evidence IDs"}, ensure_ascii=False))

def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("pack")
    a.add_argument("--project", type=Path, required=True)
    a.add_argument("--ledger", type=Path, required=True)
    a.add_argument("--output", type=Path, required=True)
    a.add_argument("--allow-review", action="store_true")
    a = sub.add_parser("verify")
    a.add_argument("--zip", type=Path, required=True)
    a = sub.add_parser("unpack")
    a.add_argument("--zip", type=Path, required=True)
    a.add_argument("--target", type=Path, required=True)
    a = p.parse_args()
    if a.command == "pack":
        pack(a.project, a.ledger, a.output, a.allow_review)
    elif a.command == "verify":
        m = verify(a.zip)
        print(json.dumps({"verified_files": len(m["files"]), "cursor": m["cursor"],
                          "review_ids": list(m["byte_review"]), "semantics_checked": False}, ensure_ascii=False))
    else:
        unpack(a.zip, a.target)

if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error, zipfile.BadZipFile) as e:
        print("ERROR: " + str(e), file=sys.stderr)
        sys.exit(1)
