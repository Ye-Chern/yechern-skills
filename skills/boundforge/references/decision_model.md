# Dual-loop decision model

BoundForge estimates how often useful research entries arise during active work. It uses the estimate to compare an episode with alternative directions and to summarize the overall portfolio.

## Work-time observations

For episode `j`, let `T_j` be recorded active work minutes and `N_j` its currently usable progress events. Events may include useful exploratory entries, accepted checked results, and accepted reproducible computations. Computations inform planning without changing mathematical bounds. They are not all the same kind of achievement: a lemma, a useful obstruction, a method note, and a negative result that rules out an approach can each help research in different ways. Numeric lower and upper bound changes are also retained separately. The output field is named `progress_events`; each episode reports its gap since the latest useful finding as `active_minutes_since_last_progress`.

Open work counts through the time of a state check. Submissions are located on the accumulated work-time axis using their original timestamps. Results at the start of that axis (`0` minutes) are included in the recent window. The inner loop uses the recent 60 active minutes of the current episode; the outer loop pools each direction's episodes. This makes it possible to distinguish old progress followed by a dry period from a recent result.

## Rate estimate

The prototype uses a weak Gamma prior and approximate Poisson event model:

`r ~ Gamma(shape=1.2, rate=30 minutes)`

`N | r,T ~ Poisson(r*T)`

so the approximate updated rate is `Gamma(shape=1.2+N, rate=30+T)`. The rate unit is useful progress events per active work minute. The estimator uses the recorded events and active exposure as its observations.

## Inner loop

The controller compares the current episode's recent rate with rates for other directions. The prototype discounts alternative rates by an assumed reorientation cost and uses a margin before recommending `DIAGNOSE_AND_PIVOT`. The switching threshold is shaped by `inner_effort`; a larger value generally asks for stronger evidence before leaving the current episode. If no alternative clearly dominates, the controller may suggest `ROTATE_ROLE_OR_METHOD` or `CONTINUE`.

These are soft preferences. A promising proof idea, a newly found obstruction, or an obvious methodological flaw can justify an action that differs from the suggestion. The effort value does not prescribe how many actions to try.

With no earlier matching-bounds, budget or global-pause outcome, the prototype returns `COLLECT_BASELINE` while an episode has under five recorded active minutes. This is an advisory default for sparse history: it does not prevent closing an episode, changing direction, or finishing a proof immediately. There is no requirement to wait out five minutes before acting on a concrete finding.

The rate estimate also depends on how findings are split into entries. Repeating an observation in a later episode can be useful context, but does not become independent mathematical evidence. Compare the substance of the results and use a broadly consistent recording granularity; do not manufacture entries to optimize the suggestion.

## Outer loop

For each registered direction, the controller estimates the chance that its rate clears a heuristic minimum useful rate. It then compares the best direction with a threshold influenced by `outer_effort`. This provides a consistent prompt to consider continuing, adding a direction, or pausing the search.

The current prototype uses:

`r_min(e_outer) = 0.045 - 0.035*(e_outer/100)`

`tau_outer(e_outer) = 0.91 - 0.38*(e_outer/100)`

A recorded time ceiling produces `SUSPEND_BUDGET` when exposure reaches the configured limit.
