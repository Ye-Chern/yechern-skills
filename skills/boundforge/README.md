# BoundForge v2.1-alpha

A local mathematics research workspace for sustained exploration, direction comparison, and recovery.

The inner loop helps choose whether to continue an episode, change method, or pivot. The outer loop compares directions across episodes. `inner_effort` and `outer_effort` (0–100) shape these preferences; the research determines the actions and time needed.

## Start

Python 3.10+ with the standard library is enough. From this folder:

```bash
python examples/quickstart.py
```

For your own research:

1. Initialize the problem and effort preferences, add a direction, and start an episode.
2. Record work with `work-start` and `work-end`. Submit useful observations, methods, obstructions, and negative results; exploratory entries may omit artifacts.
3. Attach arguments to bounds and lemmas. After actually checking the work, record `self_check`; choose other review methods when useful.
4. Recover with `state` and consult `decide`. Use the mathematical findings and new ideas to continue, change method, or pivot.
5. Close work for a temporary pause. Use `finalize` when the task is finished.

The model registry is optional; `--model-index` selects a row when one is provided. Use `conjecture`, `evidence`, and `candidates` to track candidate values and investigation priorities.

For command options, run `python -m boundforge --help`. See the [research skill](SKILL.md) and [ledger reference](references/ledger.md) for the usual workflow and state fields.

## On demand

- Exceptions, invalid dependencies, interruptions, and less common operations: [HELP.md](HELP.md).
- Project-wide scope and general notices: [NOTICE.md](NOTICE.md).
