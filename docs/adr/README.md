# Architecture Decision Records

An ADR is a short, dated record of a decision that is expensive to reverse: the
forces at play, the choice made, and what it costs. It is not a design document
and not a tutorial — it exists so that the next person does not have to guess why
an obvious-looking alternative was rejected.

`docs/CONVENTIONS.md` §12 is normative for numbering and landings; this file is
the ledger it refers to.

## Ledger

The worker is being rebuilt from an empty tree, so no record has been accepted
yet. The first accepted ADR adds its row here, in the same pull request as the
record.

| ADR | Title | Status | Date |
| --- | ----- | ------ | ---- |
| —   | No records accepted yet | — | — |

**Next free: 0008** — informational only. Never derive a number from this cell;
see *Allocation* below.

## Reserved numbers

These numbers are already spoken for by the open contract questions in
`docs/CONVENTIONS.md` §11.1. They are **not** records yet: the card that resolves
each question mints the record and adds its ledger row together. Do not take one
for unrelated work, and do not renumber them.

| ADR | Reserved for | Owner |
| --- | ------------ | ----- |
| `ADR-0004` | Q1 — the worker emits no domain events; the report route publishes every outcome | card resolving §11.1 Q1 |
| `ADR-0007` | Q2a/Q2b — `match_incremental` projection ownership, and the incremental watermark lookback | card resolving §11.1 Q2a/Q2b |

## Naming

```
docs/adr/ADR-NNNN-lowercase-slug.md
```

- `NNNN` is four digits, zero-padded. This repository's reserved range is
  `0001`–`0999`; a record above `0999` needs a new range row here first.
- The slug is lowercase words joined by hyphens, no dates, no ticket numbers, no
  author names.
- The number in the filename must equal the `Consumes` value recorded in the
  card. A mismatch is returned by the reviewer, not worked around.

## Allocation

1. **Reserve at card creation, never derive at branch cut.** The allocator writes
   `**Consumes: NNNN**` into the card body (`none` for a card that mints no
   number). The worker takes the number as given — it never reads the ledger tail,
   the `Next free` cell, or the highest file on disk.
2. Allocation is **in-flight aware**: it accounts for live worktrees, all objects
   reachable from `docs/adr`, `Consumes` values on non-`done` cards, and every
   open PR head. An unpushed local commit is invisible to a remote listing, which
   is why the open-PR sweep is not optional.
3. A card whose `Consumes` is missing or `TBD` blocks. It never invents a number.

## Landing rules

- **One record and one ledger row, in the same PR.** A record without a row, or a
  row without a record, is a Definition of Done failure.
- **Never edit an accepted record.** Supersede it: write a new ADR, set the old
  one's status to `Superseded by ADR-NNNN`, and update its ledger row.
- **The note mirrors the record.** Amending a record amends its row in the same
  PR. A deliberately historical statement belongs inside the record, dated.
- **Index-only conflicts resolve as a union.** Keep both sides' rows in ascending
  order, then set `Next free` to `max(consumed) + 1`. Never pick a side: a
  pick-a-side resolution silently drops a row.
- **Merge-time collision sweep.** The merging agent confirms the number the PR
  adds appears at no other open PR head (conventions §10.1, G7). A hit is a
  failure; the lander renumbers its own unmerged record and re-runs.
- **The guard** is `tests/unit/test_adr_numbering.py`. It fails on a duplicate
  `ADR-NNNN` prefix or a malformed `ADR-*.md` name. It does not check lane ranges
  or `origin/main` — those stay review-time obligations.
- **Citations across repositories are qualified**: `openpic-webapp ADR-0318`,
  never a bare `ADR-0318`, because both repositories have a `0318`.

## Record shape

Start from [`template.md`](template.md). The four sections are mandatory:

1. **Context** — the forces, the constraint, the evidence (file and line
   references where behaviour is the evidence).
2. **Decision** — what the worker does now, stated so a test can be written
   against it.
3. **Consequences** — what becomes easier, what becomes harder, what is now
   forbidden, and how the decision would be reversed.
4. **Alternatives** — what was considered and why it lost. This is the section
   that saves the next reader the most time; an empty one is a warning sign, not
   a shortcut.

Accepted records are immutable in substance. A correction of fact is allowed only
as a dated amendment inside the record; anything else is a superseding ADR.
