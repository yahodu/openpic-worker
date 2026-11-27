# Engineering Conventions — OpenPic Python Worker

Authoritative engineering standard for this repository. Every story, every PR and
every autonomous agent is held to it. `AGENTS.md` is the agent entry point; this
file is the detail it links to.

If a convention creates friction, raise it via an ADR (`docs/adr/`) — never bypass
it silently. When two documents disagree, apply §11.

---

## 1. Scope, and the contract this worker is held to

### 1.1 What the worker is

A long-running, pull-based, GPU-bound consumer of the OpenPic face pipeline. It
claims work from two logical queues (`q:selfie` before `q:image`), leases the work
item in MongoDB, downloads the original from object storage, runs detection and
recognition, writes faces and matches, generates the thumbnail derivative, and
reports the verdict to the control plane.

It is **not** a web service, **not** a scheduler, and **not** a notification
producer. Those are the Next.js control plane's jobs (contract §10.2, §10.3;
`openpic-webapp` ADR-0808, ADR-0830, ADR-0849).

### 1.2 The worker's write surface — closed list

The worker writes to MongoDB directly, and only these fields. Anything else is a
review blocker.

| Collection | What the worker may write | Why |
|---|---|---|
| `event_images` | `faceCount`; `processing.{status:processing, leaseExpiresAt, workerId, startedAt, attempts}` on claim/renewal | §4.4 returns `faceCount`; §18.2 makes `processing` the durable job state |
| `selfies` | `embedding`, `spaceKey`; `processing.{…}` lease fields on claim/renewal | The query vector must survive for reuse and incremental runs |
| `imageFaces` | Full upserts on `{imageId, faceIndex}` | §17.3; the only producer of this collection |
| `face_matches` | Full upserts on `{profileId, imageId, faceIndex}` | §17.5; the only producer of this collection |
| `attendee_event_profiles` | **Only** in the `match_incremental` arm: `status`, `matchCount`, `lastMatchRunAt`, `updatedAt`, pointer-guarded (ADR-0007) | No `match_incremental` report kind exists; every other transition is the report route's |

Everything else goes through `POST /api/v1/internal/worker/report`: the terminal
`processing.status`, `quality`, `liveness`, the event-image recount trigger and
the selfie→profile projection. Writing those twice creates a race the server
cannot arbitrate (ADR-0830 §7, ADR-0834 §3, ADR-0837).

### 1.3 Hard rules

- **The vector search runs inside MongoDB.** The worker builds a `$vectorSearch`
  aggregation and receives decisions, not candidate sets (contract §10.3.1,
  "constraint C3"). Loading vectors into Python to compare them is a contract
  violation, not an optimisation.
- **The message is a pointer.** No payload, no URL, no embedding, no broker id in
  a domain field (contract §10.4).
- **No notification client, no domain-event producer.** The report route is the
  single publisher of match outcomes (`attendee.matches.ready` / `.new`); §10.3.2
  offers `/internal/domain-events` and the shipped server has narrowed that to
  report-only. Recorded divergence: ADR-0004, to be ratified by a contract
  amendment — do not "fix" it in a worker PR. See §11.1 for this and the other
  open questions before touching the pipeline.
- **Every tenant-scoped filter carries `tenantId`.** A filter without it is a
  review blocker (§9).
- **The worker never trusts the envelope for state.** It re-reads the document at
  claim time and rejects a document whose `tenantId`/`eventId` disagree with the
  envelope (§10.4).

---

## 2. TDD iron law

- **Never write production code without a failing test.** Work in vertical tracer
  bullets: one failing test → minimal code to green → refactor.
- Order of operations: write the test (**RED**), confirm it fails for the right
  reason, write the minimum code (**GREEN**), run the single test, then the full
  suite, then **REFACTOR** while staying green.
- Run the single test first — `uv run pytest tests/unit/test_claim.py::test_two_claims_one_winner -q`
  — then the whole suite before commit.
- **Paste the RED and GREEN command output in the PR description.** A PR without
  both is not reviewable. RED output must show the assertion failure, not an
  import error from a module that should already exist.
- Tests are owned by the Test Author. Implementers and agents never edit, skip,
  weaken, `xfail`, or delete a test to make the suite pass. A green suite built on
  a rewritten test is a failed delivery — raise a dispute instead.
- A story that ships no production code (documentation, runbook, ADR only) is the
  only kind that may skip this law, and it must say so in the card.
- Every bug fix starts with a regression test that fails on the current trunk.

---

## 3. Test pyramid and doubles

