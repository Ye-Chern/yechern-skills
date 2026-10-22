# Help for uncommon cases

Open the matching reference when one of these situations occurs.

- **The restored ledger comes from another version or an older local durable-task:** use the migration guidance in [references/ledger.md](references/ledger.md). Preserve the original and relocate only a complete copy whose bound files have been checked.
- **Relocation fails because evidence is missing or changed:** do not refresh stored hashes. Recover the original bytes first. The ledger guide explains the narrow `--allow-missing-history` case for unrelated archived nodes and how missing history remains recorded.
- **A ZIP is incomplete, cannot be unpacked, or still needs byte review:** follow the recovery bundle section in [references/ledger.md](references/ledger.md). Unpack to a new directory and resume from the copied ledger before continuing.
- **A user requests a bounded long window or an automatic checkpoint:** check the current host's completion-event support, then follow [references/wake-events.md](references/wake-events.md). Do not infer a model wake-up from a timer file or background process.
- **The cloud path, tools, or artifact delivery method is unclear:** follow the first-run checks and handoff notes in [references/cloud-runtime.md](references/cloud-runtime.md); report unresolved capabilities as unknown.
- **A command timed out or its result is uncertain:** inspect the output, result file, or host receipt before repeating it. For processes, verify task ownership and current identity; an old PID is not enough.
- **A ledger update saved but its view is stale:** run `resume` from the copied ledger to regenerate the view. Do not submit the same update again.
