# Content Gap Brief

> **Synthetic demonstration:** This report contains invented fixture data, not market evidence.

**Decision:** `scoped_brief`
**Status:** `ok`
**Method:** `deterministic_rules_v1`

## Bounded scope

Topic: Choosing a project import method
Reader task: Choose a safe way to move a small team's projects.
Selected sources: `owned`, `competing`

## How do I check a failed import: a practical checklist

Reader decision: Choose a safe way to move a small team's projects.

### Requirements checklist

- **Get a per\-row error log.** (required): Verify the output identifies each rejected row.
- **Retry only corrected rows.** (required): Verify corrected rows can be retried without duplicating successful rows.

### Worked examples

- **Team A:** A synthetic import with one malformed date. Missing required checks: retry.
- **Team B:** A synthetic corrected\-row retry. Missing required checks: none.

### Limits and expert checks

- Confirm declared phrases still represent the intended answer checks.
- Verify synthetic example assumptions before publication.
- Review cited source excerpts and any stale or unavailable evidence.

## Coverage evidence

- `q1` / `owned`: `answer_phrase_found`. Quote: "CSV files can be imported."
- `q1` / `competing`: `no_related_passage_found_in_selected_text`.
- `q2` / `owned`: `no_related_passage_found_in_selected_text`.
- `q2` / `competing`: `answer_phrase_found`. Quote: "Inspect the import error log."

## Question provenance

- `q2` How do I check a failed import? Observed question source: `competing/b0001` "How do I check a failed import?"

## Evidence appendix

- `owned/b0002`: "CSV files can be imported." (https://example.com/owned\-import\-guide; observed 2026-10-04T10:00:00Z; SHA-256 `c7de2b2546dafe9cfb3f828396f0303ba7eed120b7eb20a2c721d13af8a59cc1`)
- `competing/b0002`: "Inspect the import error log." (https://example.com/competing\-import\-guide; observed 2026-10-04T10:00:00Z; SHA-256 `bf962028f5f240875d00ec1e128912c763605764a88e2dece52efdf792362c70`)
- `competing/b0001`: "How do I check a failed import?" (https://example.com/competing\-import\-guide; observed 2026-10-04T10:00:00Z; SHA-256 `bf962028f5f240875d00ec1e128912c763605764a88e2dece52efdf792362c70`)

## Limitations

Coverage means literal declared-phrase checks or a labeled human override within selected snapshots. It is not semantic SEO analysis, search demand, internet-wide coverage, or an outcome forecast.