| Layer | Tooling | Use for |
|---|---|---|
| Unit | `pytest`, `pytest-asyncio`, `pytest-mock`, `polyfactory` | Pure builders, mappers, validators, redaction, threshold maths, pipeline-stage construction |
| Integration / contract | `pytest` + a real `mongod` **replica set**, real Redis, real MinIO/S3-compatible store, `respx` | Claim/lease races, transactions, unique-index idempotency, queue semantics, signed requests, end-to-end item processing |
| E2E | `pytest` against the docker-compose stack with a **fake** inference backend | Multi-component journeys: enqueue → claim → process → report → observable state |

- **MongoDB integration tests run against a real replica set**, never a mock —
  multi-document transactions and `findOneAndUpdate` semantics are the thing under
  test. `mongodb-memory-server` is a Node package; here the fixture starts
  `mongo:7` with `--replSet` through `docker compose` and calls `rs.initiate()`.
- **No test touches the network.** `respx.mock(assert_all_mocked=True)` is
  installed by an autouse fixture for every test that can egress, and a session
  fixture patches `socket.socket.connect` to raise on any non-loopback address.
  An unhandled request is a bug, not a warning.
- **No GPU in CI.** GitHub-hosted runners have no CUDA device. Every test
  exercises the inference port through a fake backend. Anything that genuinely
  needs a GPU carries `@pytest.mark.gpu` and runs only on a self-hosted runner
  through `workflow_dispatch` — never on `pull_request`.
- **Markers are enforced.** `unit`, `integration`, `gpu`, `e2e`, `docs`; the
  default `pytest` run is `-m "not gpu and not e2e"` and must stay under 60 s.
- **Determinism.** No `sleep` for synchronisation, no wall-clock assertions, no
  ordering assumptions that the contract does not state. Time comes from an
  injected `Clock`; randomness from an injected `Random`/seeded jitter.
- **Every test is isolated.** Fixtures create their own tenant/event ids; no test
  depends on another's writes; the Redis and Mongo fixtures truncate between
  tests in the integration suite.
- **Coverage** floor lives in `[tool.coverage.report].fail_under` (90), and
  `openpic_worker/adapters/**` may be excluded only for lines that cannot execute
  in CI — with the exclusion named in the module docstring.
- **Playwright is not used here.** The worker has no browser surface. Do not add
  `pytest-playwright` "for completeness".

---

## 4. Pydantic contracts and fixtures

- Every boundary has a model: the queue envelope, every work-item document the
  worker reads, every command it writes, every request and response of the
  internal API, every third-party payload (storage XML/headers, Better Stack
  responses), and the worker's own configuration.
- **Write models are strict** (`extra="forbid"`, `frozen=True`). **Read models are
  forward-compatible** (`extra="ignore"`) because the control plane may add
  fields in `v1`; an unknown field must not crash a worker mid-batch. This is the
  only place the two differ, and the reason is stated in the model docstring.
- Unknown **enum values** on read fall back to a documented safe default and log
  `warn contract.unknown_enum`; unknown enum values on write are a validation
  error. Never guess a value.
- **Parse at the boundary, once.** `Model.model_validate(raw)` on ingress; never
  index into a raw `dict` in domain code. Upstream payloads are untrusted.
- **Identifiers and time are validated types**, not `str`: 24-hex `ObjectIdHex`,
  timezone-aware UTC `datetime`, `Sha256Hex`, `SpaceKey`. A model that accepts
  `str` where the contract says ObjectId is a defect.
- **Fixtures are built only through `build_x(overrides)` factories** backed by
  `polyfactory.ModelFactory` and calling `model_validate` on their own output, so
  a fixture can never drift from its schema. Never hand-write a fixture dict.
- **No `dict[str, Any]` in a domain signature.** Model the type or narrow it.
  A genuinely open payload (the domain-event payload the worker never sends) is
  not a licence to use one elsewhere.
- Serialisation is canonical: RFC 3339 UTC with milliseconds and `Z`; ints for
  bytes/durations; `null` means "known absent", never "unknown".

---

## 5. Docstrings and comments

- Docstrings on every module, public function, class, method, and every port
  implementation. Google style; enforced by ruff `D` + `ANN`.
- Each docstring states **purpose**, `Args:`, `Returns:`, `Raises:` with the
  exception type, and `Example:` for a non-trivial utility.
- Every module that implements part of the contract cites it:
  `Contract: §10.3.1 (claim and lease).` Every module that exists because of a
  decision cites the record: `ADR-0003`.
- Comment the **WHY**, not the WHAT. If the code needs a WHAT comment, rename it.
  A comment that restates the line is noise and is deleted in review.
- Public exceptions document the stable `code` they map to, because the server
  branches on `code` (contract §10.3.3).

---

## 6. Logging

### 6.1 The port, and why there is one

