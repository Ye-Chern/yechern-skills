# Design rationale

Working context should identify the current frontier; files should hold sources, versions, and conditions that may invalidate a result. A recovery entry routes the next session to relevant material. It does not replace that material.

The ledger separates evidence, claims, decisions, and tasks because they answer different questions. Stable IDs connect only the premises a result actually needs. File hashes and dependency revisions make some changes visible, while domain review determines whether the result still holds. A short state file remains preferable when it can preserve the needed context with less work.

The ledger uses SQLite events as its history and regenerates `CAPSULE.md` as a view. A transaction protects the database write; it does not make other files or delivered artifacts part of the same transaction. Keep source results and deliverables separately available when recovery depends on them.

These are engineering choices, not measured claims that a particular record format improves model accuracy or permits unlimited work. Assess the value and management cost against the actual task.

## References

- [SQLite atomic commit](https://www.sqlite.org/atomiccommit.html) describes the database transaction boundary relevant to the ledger.
- [dsh-ops, pinned revision](https://github.com/T-Auto/dsh-ops/tree/c4d829a012d8e9959f36150794edc354e49452ee) informed the distinction between external results, result validation and observed process state. This package does not include its source code or executor.
