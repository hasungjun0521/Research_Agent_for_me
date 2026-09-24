# ADR-002: Use Reusable Venue Review Forms

## Status
Accepted

## Date
2026-05-09

## Context
The workspace already supports reviewer-style critique through the critic agent, but venue review forms differ by conference, journal, year, and track. A generic critique can miss required fields such as confidence, ethical concerns, reproducibility checks, score anchors, or decision values.

## Decision
Store reusable venue/year forms in `review_forms/` and project-specific form reviews in `projects/<project>/07_reviews/form_reviews/`. Register forms in `review_forms/form_registry.json` and create review files with `scripts/commands/review/review_forms.py create-review`.

## Alternatives Considered

### Store Forms Only In Each Project

This keeps project folders self-contained, but it duplicates common venue forms across projects and makes it harder to maintain exact venue/year variants.

### Put Form Instructions Only In The Critic Prompt

This is simpler, but it does not preserve the exact form text, score anchors, or year-specific policy fields. It also makes it harder to audit which form was used.

## Consequences

- Venue review forms can be reused across projects.
- The `venue_reviewer` agent fills exact form fields instead of producing generic critique.
- Generated reviews include form id, venue, year, track, form path, score table, and evidence requirements.
- Private or copyrighted forms must be handled carefully; if needed, store only field summaries and score anchors.