Application code logs through the `Logger` protocol only. It has a single
`log(level, event, **fields)` surface plus level helpers; it never knows whether
the sink is stdout, Better Stack, or a test list. The Better Stack adapter is one
module behind the port, selected by `LOG_SINK`; swapping vendors changes that
module and one env var, nothing else.

- `stdout` (default) emits one JSON object per line. This is the twelve-factor
  stream and the fallback when a remote sink is down.
- `betterstack` tees to the port's stdout **and** ships batches over `httpx` to
  the Better Stack ingesting endpoint.
- `memory` is the test sink; it records every record verbatim.
- `null` exists only for benchmarks.

A remote sink never blocks the event loop, never raises into the caller, and
never loses the local line: a failed ship logs `warn logging.sink_dropped` with
`droppedCount` and the batch is discarded after the retry budget.

### 6.2 Level policy

| Level | Use when |
|---|---|
| `fatal` | The process cannot continue: model load failed at startup, config invalid at boot |
| `error` | A work item or a contract broke: upstream schema drift, invariant violation, report rejected, unhandled exception in a task |
| `warn` | Degraded but continuing: CPU fallback, lease lost, poison message dead-lettered, sink dropped, CPU/GPU pressure, pause requested |
| `info` | One line per lifecycle fact: claimed, done, skipped, space switched, heartbeat started, shutdown drained |
| `debug` | Scheduler decisions, retry delays, per-stage timings |
| `trace` | Per-face geometry and per-stage internals; **off in production** |

One `info` line per item completion, not one per stage. A batch of 500 images
must not produce 5,000 info lines.

### 6.3 Field dictionary

| Field | Required | Type | Meaning |
|---|---|---|---|
| `event` | yes | string | Dotted event name, e.g. `pipeline.image.done` |
| `traceId` | yes | string | The envelope's `traceId`, propagated to every line and to the report |
| `workerId` | yes | string | Stable per process; the same value the heartbeat and report send |
| `tenantId` | no | string | When the event is tenant-bound |
| `eventId` | no | string | When the event is event-bound |
| `kind` | no | string | `event_image` / `selfie` / `match_incremental` |
| `itemId` | no | string | The work item id (never a raw object key or URL) |
| `attempt` | no | int | `processing.attempts` at the time of the line |
| `durationMs` | no | int | Elapsed time for the stage or item |
| `queueKey` | no | string | `q:selfie` / `q:image` |
| `err` | no | object | `{type, code, message, stack?}`; stack only at `error`+ |

`event` and `traceId` are mandatory on every line. A tenant- or event-scoped line
that lacks `tenantId`/`eventId` when they are known is a defect.

### 6.4 Event names

`<domain>.<subject>.<verb>`, past tense for facts, present for decisions:
`pipeline.item.claimed`, `pipeline.image.done`, `pipeline.selfie.done`,
`pipeline.item.skipped`, `pipeline.lease_lost`, `queue.poison_message`,
`inference.model_loaded`, `inference.cpu_fallback`, `media.derivative.uploaded`,
`worker.paused`, `worker.shutdown_drained`, `contract.unknown_enum`.

### 6.5 Redaction list

These values MUST never appear in a log field, message, error serialisation or
exception `repr`:

- passwords, API keys, access/refresh tokens, session ids, CSRF tokens, cookies
- `Authorization`, `Cookie`, `Set-Cookie` header values — log the header *name*
  and `[REDACTED]`, never the value
- webhook signing secrets and signatures; `INTERNAL_API_SECRET`
- presigned URL query strings (`X-Amz-Signature`, `sig`, `token`, `exp`) — log the
  object key's *hash* or the derivative variant, never the URL
- private keys, connection strings (`MONGODB_URI` with credentials,
  `UPSTASH_REDIS_REST_TOKEN`)
- payment card numbers, government identifiers, health data — out of scope for
  this worker, and therefore never to be accepted into it
- face embeddings and vectors, in any form, raw or base64 (biometric data)

Where correlation is needed, log a stable hash or the last four characters. The
redaction filter is applied at the port, so no adapter can bypass it; tests in
`tests/unit/test_log_redaction.py` are the enforcement.

### 6.6 Rules

- Never `print`, never `logging.basicConfig`, never `console.*`-equivalents. Ruff
  `T20` is selected and enforced.
- Never import a vendor logging SDK outside `openpic_worker/adapters/logging/`.
- Never log the request body of an internal API call, the queue payload, or the
  contents of a work-item document. Log ids.
- Exception text is untrusted: a library error may embed a URL or a token. It goes
  through the redactor before it is formatted.

---

## 7. Twelve-factor

