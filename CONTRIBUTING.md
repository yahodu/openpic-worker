# Contributing to OpenPic Worker

Thank you for wanting to improve the OpenPic worker. This guide covers how to
propose a change, how the code is written, how it is reviewed, and the terms your
contribution is accepted under. It is written for both people and autonomous
agents — the rules are the same for both, and where an agent differs, the
difference is stated.

The repository runs **GitHub flow**: `main` is the only long-lived branch, every
change arrives as a short-lived branch and a pull request, and a squash merge to
`main` is the only way code lands. `main` is what deploys.

Read these first:

1. [`LICENSE`](LICENSE) — the project is proprietary; your contribution terms are
   in section 6.
2. [`docs/CONVENTIONS.md`](docs/CONVENTIONS.md) — the **authoritative** engineering
   standard. If this guide and the conventions disagree, the conventions win.
3. [`AGENTS.md`](AGENTS.md) — operating rules for autonomous agents.
4. [`docs/adr/`](docs/adr/README.md) — why the expensive-to-reverse decisions are
   what they are.
5. [`.github/CI-CD.md`](.github/CI-CD.md) — what CI enforces and what deploying
   requires.

---

## 1. Who can contribute

Contributions are accepted from **contributors the owner has added to the
repository**. If you are not one yet, open an issue that describes the change you
want to make and the problem it solves, and the owner will decide whether to add
you.

Unsolicited pull requests from outside contributors may be closed without a
review. This is not hostility — it is what keeps the contribution terms and the
licensing of the project coherent.

## 2. Before you write code

1. **Find the requirement.** Every change traces to a ticket (`OP-<number>`), an
   issue, or an explicit instruction. No ticket, no branch.
2. **Read the owned document.** A claim/lease change reads
   [`docs/API Contract.md`](docs/API%20Contract.md) §10.4 and §18.2; a storage or
   thumbnail change reads
   [`docs/Upload flow.md`](docs/Upload%20flow.md) and
   [`docs/Thumbnail Generation and Cache flow.md`](docs/Thumbnail%20Generation%20and%20Cache%20flow.md).
   The contract is normative: if the code and the contract disagree, stop and ask
   which one is wrong.
3. **Search the ADRs** for the area. A decision that looks odd usually has a
   record explaining the alternative that was rejected.
4. **Check §11.1 of the conventions first.** It lists the open contract questions
   (domain events, the `match_incremental` projection, the incremental watermark)
   with the behaviour the worker must keep **until** each is resolved. Do not
   "fix" one of these in a worker PR.
5. **Check the board for a duplicate.** Someone may already be fixing it.

## 3. Local setup

The Python tree is being rewritten. Until `pyproject.toml` and `uv.lock` land,
the Python CI jobs detect their absence and skip by design (see
[`.github/CI-CD.md`](.github/CI-CD.md)); `pr-checks.yml`, CodeQL and the secret
scan already run. Once the tree exists:

```bash
uv sync --frozen                    # never re-lock locally to make CI pass
cp .env.example .env                # fill in what you need; placeholders only
docker compose up -d                # mongo:7 replica set, redis, minio
uv run python -m openpic_worker.admin.index_check
```

Run the checks you will be judged on before you push:

```bash
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest -q -m "not gpu and not e2e"     # the fast default, under 60 s
uv run pytest -q -m integration               # needs docker compose up -d
```

`uv run pytest -q` on its own is the default selection and also excludes `gpu`
and `e2e`. Nothing in CI has a CUDA device.

## 4. Branch, commit and pull request

| Thing        | Rule                                                                                        |
| ------------ | ------------------------------------------------------------------------------------------- |
| Branch       | `OP-<number>-<feature\|bug\|task>-<lowercase-slug>`, cut from `main`                        |
| Unticketed   | `<type>/<lowercase-slug>` with `type` in `feature,bug,fix,chore,ci,docs,build,test,refactor,perf` |
| Commit       | Conventional Commits: `type(scope): OP-123 short description`                                |
| Types        | `feat`, `fix`, `chore`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `revert`  |
| Pull request | Title `type(scope): OP-123 description`, filled in from the PR template                      |
| Merge        | Squash merge into `main`; the branch is deleted on merge                                     |

The PR title check is not cosmetic: `main` enforces linear history, so a
squash-merged PR's title **becomes** the commit message on `main`. The ticket is
optional in the title (`ci: pin actions to commit SHAs` is valid); the type is
not.

Work on **one logical change per pull request**. A pull request that mixes a fix,
a refactor and a formatting sweep cannot be reviewed, and will be returned.

