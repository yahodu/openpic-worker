# AGENTS.md — OpenPic Worker Agent Operating Rules

This file is the entry point for autonomous agent behaviour in this repository.
Every agent — spawned by a board, running as a CI job, or invoked ad-hoc — reads
this file before taking any action.

`docs/CONVENTIONS.md` is the **authoritative engineering standard**. This file is
the short version that points at it: where the two disagree, the conventions win.
Decisions live in `docs/adr/`, and the PR + Definition of Done gate lives in
`.github/pull_request_template.md`.

## 1. Read order

1. `docs/CONVENTIONS.md` §1 — what this worker is, and the closed list of what it
   may write.
2. The card or ticket, including its `Consumes:` value for any ADR it mints.
3. The tests that define the work. They are the specification; prose is
   commentary.
4. `docs/adr/README.md` and the ADRs touching the area.
5. §11.1 of the conventions — the open contract questions. The worker's current
   behaviour there is **deliberate**; do not "correct" it.

## 2. Workspace discipline

- Work in the worktree or branch you were given. Never touch the main checkout,
  never switch another card's branch, never `git checkout main` to "start clean".
- One logical change per branch and per pull request. A branch that grows a second
  unrelated fix is returned, not reviewed.
- Never commit to `main`. Every change arrives as a PR against `main` and is
  squash-merged.
- Before you start, check whether the work already exists — an open PR or a live
  card for the same file, test or symptom. A hit means comment on it, not create a
  duplicate.

## 3. Test ownership

- TDD is mandatory: failing test first, confirm it fails for the right reason,
  minimum code to green, then refactor.
- **The Test Author owns the tests.** Implementers and agents never edit, skip,
  weaken, `xfail` or delete a test to make the suite pass.
- If the specification is wrong or self-contradictory: implement everything
  unambiguous, leave the disputed test red, and hand back a written dispute with
  evidence. Do not guess and do not silently drop the case.
- No test-environment branches in production code. No fixture-specific special
  cases. No stubs that fake the behaviour a test asserts.
- No GPU in CI. Use the fake inference backend; anything genuinely GPU-bound
  carries `@pytest.mark.gpu` and never runs on `pull_request`.

## 4. The worker's boundary

- The report route is the single publisher of match outcomes. Do not add an
  outbox client, a notification client or a domain-event producer (conventions
  §1.3, ADR-0004).
- MongoDB is written directly only through the closed field list in conventions
  §1.2. Anything else goes through `POST /api/v1/internal/worker/report`.
- The queue message is a pointer. No payload, URL, embedding or broker id in a
  domain field.
- Every tenant-scoped filter carries `tenantId`. A document whose `tenantId` or
  `eventId` disagrees with the envelope is skipped as if absent.
- No credential, embedding, object key, signed URL, token or stack trace in a log
  line, an error body or a commit.

## 5. Decisions

- An expensive-to-reverse decision needs an ADR in the same PR as the code that
  takes it (`docs/adr/template.md`, sections Context · Decision · Consequences ·
  Alternatives).
- Use the `Consumes` number the card gives you. Never derive one from the ledger
  or the highest file on disk. If it is missing or `TBD`, stop and ask.
- The record and its ledger row in `docs/adr/README.md` land together. A record
  without a row, or a row without a record, is a failed delivery.
- Never edit an accepted ADR; supersede it.
- Cite webapp records qualified: `openpic-webapp ADR-0318`.

## 6. Protected files

`AGENTS.md`, `CLAUDE.md`, `SOUL.md` and `.cursorrules` are owner-approved only.
When a write to one is refused (conventions §10.3):

1. Stop at the first refusal. Do not retry, do not route around it.
2. Publish the exact diff and `sha256sum` of the patch on the card.
3. Block with the file name and hash and wait for an explicit owner comment.
4. Apply the approved diff unchanged and prove the applied hash matches the
   published one.

A rule that is removed or weakened is the owner's own commit, never an agent's.
If a rule belongs anywhere, it belongs in `docs/CONVENTIONS.md` or an ADR, and
the protected file keeps pointing at it.

## 7. Before you open the pull request

- `uv run ruff check .` and `uv run ruff format --check .` clean.
- `uv run ty check` clean.
- `uv run pytest -q` green, coverage at or above `fail_under`.
- RED and GREEN output captured for the PR body.
- Docstrings on every public symbol; structured logs for new behaviour.
- No new dependency without a reason in the PR body; `uv.lock` updated and
  committed.
- No hard-coded tunable; config comes from the environment or the config channel.
- Env changes documented in the PR's table (`.env.example` is the template).

## 8. Merge and report

- The merge gate is conventions §10.1 (G1–G7), evaluated against the **current
  head SHA**, with its output pasted into the PR.
- On any failing condition: do not merge, do not rebase, do not `gh run rerun`, do
  not `--admin`. Comment the failing condition, merge `origin/main` in if the
  branch is behind, push, and re-evaluate on the new head.
- After the squash lands, archive the reviewed tip to `refs/prhead/<n>` and release
  the local branch (conventions §10.2), printing the four assertions.
- Report what you measured — check names and conclusions on the head, test counts,
  gate output. "Should pass" is not a result.
- Do not block on questions you can answer. When a human decision is genuinely
  needed, record the context and surface it; never guess silently.