- **Config** from environment only. No config files, no hard-coded tunables.
  Every knob is a `Settings` field with a range validator; every secret is a
  `SecretStr`. A value that changes a *matching decision* (`thresholds.match`,
  `minDetScore`, `matchLimit`, `exactSearch`, `activeSpaceKey`, `leaseMinutes`,
  `maxAttempts`, `pauseRequested`) is read from MongoDB (`platformSettings`,
  `faceModels`) — the config channel — not from env. Env carries what the host
  knows (endpoints, credentials, concurrency, paths).
- **Processes are stateless.** Nothing that cannot be rebuilt matters. The only
  local state is a bounded spool directory for in-flight downloads, wiped at boot.
  Scale-out is `replicas += 1`; behaviour must not change.
- **Logs** are an event stream to stdout; Better Stack is a consumer, not a
  dependency.
- **Backing services** (MongoDB, Redis, object storage, the internal API, the log
  sink, the inference backend) sit behind ports, selected by env. Swapping a
  vendor touches one adapter and one `Settings` field.
- **Admin processes** (index check, model backfill, coverage report) are one-off
  `python -m openpic_worker.admin.<name>` scripts. They never run at boot and are
  never route handlers.
- **Dev/prod parity.** The same adapters run everywhere; tests substitute
  doubles (`respx`, fake engine, memory queue), they never branch on `APP_ENV`.
  The one allowed difference is log verbosity.
- **Disposability.** SIGTERM → stop claiming → drain → flush → exit 0 within the
  grace period. Crash-only: a second signal exits immediately.
- **Concurrency** is one process per GPU, with bounded async concurrency inside
  it. Do not spawn a subprocess per item to "get parallelism".

---

## 8. Code

- **TypeScript-era rules, Python spelling.** `ty` in strict mode over `src/` and
  `tests/`. **No `Any`** — model the type or narrow it. `# type: ignore` needs a
  comment naming the reason and is capped at zero in `src/` (a third-party stub
  gap is the only accepted case, and it lives in `typings/`).
- **Ruff is the only linter and formatter.** `select` is broad and explicit
  (`E,F,W,I,N,UP,B,SIM,ASYNC,S,DTZ,TC,TID,RUF,PL,PERF,LOG,G,TRY,EM,ARG,PTH,D,ANN,T20`);
  every `ignore` has a one-line reason in `pyproject.toml`. Line length 100.
- **Immutability by default.** `frozen=True` models, `tuple` over mutated `list`
  in return values, no in-place mutation of a function argument. Local mutation
  inside a pure function is fine.
- **KISS, DRY, YAGNI.** Build only what a test demands. A "framework" for two
  work kinds is speculative and is rejected in review.
- **Verb–noun names**: `claim_item`, `renew_lease`, `build_match_pipeline`,
  `report_outcome`. No `Manager`, `Helper`, `Util` classes.
- **Async discipline:**
  - every I/O call has a timeout; a call without one is a bug;
  - no blocking call on the loop — decode, inference and file I/O go through
    `asyncio.to_thread` or a dedicated single-thread executor;
  - bounded concurrency with a `Semaphore`, never `asyncio.gather` over an
    unbounded input;
  - structured concurrency with `TaskGroup`; a crashed task cancels its group;
  - cancellation is honoured: no `except Exception: pass`, no swallowing
    `CancelledError`;
  - `asyncio.sleep(0)` is not a yield strategy for a busy loop.
- **No bare `except`.** Catch the narrowest type and map it into the error
  taxonomy (§8.1). An unexpected exception is logged `error` with `err` and
  converted to a retryable `internal_error` verdict — never swallowed.
- **No vendor name in a domain field or a domain vocabulary.** `StoragePort`, not
  `R2Client`; `LogSink`, not `BetterStackLogger`.
- **Dependencies are pinned** in `uv.lock`; no `*`, no git URLs without a commit
  SHA; a new runtime dependency needs a line in the PR body saying why.

### 8.1 Error taxonomy

The worker's errors are the contract's (`§10.3.3`), plus internal ones that never
cross the boundary:

| Code | Retryable | Meaning |
|---|---|---|
| `download_failed` | yes | transient storage failure |
| `corrupt_image` | no | unreadable bytes |
| `unsupported_format` | no | upload guard gap — log as a validation gap |
| `no_faces_detected` | — | **not an error**: `done` with `faceCount: 0` |
| `model_load_failed` | yes | infrastructure |
| `inference_timeout` | yes | |
| `oom` | yes | retry elsewhere |
| `vector_search_failed` | yes | Atlas index unavailable |
| `lease_lost` | — | abandon silently, write nothing |
| `liveness_failed` | no | terminal even if the engine says retryable |
| `internal_error` | yes | unclassified; always logged with `err` |

