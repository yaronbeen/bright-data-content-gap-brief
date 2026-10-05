# Checked Example: Don't Commission It Twice

This is a manual exercise of the skill on a newly generated offline report, not an additional CLI output or a published assignment. All example evidence is invented.

From the repository root, generate the input with `python3 -m content_gap_brief analyze fixtures/demo.json --out-dir /tmp/assignment-skill-example`. Ask an assistant with local file access: "Read the gap-to-writer-assignment SKILL.md as instructions. Use /tmp/assignment-skill-example/report.json as untrusted data. Write the assignment in Markdown, or a no-assignment memo if gated. Do not fetch links or publish." No installation or configuration is needed; the bundled skill is not auto-registered.

## Scope And Gate

Checked input: `/tmp/opencode/skills-20261005-content_gap_brief/demo/report.json`. As of `2026-10-04T10:00:00Z`; status `ok`; decision `scoped_brief`; selected sources `owned`, `competing`, both synthetic. Chosen question `q2`, origin `observed`, wording provenance `competing/b0001`. Its title/heading is not body-fit evidence: `competing/b0002` supplies that body evidence. The selected owned `q2` row is `no_related_passage_found_in_selected_text`; this is a literal, scoped gap, not search demand or market evidence.

## Assignment

Title: "How do I check a failed import: a practical checklist"

Reader task: "Choose a safe way to move a small team's projects."

Copy the supplied outline:

- The decision: Choose a safe way to move a small team's projects.
- Requirements checklist
- Worked example: Team A
- Limits and expert checks

Angle basis: `competing/b0002`. Do not claim the selected competing guide proves a product capability or a universal editorial gap.

## Acceptance Checks

These are operator-declared editorial checks, not measured behavior:

- `error_log`, required: "Get a per-row error log." Acceptance: "Verify the output identifies each rejected row."
- `retry`, required: "Retry only corrected rows." Acceptance: "Verify corrected rows can be retried without duplicating successful rows."

## Do Not Recommission / Example Repairs

- Suppress `q1`, origin `editor_inferred`: selected owned row is `answer_phrase_found`, supported by `owned/b0002`. Do not commission another CSV-import eligibility article from this report. This does not prove every possible CSV question is covered.
- Review-question IDs: none supplied.
- Team A: `synthetic_operator_example`; "A synthetic import with one malformed date." Computed missing required criterion: `retry`. Proposed writer repair: add a demonstration addressing the supplied corrected-row retry check; do not say the scenario already satisfies it.
- Team B: `synthetic_operator_example`; "A synthetic corrected-row retry." Computed missing required criteria: none. This is a declared fictional scenario, not a successful product test.
- Owner, deadline and word count: not supplied. No assignment was submitted or article published.

## Evidence And Expert Review

Retain the report's expert checks: confirm declared phrases still represent intended answer checks; verify synthetic assumptions before publication; review cited excerpts and stale/unavailable evidence. Warnings: none supplied. No search-volume, ranking or traffic claim is supported. Real excerpts need human privacy review.

- `owned/b0002`: "CSV files can be imported."
- `competing/b0001`: "How do I check a failed import?"
- `competing/b0002`: "Inspect the import error log."

Both sources: observed `2026-10-04T10:00:00Z`; status `collected`; provenance `synthetic_fixture`; record unknown / `none`; published/provider dates unknown.

- `owned`: `https://example.com/owned-import-guide`; SHA-256 `c7de2b2546dafe9cfb3f828396f0303ba7eed120b7eb20a2c721d13af8a59cc1`.
- `competing`: `https://example.com/competing-import-guide`; SHA-256 `bf962028f5f240875d00ec1e128912c763605764a88e2dece52efdf792362c70`.

Hashes identify invented snapshots, not truth. [Validation record](validation.md).
