# Uploading this skill to Qoder Cloud

Upload the skill ZIP to Qoder Cloud and send a task prompt with the actual goal. For an existing task, include its latest recovery ZIP. Do not provide a Windows path as though it were available in the cloud.

Suggested prompt:

> Please unpack the skill ZIP and follow `durable-task-qwen-cloud/SKILL.md` for this task. If I attached a recovery ZIP, unpack it to a new directory, inspect the current recovery entry and relevant evidence, then continue from the stated next action. The task is: [describe the task].
>
> [Optional: This work has a total time window of ___; reserve ___ for delivery. If a checkpoint interval would help, use ___.]

The package includes the skill, standard-library scripts, and synthetic tests. A short task may use the existing project entry or one state file. Use a ledger or timer only when the task needs it. When the task needs cross-session recovery, prepare a recovery ZIP and confirm delivery through the actual attachment tool available in the cloud session.

To check the local script behavior, run `python3 -m unittest discover -s <skill>/tests -v`. This does not validate cloud session lifetime, model recovery quality, or research conclusions.