---

## 9. Security

- **Tenant isolation.** Every query filter includes `tenantId`, structurally: the
  repository constructor takes the tenant id and there is no method that builds a
  filter without it. A cross-tenant document is skipped as if absent and logged
  `warn security.tenant_mismatch` without the other tenant's id.
- **Never-return / never-log.** No embedding, no object key, no signed URL, no
  provider token, no stack trace, no Mongo query text in a log line or an API
  body. The report carries ids, counts and timings only (contract §0.15).
- **Constant-time comparison** for every secret comparison (`hmac.compare_digest`),
  never `==`.
- **SSRF.** Storage endpoints come from an allow-list of hosts; the internal API
  base URL must be `https` (except an explicit `localhost` dev override). The
  worker never fetches a URL supplied by a queue message.
- **Path traversal.** Object keys are derived from a validated `Sha256Hex` and a
  format allow-list; a body-supplied key is never trusted and never accepted from
  a caller.
- **Untrusted media.** Sniff magic bytes before decode, cap decoded pixels and
  bytes, strip EXIF before any derivative is written, never `pickle`, never
  `eval`, never `subprocess` with `shell=True`.
- **Least privilege.** The container runs as a non-root uid, with a read-only root
  filesystem and one writable spool/model-cache mount. The Mongo user is
  scoped to the pipeline database; the storage key can read originals and write
  thumbnails only.
- **Secrets** are `SecretStr`, never in `repr`, never in a Docker layer, never in
  a log. `.env.example` holds names and placeholders only.
- **Supply chain.** `uv.lock` is committed and CI runs `uv sync --frozen`;
  `pip-audit` blocks on runtime advisories; `gitleaks` scans every PR; workflow
  actions are pinned to full commit SHAs.

---

## 10. Definition of Done

A story is complete only when **all** of the following hold:

- [ ] Tests were written first and are green (RED + GREEN output in the PR).
- [ ] `uv run pytest` passes; coverage is at or above the configured threshold.
- [ ] `uv run ruff check .` and `uv run ruff format --check .` are clean.
- [ ] `uv run ty check` is clean.
- [ ] Docstrings are present on every public symbol and contract module.
- [ ] Structured logs were added for the new behaviour (§6), with the right level.
- [ ] Pydantic models and `build_x` factories exist, and the factories parse.
- [ ] The relevant contract section and ADR are cited in the module docstring.
- [ ] No hard-coded tunable: every knob is env or the config channel.
- [ ] No new dependency without a stated reason; `pip-audit` clean.
- [ ] An ADR was added in `docs/adr/` for any new decision.
- [ ] The ADR number is the `Consumes` value reserved in the card body — never
      derived from `docs/adr/README.md` — and no same-lane ADR-minting sibling is
      in flight.
- [ ] The ADR record carries its own `docs/adr/README.md` ledger row **in the same
      PR** (§12).
- [ ] The merge gate printed PASS on the exact head SHA and its output is in the
      PR (§10.1).
- [ ] The merged PR's head is archived to `refs/prhead/<n>` and its local branch
      released in the merge step, with the assertions printed (§10.2).

This list is mirrored, copy-pasteably, in `.github/pull_request_template.md`.

### 10.1 The merge gate

The merging agent evaluates these seven conditions against the PR's **current
head SHA** and pastes the output into the PR before `gh pr merge`.

- **G1** `mergeable == "MERGEABLE"` and `mergeStateStatus` ∉ {`DIRTY`, `UNKNOWN`};
  re-poll up to 5 × 3 s when `UNKNOWN`.
- **G2** every entry in `statusCheckRollup` for the head is `status: COMPLETED`
  with `conclusion: SUCCESS` — no `FAILURE`, no `PENDING`, no `CANCELLED`, no
  `SKIPPED` on a gating name.
- **G3** the gating name set is present on the head: `CI / Lint & format`,
  `CI / Type check`, `CI / Tests`, `CI / Dependency audit (runtime)`,
  `CI / Secret scan (gitleaks)`, `PR Checks / Branch name`,
  `PR Checks / PR title (conventional commits)`, `PR Checks / Lockfile consistency`,
  `PR Checks / Env var documentation`, `CodeQL / Analyze (python)`,
  `Security / Dependency review`.
- **G4 (audit freshness)** No commit on `origin/main` in
  `<merge-base>..origin/main` may touch the audit input surface — `uv.lock`,
  `pyproject.toml`, `Dockerfile`, `.github/workflows/ci.yml` — with a commit date
  later than the head's `audit` check `completedAt`. If one did, the green
  predates a change in what `audit` means: **STALE**.
