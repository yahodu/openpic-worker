<!--
Title must be a conventional commit, e.g.:
  feat(worker): OP-12 drain the queue on SIGTERM
  ci: pin actions to commit SHAs
`main` enforces linear history, so a squash merge uses this title as the commit
message. The ticket is optional; the type is not. See CONTRIBUTING.md §4.
-->

## What

<!-- One paragraph: what changes, in the reader's terms. -->

## Why

<!-- The problem this solves. Link the ticket (OP-xxx) or the issue. -->

## How it was verified

<!--
Not "tests pass" — what you actually ran, and what it proved. A docs-only PR says
so here; conventions §2 allows skipping TDD when no production code ships.
-->

- [ ] `uv run ruff check .` and `uv run ruff format --check .`
- [ ] `uv run pytest -q` (RED and GREEN pasted below for a behaviour change)
- [ ] Exercised against a real GPU host (say where, or write "CPU-only: device layer mocked")

<details>
<summary>RED — the test that demanded this change</summary>

```
```

</details>

<details>
<summary>GREEN — the same test after the change</summary>

```
```

</details>

## Contract and decisions

- Contract section:
- ADR: none / ADR-NNNN (ledger row lands in this PR)
- §11.1 open question touched: none / Q1 / Q2a / Q2b

## GPU / runtime impact

<!--
Delete for PRs that cannot affect the worker at runtime. Worth stating: peak
VRAM, batch size, wall-clock per job, backend used, driver/CUDA constraints.
-->

- Backend affected:
- Peak VRAM observed:
- Throughput change:

## 🔐 Environment Variables

<!--
Required when .env.example changes — the `env-docs` check greps for this heading.
Write "No env changes" when the template did not change.
-->

| Change | Variable | Notes |
| ------ | -------- | ----- |
|        |          |       |

## Deployment notes

<!-- Delete when there are none. Note ordering requirements with the control plane. -->

## Definition of Done

Every box must be honest (conventions §10).

- [ ] Tests were written first and are green (RED + GREEN above)
- [ ] `uv run pytest` passes; coverage is at or above the configured threshold
- [ ] `uv run ruff check .` and `uv run ruff format --check .` are clean
- [ ] `uv run ty check` is clean
- [ ] Docstrings on every public symbol and contract module
- [ ] Structured logs added for the new behaviour, at the right level
- [ ] Pydantic models and `build_x` factories exist, and the factories parse
- [ ] The relevant contract section and ADR are cited in the module docstring
- [ ] No hard-coded tunable: every knob is env or the config channel
- [ ] No new dependency without a stated reason; `pip-audit` clean
- [ ] ADR added in `docs/adr/` for any new decision
- [ ] The ADR number is the card's `Consumes` value, with no same-lane sibling in flight
- [ ] The ADR record carries its `docs/adr/README.md` ledger row in this same PR
- [ ] The merge gate printed PASS on this exact head SHA, pasted below
- [ ] Post-merge: head archived to `refs/prhead/<n>`, local branch released

```
# G1–G7 output for this head SHA goes here
```

## Checklist

- [ ] No secrets, tokens, embeddings, object keys or signed URLs in code, logs, or fixtures
- [ ] New/changed dependencies are pinned in `uv.lock`
- [ ] Migration/rollback considered (a deploy that cannot be undone is a decision, not a detail)
- [ ] Docs updated where behaviour is now different
- [ ] One logical change: no unrelated refactor or formatting sweep here
