# 1. Record architecture decisions

Date: 2026-07-24

## Status

Accepted

## Context

Architectural decisions in redsun (storage lifecycle, container build phases,
device/presenter wiring) have so far lived in chat transcripts, agent memos
under `.claude/agents/`, and code comments. Contributors and agents need a
public, durable record of *why* the architecture is shaped the way it is,
especially across breaking rewrites.

ophyd-async — whose device model redsun builds on — keeps Architecture
Decision Records under `docs/explanations/decisions/`, following the format
described in [Michael Nygard's blog](http://thinkrelevance.com/blog/2011/11/15/documenting-architecture-decisions).

## Decision

We will keep ADRs in `docs/explanation/decisions/`, numbered sequentially,
using the same lightweight format as ophyd-async (see `COPYME`): Status,
Context, Decision, Consequences. New architectural changes get a new ADR;
superseded ADRs are marked as such rather than edited.

## Consequences

- Design work that changes architecture lands as an ADR before (or with) the
  implementation.
- `.claude/agents/` memos and CLAUDE.md summarise and link to ADRs instead of
  being the primary record.
- ADR pages are wired into the zensical nav under Explanation → Decisions.