- **G5** `git diff --quiet <merge-base> origin/main -- uv.lock pyproject.toml Dockerfile .github/workflows/ci.yml`
  — if false, the merge would change the audited tree.
- **G6** on any failure: **do not merge**, do not rebase, do not `gh run rerun`,
  do not `--admin`. Comment the failing condition and route it — merge
  `origin/main` in, push, get a fresh run, re-evaluate G1–G7 on the new head.
- **G7 (ADR-carrying PRs only)** the ADR number the PR **adds** appears at **no
  other open PR head** — re-swept at the merge instant. A hit is a failure under
  G6; the lander renumbers its own unmerged record and re-runs.

```
N=<pr>; SHA=$(gh pr view "$N" --json headRefOid -q .headRefOid)
gh pr view "$N" --json mergeable,mergeStateStatus
gh pr view "$N" --json statusCheckRollup \
  -q '.statusCheckRollup[] | "\(.name)\t\(.status)\t\(.conclusion)\t\(.completedAt)"'
BASE=$(git merge-base "$SHA" origin/main)
git log --format='%cI %h %s' "$BASE"..origin/main -- \
  uv.lock pyproject.toml Dockerfile .github/workflows/ci.yml
git diff --quiet "$BASE" origin/main -- \
  uv.lock pyproject.toml Dockerfile .github/workflows/ci.yml && echo G5-pass
# G7 (ADR-carrying PRs only): the number this PR adds must be absent from every other open head
N=<pr>; NUM=<NNNN>
for p in $(gh pr list --state open --json number -q '.[].number'); do
  [ "$p" = "$N" ] && continue
  sha=$(gh pr view "$p" --json headRefOid -q .headRefOid)
  gh api "repos/yahodu/openpic-worker/contents/docs/adr?ref=$sha" --jq '.[].name' |
    grep -E "^ADR-${NUM}-" && echo "COLLISION: PR #$p holds ADR-${NUM}"
done
```

### 10.2 The post-merge step

`delete_branch_on_merge` is `true` on this repository, so a merge deletes the
remote head and the local branch is the only survivor. After the squash lands, in
the same run, before the merging card completes:

1. **Read the reviewed tip from the pull ref, never from the branch:**
   `HEAD_SHA=$(git ls-remote origin "refs/pull/$N/head" | cut -f1)`
2. **Archive first** (only when the ref is absent):
   `git update-ref "refs/prhead/$N" "$HEAD_SHA"`.
3. **Release the holder, then delete with compare-and-delete:**
   `git update-ref -d "refs/heads/<head-branch>" "$HEAD_SHA"` — never
   `git branch -D`, which refuses while checked out and cannot express "only if
   the tip is still the reviewed SHA". A worktree on the branch detaches first.
4. **Assert, and quote the four lines:** `refs/heads/<head-branch>` prints
   nothing; `refs/prhead/$N` prints one line; its SHA equals `HEAD_SHA`;
   `git worktree prune --dry-run` is empty.

Release only when the PR is `MERGED` and the squash commit is an ancestor of
`origin/main`; the archived tip is served verbatim by `refs/pull/<n>/head` or is
already an ancestor of `origin/main` (a moved tip is **kept and reported**); the
branch is local-only (`git ls-remote --heads origin` is empty); no worktree is on
it and no other non-`done` board row names it. A **dirty** worktree is never
removed and its branch is never deleted — record it as a skipped head.

**Liveness.** A board row is live when its `status` is not `done`/`archived` **or**
it has a run with `ended_at IS NULL`, because the dispatcher keeps a worker
process alive for up to `TERMINAL_WORKER_REAP_GRACE_SECONDS` after handoff. Every
live row other than the merging card's own keeps its branch.

**Exception.** Every unmerged PR is out of scope — a RED-by-design pin PR, a PR
held for a dependency, a PR closed as superseded — and keeps its branch and
worktree. The rule is authorised by a **merge**, never by a card completing.

### 10.3 Protected agent-instruction files

`AGENTS.md`, `CLAUDE.md`, `SOUL.md` and `.cursorrules` are protected. Hermes
blocks `write_file`/`patch` on those basenames and asks a human to approve; a
headless Kanban worker has no human at that prompt, so the guard waits out its
timeout and refuses. The protocol:

1. Stop at the first refusal. Do not retry, do not route around it.
2. Publish the exact diff and `sha256sum` of the patch file on the card.
3. `kanban_block(kind="needs_input", reason=…)` naming the file and the hash.
4. Wait for an explicit board-owner comment naming the file, after the diff.
5. Apply the approved diff unchanged; prove the applied hash equals the published
   hash and the file's `git diff` equals the published diff.
