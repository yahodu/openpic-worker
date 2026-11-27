# CI/CD

Five workflows, one job each per concern. Everything is triggered by the
branch model this repo runs on: `main` is the only long-lived branch, work
lands there through a PR, and `main` is what deploys.

| Workflow | Trigger | Blocks merge | Purpose |
| -------- | ------- | ------------ | ------- |
| `ci.yml` | PR, push to `main` | yes | lint, format, types, tests, runtime dependency audit, secret scan |
| `pr-checks.yml` | PR | yes | branch name, conventional PR title, PR size, lockfile consistency, env docs |
| `codeql.yml` | PR, push to `main`, weekly | yes (Security tab) | static analysis of the Python surface |
| `security.yml` | PR, push to `main`, weekly, branch-protection changes | yes (dependency review) | dependency review on PRs, OpenSSF Scorecard |
| `cd.yml` | push to `main`, manual | — | image build/scan/attest, Modal deploy, smoke test |

## Current state: the gates are dormant

The repository is empty on purpose — the worker is being rewritten. Every
Python job detects `pyproject.toml` and skips while it is absent, so `main`
stays green instead of red for a missing file. Nothing needs to be edited to
turn them on: push a `pyproject.toml` plus `uv.lock` and the lint, type,
test and audit jobs start running. The `project` detector job can be deleted
once that happens; it becomes dead weight.

`pr-checks.yml`, `security.yml` and the secret scan are live **now** — they
apply to docs, workflows and config as well as to Python.

## Toolchain assumptions

- **uv** for dependency resolution (`uv.lock`, `uv sync --frozen`). CI never
  re-locks; a stale lockfile is a failed build, which is the point.
- **ruff** for lint *and* format. One tool, one config block, no Black/isort
  stack.
- **mypy** for types.
- **pytest** with coverage; the threshold lives in `[tool.coverage.report].
  fail_under`, so the policy is next to the code rather than in YAML.
- **pip-audit** for advisories, split into a blocking runtime audit and a
  non-blocking dev-toolchain audit.
- **gitleaks CLI**, installed from a pinned release and verified against its
  published SHA-256. The `gitleaks-action` is not used: it refuses to run for
  organisation-owned repositories without a paid licence, and pinning the
  binary by digest is the stronger guarantee anyway.

## Two settings that live outside the repo

- **CodeQL default setup is disabled** on this repository. It was enabled
  before these workflows existed, ran a second, untunable analysis, and
  failed on the empty tree. `codeql.yml` replaces it and is reviewable like
  anything else. Re-enable default setup only if you delete `codeql.yml`;
  running both duplicates every alert.
- **Dependabot security updates** are enabled; `dependabot.yml` adds the
  version-update PRs on top. Its `pip` and `docker` blocks are commented out
  because an ecosystem with no manifest is a *scheduled error* on the
  Dependabot page, not a no-op. Uncomment them when `pyproject.toml` and the
  `Dockerfile` land — Dependabot will not add them back by itself.


## GitHub-hosted runners have no GPU

Every job here runs on `ubuntu-latest`, which has no CUDA device. Consequences
worth designing around:

- Unit tests must exercise the device layer through a fake/mock backend. A test
  that needs `torch.cuda.is_available()` to be true belongs nowhere in this
  pipeline.
- Container builds are CPU-only. A CUDA *base image* is fine; running a kernel
  in CI is not.
- Real GPU validation happens after deploy (the smoke test) or on a GPU runner
  you provision yourself. If you add a self-hosted GPU runner later, a manual
  `workflow_dispatch` workflow with `runs-on: [self-hosted, gpu]` is the right
  shape — do not put it on `pull_request`, or an arbitrary PR gets a GPU.

## What deploying requires

### Environments

Create `production` (Settings → Environments) and make it worth the name:

- **Required reviewers** — this is the control that stops `main` from rolling
  straight to live.
- **Deployment branches: `main` only.**
- Environment secrets: `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET`.

### Repository variables

| Variable | Required | Purpose |
| -------- | -------- | ------- |
| `DEPLOY_ENABLED` | yes, to deploy | `true` arms the deploy job. Anything else and CD builds and scans but ships nothing — deliberate, so a fresh repo cannot deploy by accident. |
| `MODAL_ENTRYPOINT` | no | Modal app file, default `app.py`. |
| `MODAL_ENVIRONMENT` | no | Modal environment name; unset means Modal's default. |
| `MODAL_CLI_VERSION` | recommended | Pins the Modal CLI. It runs with production credentials, so pin it. |
| `WORKER_HEALTH_URL` | recommended | Post-deploy smoke test target. Without it, the smoke test skips and nobody pretends otherwise. |

### Branch protection

The existing `main` ruleset already requires a PR, one approval, linear
history and no force-push. Add required status checks once the workflows have
run at least once:

```
CI / Lint & format
CI / Type check
CI / Tests
CI / Dependency audit (runtime)
CI / Secret scan (gitleaks)
PR Checks / Branch name
PR Checks / PR title (conventional commits)
PR Checks / Lockfile consistency
CodeQL / Analyze (python)
Security / Dependency review
```

Do not add `Scorecard` — it runs on `main`, not on PRs, so requiring it would
block every PR.

## Deliberate omissions from the web app repo

Ported in spirit, not by copy: the web app's `ci_evidence_guard.yml` exists
because a *conflicting* PR gets no `pull_request` run at all, leaving a fake
green rollup. That matters only when required status checks exist; this repo
has none yet, so the guard would be ceremony. Reconsider it at the same time
you turn on required checks.

Not ported at all, and why:

- **Discord notification workflows** (`pr_closure_notifier`,
  `pr_related_notification_scheduler`, `production_deployment_monitor`) — they
  track Vercel deployments for the web app. There is no Vercel here.
- **`version_bump.yml`** (semantic-release) — the web app ships a library-ish
  artifact where versions matter to consumers. A worker is deployed, not
  depended on; the image is tagged by commit SHA, which is a precise enough
  identity and needs no bot commit on a branch-protected `main`. If you later
  want released versions and a changelog, `python-semantic-release` is the
  Python-shaped equivalent.
- **`new_branch_flow.yml`** (auto-draft PR on branch create) — convenient, but
  it makes a PR the side effect of `git push` and creates noise for branches
  that never become PRs. `gh pr create` is one command.
- **PR size gate as a hard 500-line limit** — the web app has it commented out
  for good reason. Here: warn at 400, block at 1000, waivable with the
  `large-pr` label.

## Why actions are pinned to SHAs

A tag like `@v4` is movable: whoever controls the action's repository can point
it at new code, and that code runs with this repo's token and, in the deploy
job, production credentials. Pinning to a 40-character commit SHA is the only
version of "use v4" that cannot change underneath you. Dependabot updates the
pins weekly and writes the new SHA in the PR, so this costs nothing to
maintain.
