# Security policy

## Reporting a vulnerability

Do **not** open a public issue for a security problem. Use GitHub's private
vulnerability reporting:

<https://github.com/yahodu/openpic-worker/security/advisories/new>

Include what you can: affected component, reproduction steps, and the impact
you believe it has. You will get an acknowledgement, and credit in the advisory
once a fix is available unless you ask otherwise.

## What this repository handles

This worker runs on third-party GPU hosts (Modal, vast.ai) and therefore holds
credential material that is worth more than the code itself:

| Secret | Scope | Turns up in |
| ------ | ----- | ----------- |
| `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET` | `production` environment only | CD deploy job |
| `VAST_API_KEY` | host provisioning, not in CI | control plane |
| Database / queue credentials | per-environment | `.env` on the host, never the repo |

Rules that follow from that:

- No credential ever enters the repository or a log line. `.env.example` holds
  names and placeholder values, nothing else.
- Only the deploy job sees `MODAL_TOKEN_*`, and only after the `production`
  environment approval. No `pull_request`-triggered workflow in this repo has
  access to environment secrets, so a malicious PR from a fork cannot reach
  them.
- Workflow actions are pinned to full commit SHAs, not tags, because a movable
  tag on a third-party action is remote code execution with your token.

## Scope

In scope: this repository's code, its container image, and its CI/CD
configuration. Out of scope: vulnerabilities in Modal or vast.ai themselves
(report those to the respective vendor), and findings that require
already-compromised credentials.
