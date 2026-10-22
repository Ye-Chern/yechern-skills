# Notice

This package supports recovery of work in Qoder Cloud. It does not change platform time limits, guarantee that a session or process remains alive, or establish that a research result is correct.

- A file or process marker is an observation. Only an actual host completion event can trigger a continuation, and the event still needs to be checked against the task and its recorded ID.
- Ledger hashes cover file bytes and declared dependencies. Bundle verification checks packaged bytes; neither check source authenticity, semantic correctness, or undeclared relationships.
- A task ledger and recovery ZIP contain project material. Include only files needed for recovery, protect private data, and never include credentials in a skill package.
- Logged commands do not execute themselves. Do not treat a recorded command, timer, audit result, or `done` label as proof of domain completion.
- Preserve the user's authorization for agents, external messages, uploads, and other side effects. This skill does not create permission.

Tell the user which files were actually generated and whether the environment confirmed delivery. Do not claim an upload or a download link without an observed result.
