# Changelog

All notable changes to the worker are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the entries are
written for whoever operates the pipeline, not for whoever wrote the diff.

## How this file is maintained

- **Add the bullet in the PR that makes the change**, under `Unreleased`. If a
  change is not worth a line here, it is probably not worth a separate PR.
- Group under **Added**, **Changed**, **Fixed**, **Removed**, **Security**.
- Say what is observable: the queue, the collection, the report body, the log
  event, the environment variable. Not "refactored the claim path".
- **Releases are milestones, not artifacts.** The container image is tagged by
  commit SHA and deployed through the `production` environment, so there is no
  version-bump bot and no tag-driven release (see
  [`.github/CI-CD.md`](.github/CI-CD.md)). The owner cuts a dated heading when a
  deploy-worthy milestone lands; `git log main` remains the authoritative history.
- Never rewrite a released section. A correction is a new bullet under
  `Unreleased`.

## [Unreleased]

### Added

- Repository documentation set: `LICENSE`, `CONTRIBUTING.md`, `AGENTS.md`,
  `CODE_OF_CONDUCT.md`, `SECURITY.md`, `SUPPORT.md`, the ADR ledger and template.

### Changed

### Fixed

### Removed

### Security