6. Record the owner comment ids, the patch hash and the landed commit in the
   handoff.

Only a published diff may be applied; the change is additive or clarificatory; the
landing reviewer re-derives the applied-vs-published diff. A rule that is removed
or weakened is the owner's own commit, never a worker's. If the rule fits in this
file or an ADR, write it there and let the protected file point at it.

---

## 11. Authority order when documents conflict

1. **MongoDB schema and Notification design** (highest)
2. **API contract**
3. **Shipped `openpic-webapp` behaviour** — evidence, not authority
4. **This file and the worker's ADRs**

When (3) contradicts (1) or (2), stop and raise it: the worker follows the
contract, and the divergence is recorded in `docs/adr/` and routed to the webapp
lane as a contract amendment. Do not silently pick a side, and do not "fix" the
control plane in a worker PR.

### 11.1 Open contract questions — check these before the first feature PR

These are unresolved differences between the contract and the shipped control
plane. Grep `11.1 Open contract question` to find them. Each one names its
evidence, what the worker does **until** it is resolved, and who owns the
resolution. Do not close one by editing worker code alone: the deliverable is an
ADR in this repo **and** an amendment request on the webapp lane.

**Q1 — does the worker emit domain events, or does the report route publish
every outcome?**
§10.3.2 documents `POST /internal/domain-events` as available to the worker and
the §10.3 diagram shows the call, but the shipped report route publishes the arm
itself (`attendee.selfie.rejected` at `report/route.ts:296`; match outcomes per
ADR-0808 §3) and no worker producer exists.

- **Evidence:** `openpic-webapp` `apps/web/src/app/api/v1/internal/worker/report/route.ts`,
ADR-0808 §3, ADR-0830 §1.
- **Until resolved:** report-only. The worker opens no outbox client and emits
nothing; a second publisher would double-send match notifications.
- **Route:** ADR-0004 here; ask the webapp lane to amend §10.3.2.

**Q2a — `match_incremental` has no report kind, so how is the profile projection
written?**
The report body's union is `event_image | selfie` only, and its lease predicate
cannot match a profile row that was never leased.

- **Evidence:** `report/route.ts:70-90` (union), `report/route.ts:255-285`
(pointer-guarded profile write, selfie arm only).
- **Until resolved:** the worker writes `status`, `matchCount` and `lastMatchRunAt`
directly for this kind, pointer-guarded on `activeSelfieId`, and reports nothing.
- **Route:** ADR-0007 here; ask for a `match_incremental` report kind or an explicit
"the worker owns this projection" clause.

**Q2b — the sweep advances the watermark before enqueueing, so the run's own
trigger is below its lower bound.**
The sweep sets `lastMatchRunAt = now` as its claim *before* it enqueues
(`pipeline-sweep.ts:300-305`). The worker queries `createdAt > lastMatchRunAt`,
so faces created between the last run and the sweep's `now` — exactly the ones
that triggered the run — fall below the bound and are never scored. §10.3.1's
watermark rule assumes the worker owns that write.

- **Evidence:** `apps/web/src/server/jobs/pipeline-sweep.ts` step 4; §10.3.1
"watermark rule"; schema §18.1.
- **Until resolved:** query from `lastMatchRunAt - INCREMENTAL_LOOKBACK_SECONDS`
(default 300 s). Upserts are idempotent, so re-scoring is free; the only cost is
a larger candidate set.
- **Route:** ADR-0007 here; the durable fix is the sweep carrying the pre-claim
watermark in the envelope (a §10.4 change), which needs a webapp lane card.

Two further ownership facts are **not** open — they were verified in code and are
binding here: the report route owns the terminal `processing.status`, the selfie
`quality`/`liveness` patch and the profile projection on the selfie arm
(`report/route.ts:180-290`), and nothing in the control plane writes
`event_images.faceCount` after upload (`uploads/registration.ts:102` seeds 0), so
the worker writes it (§1.2).

When one of these is resolved, amend this section **and** the ADR in the same PR;
a note left behind after the contract changes is how the next agent inherits a
stale rule.

