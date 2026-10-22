# Optional checkpoint notifications

Use this only when a user-defined work window needs a later checkpoint and the current host can return a real background-task completion event. A budget or timer file alone cannot wake the model. If the host cannot provide a completion event, save the state and recovery files for the next user message.

## Start one checkpoint

Save the current project state first. If the user gave a total window, create its budget once:

```text
python3 <skill>/scripts/work_budget.py start --file <project>/window.json --minutes <user-selected-minutes> --reserve-minutes <delivery-reserve>
```

Use `status` to check the same budget after recovery. Do not reset its deadline. Choose an interval that fits the task and the time left before the delivery reserve, then arm a new record:

```text
python3 <skill>/scripts/checkpoint_timer.py arm --budget <project>/window.json --record <project>/jobs/tick-001.json --interval-seconds <chosen-interval>
```

Give one supported background watcher the record path, timer ID, and the original task ID. The watcher waits on that same record with `checkpoint_timer.py wait --record ... --max-seconds ...`; if it reports `pending`, it continues waiting on the same record. Each foreground wait slice must fit the host's actual tool timeout and the script's 240-second maximum. Do not arm another timer to extend a pending checkpoint.

Record the real host job or thread ID in the project when the host returns it. The timer's placeholder text is not a job ID. The watcher only reports the timer result and stops; it does not do task work, change the budget, or create additional watchers.

## Handle a return

Check that the receipt matches the timer and task IDs, then inspect the result file, budget, and project state. A timer result proves only that the time was observed. It does not prove the host delivered a notification or that the task progressed.

If work remains and the old watcher has ended, save a fresh checkpoint and arm one new record using the same deadline. If the task is complete, stopped, or at its delivery reserve, cancel the timer and stop the watcher if the host supports that action. Record whether stopping was confirmed. Ignore duplicate or late receipts after checking them against the task record.

If the watcher or receipt fails, stop automatic rearming for that window. Save the recovery state and continue only when a user message or another real host event arrives. Never extend a window without the user's new instruction.
