# Cloud runtime details

Check a tool, path, dependency, or delivery method when the task relies on it. Record only what affects this task; mark untested capabilities unknown. Paths and tool names must come from the current session.

Keep the skill ZIP separate from task recovery files. A ZIP written to temporary cloud storage is not delivered until the current session confirms an attachment or other user-accessible handoff.

## User-defined time windows

When the user gives a total duration, create one budget file and reuse it after recovery:

```text
python3 <skill>/scripts/work_budget.py start --file <project>/window.json --minutes <user-selected-minutes> --reserve-minutes <delivery-reserve>
python3 <skill>/scripts/work_budget.py status --file <project>/window.json
```

The budget uses UTC wall time and includes disconnection time. A restored window keeps its original deadline. A new window requires the user's instruction; keep the earlier record as history. When the budget reaches its delivery reserve, finish current validation and handoff rather than opening new searches.

This script records time only. It does not register a model event or keep the session alive. Use a checkpoint watcher only when requested or needed for continuation and the current host confirms a real completion event; see [wake-events.md](wake-events.md).

## Long calculations

Break a calculation into units that fit the actual tool limits. Keep each unit's purpose, input range, generator version, raw output, independent check, and last committed result in the task's existing state or ledger. Commit a unit only after its check passes. On recovery, verify coverage, gaps, and duplicates; changed inputs or generators may invalidate earlier units.

Write new or fixed outputs to the recovered copy. Check critical reproduction commands there before delivery so they cannot accidentally write into the original project.

## Processes and uncertain results

Process state and host notifications are separate observations. A file marker proves that a file can be read; a process ID or ETA may be stale. Across environments, treat an old process as unknown. After timeout or disconnection, inspect the result before retrying; repeat only when safe.

This package does not configure external schedulers or validate Cloud Agents API account access, billing, or lifecycle behavior. Test any such integration in its actual environment before relying on it.
