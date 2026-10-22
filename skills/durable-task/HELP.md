# Help for uncommon cases

Use this page only when the matching situation occurs.

- **The current notes no longer support reliable recovery:** use the ledger format, revision rules, and recovery commands in [references/protocol.md](references/protocol.md). Keep the original project and evidence; do not upgrade an incompatible ledger in place.
- **A project or ledger is moving to another directory or environment:** follow the handoff and relocation guidance in [references/handoff.md](references/handoff.md) and the migration section in [references/protocol.md](references/protocol.md). Verify the copied bytes before resuming.
- **Relocation reports missing historical evidence:** use `--allow-missing-history` only for unrelated retracted or superseded records after confirming protected references. Record the missing IDs and paths; missing evidence cannot be re-accepted without recovering and checking the source.
- **A copied file changes hash after Git checkout on Windows:** compare the actual bytes and inspect line-ending conversion. Do not refresh an old hash just to clear an audit warning. The protocol's Git note describes a narrowly scoped repair.
- **A ledger update committed but the capsule was not written:** run `resume` to rebuild the view; do not repeat the mutation.
- **A long action times out or a process is still running:** check its result, ownership, and current identity before retrying or stopping it. See [references/handoff.md](references/handoff.md).
- **You are improving this skill after a real failure:** use [references/evolution.md](references/evolution.md), preserve a rollback path, and replay the failure case.
