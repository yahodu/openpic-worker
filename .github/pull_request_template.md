<!--
Title must be a conventional commit, e.g.:
  feat(worker): OP-12 drain the queue on SIGTERM
  ci: pin actions to commit SHAs
The squash-merge on main uses this title as the commit message.
-->

## What

<!-- One paragraph: what changes, in the reader's terms. -->

## Why

<!-- The problem this solves. Link the ticket (OP-xxx) or the issue. -->

## How it was verified

<!-- Not "tests pass" — what you actually ran, and what it proved. -->

- [ ] `uv run ruff check .`
- [ ] `uv run mypy .`
- [ ] `uv run pytest`
- [ ] Exercised against a real GPU host (say where, or write "CPU-only: device layer mocked")

## GPU / runtime impact

<!--
Delete this section for PRs that cannot affect the worker at runtime.
Worth stating explicitly: peak VRAM, batch size, expected wall-clock per job,
which backend (Modal / vast.ai) was used, and any driver/CUDA constraints.
-->

- Backend affected:
- Peak VRAM observed:
- Throughput change:

## 🔐 Environment Variables

<!--
Required when .env.example changes — the `env-docs` check reads this section.
Use the table for added/removed/modified variables. Write "No env changes"
if the template did not change.
-->

| Change | Variable | Notes |
| ------ | -------- | ----- |
|        |          |       |

## Checklist

- [ ] No secrets, tokens, or connection strings in code, logs, or test fixtures
- [ ] New/changed dependencies are pinned in `uv.lock`
- [ ] Migration/rollback considered (a deploy that cannot be undone is a decision, not a detail)
- [ ] Docs updated where behaviour is now different
