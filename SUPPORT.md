# Support

This is the OpenPic face-pipeline worker. It runs on third-party GPU hosts and
talks to the control plane; it is not a public service, and it is not a library
you install.

## Where to go

| You need | Go to |
| -------- | ----- |
| Report a bug in the worker | [Open a bug report](https://github.com/yahodu/openpic-worker/issues/new?template=bug_report.md) |
| Request a behaviour change | [Open a feature request](https://github.com/yahodu/openpic-worker/issues/new?template=feature_request.md) |
| Ask how something works | [Open an issue](https://github.com/yahodu/openpic-worker/issues/new) with the `question` label, or ask in the relevant pull request |
| Report a vulnerability | [Private security advisory](https://github.com/yahodu/openpic-worker/security/advisories/new) — never a public issue; see [`SECURITY.md`](SECURITY.md) |
| Understand the contract | [`docs/API Contract.md`](docs/API%20Contract.md), then the flow document for the area |
| Understand why something is the way it is | [`docs/adr/`](docs/adr/README.md) |
| Contribute a change | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| License or commercial use | <https://openpic.in> |

## Before you file

- **Check the open issues and pull requests.** A pipeline failure usually has an
  existing report; add your evidence there.
- **Bring the evidence.** The commit SHA the worker was built from, which backend
  (Modal or vast.ai), the queue (`q:selfie` or `q:image`), the work-item id if you
  have it, the log event names and the error code from the contract's taxonomy
  (§10.3.3) — with secrets, embeddings, object keys and signed URLs removed.
- **Do not paste a `.env`, a token, a connection string or a signed URL.** If a
  secret may have leaked, treat it as a vulnerability and use the private
  advisory channel.

## What support is not

There is no SLA, no hosted instance and no guarantee that an issue will be
implemented. Contributions are accepted from contributors the owner has added to
the repository ([`CONTRIBUTING.md`](CONTRIBUTING.md) §1).