The PR template asks for the RED and GREEN test output, the DoD checklist, the
contract section you implemented, GPU/runtime impact, deployment notes and any
environment-variable change. Fill it in honestly — the merge gate checks the head
you actually tested.

## 5. Test-driven development is mandatory

No production code without a failing test that demands it.

1. **RED** — write the test, run it, and confirm it fails **for the right
   reason** (an assertion failure, not an import error).
2. **GREEN** — write the smallest code that passes it.
3. **REFACTOR** — clean up while the suite stays green.
4. Paste both outputs into the pull request. A pull request without them is not
   reviewable.

Rules that are not negotiable:

- **Never edit, skip, weaken, `xfail` or delete a test to make the suite pass.** A
  green suite achieved by rewriting the test is a failed delivery. If a test looks
  wrong, stop and raise a dispute with evidence; the Test Author owns the test.
- **No test-environment branches.** `if os.getenv("PYTEST_CURRENT_TEST")` in
  production code is a rejection. Tests substitute doubles (fake inference
  backend, `respx`, real services in containers) instead.
- **No fixture-specific special cases.** The code must work for the general
  behaviour the test exemplifies.
- **Every bug fix starts with a regression test** that fails on the current trunk.
- A change that ships no production code (documentation, runbook, ADR only) is the
  only kind that may skip the law, and it must say so in the PR or card.

### Test pyramid

| Layer       | Tooling                                                                 | Use for                                                                 |
| ----------- | ----------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| Unit        | `pytest`, `pytest-asyncio`, `pytest-mock`, `polyfactory`                 | Builders, mappers, validators, redaction, threshold maths, stage wiring  |
| Integration | `pytest` + real `mongod` replica set, real Redis, real MinIO, `respx`    | Claim/lease races, transactions, idempotency, queue semantics, signed requests |
| E2E         | `pytest` against docker-compose with a **fake** inference backend        | enqueue → claim → process → report → observable state                    |

- Integration runs against a **real replica set**, because multi-document
  transactions and `findOneAndUpdate` semantics are the thing under test. A Mongo
  mock proves nothing here.
- **No test touches the network.** `respx.mock(assert_all_mocked=True)` is
  autouse where a test can egress, and a session fixture makes any non-loopback
  socket connect raise. An unhandled request is a bug, not a warning.
- **No GPU in CI.** Everything exercises the inference port through a fake
  backend. Genuine GPU tests carry `@pytest.mark.gpu` and run only through
  `workflow_dispatch` on a self-hosted runner — never on `pull_request`.
- **Determinism.** No `sleep` for synchronisation, no wall-clock assertions, no
  ordering assumptions the contract does not state. Time comes from an injected
  `Clock`; randomness from an injected `Random`.
- **Coverage** floor is `fail_under` in `pyproject.toml` (90). A shortfall is
  fixed with tests, never by lowering the threshold.

## 6. Coding conventions

`docs/CONVENTIONS.md` is normative. The rules that come up in almost every review:

| Topic               | Rule                                                                                                                  |
| ------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Types               | Fully annotated; `ty check` clean; no `# type: ignore` instead of a fix                                                |
| Contracts           | Every boundary has a Pydantic model: queue envelope, work item, API request/response, third-party payload, config       |
| Model strictness    | Write models `extra="forbid"`, `frozen=True`; read models forward-compatible (`extra="ignore"`)                         |
| Tenancy             | Every tenant-scoped filter carries `tenantId` structurally; a missing one blocks the review                            |
| Secrets             | `SecretStr`, never in `repr`, never logged; compared with `hmac.compare_digest`, never `==`                            |
| Never-log fields    | No embedding, object key, signed URL, provider token, stack trace or Mongo query text in a log line or API body         |
| Logging             | Through the logging port only — never `print`, never a vendor SDK directly                                              |
| Async               | Every I/O call has a timeout; no blocking work on the loop; bounded concurrency; `TaskGroup` for structured concurrency |
| Errors              | No bare `except`; map into the contract's error taxonomy (§8.1); never swallow `CancelledError`                         |
| Config              | Environment for deploy config, the config channel for runtime tunables — never a hard-coded knob                        |
| Files and names     | Verb–noun functions (`claim_item`, `report_outcome`); no `Manager`/`Helper`/`Util` classes; no vendor names in domain vocabulary |
| Dependencies        | Pinned in `uv.lock`; no `*`, no git URL without a commit SHA; a new runtime dependency needs a stated reason in the PR  |
| Lint and format     | `ruff` for both, line length 100, configured in `pyproject.toml`                                                        |

