# Ledger and research state

## What the ledger records

The event stream records task setup, directions, episodes, role changes, timed work, submissions, reviews, retractions, conjectures, evidence, forecasts, forecast resolutions, scale choices, and finalization. Events are timestamped when written and linked with a hash chain. `state` replays the history to derive current work, research progress, and bound status.

An episode belongs to one direction. A role change updates the role shown for the current episode as soon as the event is recorded. A work interval begins at `work-start` and ends at `work-end`; open work contributes elapsed exposure at a state check. The timeline used for recent progress is accumulated active work time. Idle time outside work intervals is not included.

## Submissions and evidence levels

`observation`, `obstruction`, `method`, and `negative` are exploratory entries. An artifact may be attached, but is not required. They contribute to research progress.

Other claim kinds use an artifact and may list dependencies. `self_check`, `peer_model`, `human`, and `formal` are review labels for accepted local checks. `reproducible_computation` records an accepted computation as computed. Accepted proof-level reviews and valid dependencies determine checked claims.

Progress events and recorded bound endpoints are derived separately. Exploratory entries, accepted checked claims, and accepted `reproducible_computation` claims can inform the research-rate heuristic. Computation is marked `computed`; it does not make a claim mathematically checked or update an endpoint. Only accepted `lower` and `upper` claims at a proof review level update endpoints. Other reviewed claim types may be useful progress without changing the numeric bounds. Rejected or retracted claims are removed from current derived progress; invalid dependencies propagate to descendants. The original submissions and review events remain available for recovery. `decide` reports direction counts as `progress_events`; `state` and `decide` expose the episode work-time gap as `active_minutes_since_last_progress`.

For an infimum, a lower claim records `L <= A`, while an upper claim records `A <= U`. A pair with matching recorded values is `MATCHING_RECORDED_BOUNDS`; a pair with `L > U` is `INCONSISTENT_BOUNDS`.

Conjectures and evidence families guide prioritization but do not update bounds. Candidate relations to the ledger are `OPEN`, `MATCHES_RECORDED_BOUNDS`, `EXCLUDED_BY_RECORDED_LOWER`, or `EXCLUDED_BY_RECORDED_UPPER`. Attainment labels report `RECORDED_ATTAINED`, `RECORDED_NONATTAINED`, `CONFLICT`, or `UNKNOWN`.

## Model reliability records

The optional model registry can associate forecasts with a model row and role. A resolution can use `self_check`, `peer_model`, `human`, or `formal`; the model resolving its own forecast must use `self_check`. After a forecast has an outcome, `sync` can add it to the row; the latest resolution is used when a result is corrected. Unresolved forecasts are omitted, not counted as failures. `omega` is a bounded planning weight for candidate priority. Registry tracking can be skipped without affecting research logging, decisions, or recovery.

For interruptions, invalid dependencies, or a task already finalized, use the corresponding section in [HELP](../HELP.md).

## Starting a task from the CLI

From the installed skill directory, run the commands below with an absolute database path in your task folder. `--db` is a global option and comes before the subcommand:

```text
python -m boundforge --db /path/to/task/research.db init --problem "A=inf f(x)" --inner 50 --outer 50
python -m boundforge --db /path/to/task/research.db direction --name "Direct estimate" --why "Test a simple bound"
```

Use the direction ID returned in the `result` field of the second command:

```text
python -m boundforge --db /path/to/task/research.db episode-start --direction <direction-id> --why "Investigate the estimate"
python -m boundforge --db /path/to/task/research.db state
```

The same `result` field supplies episode, work and claim IDs for later commands. Run the relevant subcommand with `--help` for its required arguments. The runnable [quickstart](../examples/quickstart.py) shows a complete record with a bound proof, nonattainment, work closure and finalization; the [shell example](../examples/quickstart.sh) shows CLI calls. On Windows use an absolute Windows database path in place of the illustrative path above.