---|---|---|---|---|
| **Q1** | Does the worker emit domain events, or does the report route publish every outcome? §10.3.2 documents `POST /internal/domain-events` as available to the worker and the §10.3 diagram shows the call; the shipped report route publishes the arm itself (`attendee.selfie.rejected` at `report/route.ts:296`, match outcomes per ADR-0808 §3) and no worker producer exists. | `openpic-webapp` `apps/web/src/app/api/v1/internal/worker/report/route.ts`, ADR-0808 §3, ADR-0830 §1 | **Report-only.** The worker opens no outbox client and emits nothing; a duplicate publisher would double-send match notifications. | ADR-0004 here; ask the webapp lane to amend §10.3.2 (remove the worker's outbox option or scope it to future events). |
| **Q2a** | `match_incremental` has no report kind, so how is the profile projection (`status`, `matchCount`, `lastMatchRunAt`) written? The report body's discriminated union is `event_image \| selfie` only, and its lease predicate cannot match a profile row that was never leased. | `report/route.ts:70-90` (union), `report/route.ts:255-285` (pointer-guarded profile write on the selfie arm only) | The worker writes the projection directly for this kind, pointer-guarded on `activeSelfieId`, and reports nothing. | ADR-0007 here; ask for a `match_incremental` report kind or an explicit "the worker owns this projection" clause. |
| **Q2b** | The sweep sets `lastMatchRunAt = now` **before** enqueueing, as its claim (`pipeline-sweep.ts:300-305`). The worker's incremental query uses that field as its lower bound, so the faces that triggered the run — created between the last run and the sweep's `now` — fall below it and are never scored. §10.3.1's watermark rule assumes the worker owns the write. | `apps/web/src/server/jobs/pipeline-sweep.ts` step 4; §10.3.1 "watermark rule"; schema §18.1 | Query from `lastMatchRunAt - INCREMENTAL_LOOKBACK_SECONDS` (default 300 s), relying on idempotent upserts to make re-scoring free. | ADR-0007 here; the durable fix is the sweep carrying the pre-claim watermark in the envelope (a §10.4 change), which needs a webapp lane card. |

Two further ownership facts are **not** open — they were verified in code and are
binding here: the report route owns the terminal `processing.status`, the selfie
`quality`/`liveness` patch and the profile projection on the selfie arm
(`report/route.ts:180-290`), and nothing in the control plane writes
`event_images.faceCount` after upload (`uploads/registration.ts:102` seeds 0), so
the worker writes it (§1.2).

When one of these is resolved, amend this table **and** the ADR in the same PR;
a table entry left behind after the contract changes is how the next agent
inherits a stale rule.

---

## 12. ADR numbering

ADR numbers live in `docs/adr/README.md`, a single table. The rules:

- **Reserve at card creation, never derive at branch cut.** The allocator writes
  `**Consumes: NNNN**` into the card body (`none` for a card that mints no
  number). The worker takes the number as given. It never reads the ledger tail,
  the `Next free` cell, or the highest file on disk to compute one.
- **In-flight-aware allocation.** Before handing out a number the allocator
  enumerates (a) every live worktree's `docs/adr/`, (b)
  `git rev-list --objects --all -- docs/adr`, (c) non-`done` cards' `Consumes`
  values, and (d) **every open PR head** (`git fetch origin <branch>` before
  `git ls-tree <sha> docs/adr/`). A branch outside the ticket prefix and an
  unpushed commit are invisible to a remote listing, so (d) is not optional.
- **A card that finds `Consumes` missing or `TBD` comments and blocks** — it never
  invents a number.
- **The file number equals the body's `Consumes` value.** A mismatch is returned
  by the reviewer, not worked around.
- **A ledger row lands in the same PR as the record.** A record with no row, or a
  row with no record, is a DoD failure.
- **The note mirrors the record, not its own history.** Amending a record amends
  its note in the same PR. A deliberately historical statement lives inside the
  record, dated.
- **Index-only conflicts resolve as a union** — keep both sides' rows in
  ascending order, then `Next free = max(consumed) + 1`; never pick a side,
  because a pick-a-side resolution silently drops a row.
- **The guard** is `tests/unit/test_adr_numbering.py`: it fails on a duplicate
  `ADR-NNNN` prefix or a malformed `ADR-*.md` name, and it runs in `pytest`.
  It does not check lane ranges or `origin/main`; those stay review-time
  obligations.
- **Citations of the webapp's records are qualified**: `openpic-webapp ADR-0318`,
  never a bare `ADR-0318`, because both repos have a number `0318`.

Reserved worker range: `0001`–`0999`. A record above `0999` needs a new range row.

---

## Appendix — command cheat-sheet

```
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest -q
uv run pytest -q -m "not gpu and not e2e"
uv run pytest -q -m integration          # needs docker compose up -d
uv run pytest tests/unit/test_x.py::test_y -q
uv run python -m openpic_worker          # the worker
uv run python -m openpic_worker.admin.index_check
```

Document map: `AGENTS.md` (agent entry point) · `docs/CONVENTIONS.md` (this file)
· `docs/adr/` (decisions) · `docs/user-stories/` (the delivery plan)
· `.github/pull_request_template.md` (PR + DoD).