## 7. Architecture decisions

Any decision that is expensive to reverse needs an ADR in `docs/adr/`:

- One file per decision, named `ADR-NNNN-<slug>.md`, sections **Context ·
  Decision · Consequences · Alternatives** (start from
  [`docs/adr/template.md`](docs/adr/template.md)).
- Numbers are reserved in advance from the worker's `0001`–`0999` range; never
  derive a number from the ledger, the `Next free` cell or the highest file on
  disk. Take the `Consumes` value you were given in the card (or ask the owner)
  before you mint a record.
- The record and its row in [`docs/adr/README.md`](docs/adr/README.md) land **in
  the same pull request**. A record without a row, or a row without a record,
  fails the Definition of Done.
- Never edit an accepted ADR. Supersede it with a new one and mark the old
  `Superseded by ADR-NNNN`.
- Cite the webapp's records qualified — `openpic-webapp ADR-0318` — because both
  repositories have a `0318`.
- `tests/unit/test_adr_numbering.py` is the backstop; run it before you push.

## 8. Review and merge gates

A pull request is mergeable only when all of these hold:

1. Branch name and PR title match the patterns in section 4.
2. CI is green on the **head commit**: lint & format, type check, tests,
   runtime dependency audit, secret scan, CodeQL, dependency review.
3. The PR body carries the RED and GREEN evidence and every DoD box is honest.
4. Review has approved the change.
5. The merge gate (conventions §10.1, conditions **G1–G7**) printed PASS on the
   exact head SHA, and that output is in the PR.
6. After the squash lands, the head is archived to `refs/prhead/<n>` and the local
   branch released (conventions §10.2).

The gate is deliberately literal. It will not accept a green run from an earlier
head: if `uv.lock`, `pyproject.toml`, `Dockerfile` or `.github/workflows/ci.yml`
changed on `main` after the audit finished, the audit is stale and the PR must
take a fresh run. Do not force-push over a review, do not merge with a red or
pending check, and do not re-run a failed check to make it green — fix the cause.

## 9. Working as an agent

Autonomous agents follow the same rules plus these:

1. **Orient before acting.** Read `AGENTS.md`, the card or ticket, and the tests
   that define the work. The tests are the specification; prose is commentary.
2. **Stay in your workspace.** Work in the worktree or branch you were given;
   never touch the main checkout or another card's branch.
3. **Never modify tests, fixtures, mocks or test utilities.** If the specification
   is wrong or self-contradictory, implement everything unambiguous, leave that
   test red, and hand back a written dispute with evidence.
4. **No test-environment branches, no hard-coded fixture values, no stubs** that
   fake the behaviour a test asserts.
5. **Commit in small logical chunks** with Conventional Commit messages, push, and
   open the pull request against `main` — never commit directly to `main`.
6. **Respect the protected files.** `AGENTS.md`, `CLAUDE.md`, `SOUL.md` and
   `.cursorrules` are owner-approved only (conventions §10.3). A refused write is
   a stop, not a puzzle to route around.
7. **Do not block on questions you can answer.** When a decision truly needs a
   human, record the context and surface it; do not silently guess.
8. **Report what you measured.** Test counts, check runs on the head SHA and the
   merge gate output are evidence; "should pass" is not.
9. **Record decisions in ADRs** (section 7) exactly as a human would.

Agents that write code do not write the tests for it and do not approve their own
work: the author, the reviewer and the merger are separate roles.

## 10. Contribution terms

By submitting a contribution you accept the terms in [`LICENSE`](LICENSE) §6. In
short:

- You keep the copyright in your contribution.
- You grant the owner a perpetual, irrevocable, worldwide, royalty-free licence to
  use, modify, distribute **and relicense** your contribution under any terms,
  including a future different licence for the project.
- You confirm the contribution is yours to submit and does not knowingly infringe
  anyone else's rights.
- The contribution is provided as-is, without warranty, and the owner is not
  obliged to use it.

Without that grant the project could not change its licence later, which is why it
is a condition of contributing rather than a formality.

## 11. Security

Do not open a public issue for a vulnerability. Use
[GitHub security advisories](https://github.com/yahodu/openpic-worker/security/advisories/new)
with the affected component, a reproduction and the impact — see
[`SECURITY.md`](SECURITY.md) for the scope and the credentials this repository
handles. Never commit a real secret: `.env.example` carries placeholders only, and
a secret scan runs on every pull request.

## 12. Questions

Open an issue with the `question` label, or ask in the pull request. For licensing
or commercial use, contact the owner through <https://openpic.in>.
