# Handover 004

Date: 2026-10-05

## What Was Done

- Added regression tests for query-bearing imported page URLs, imported SERP results, and collected SERP results; serialized libraries are asserted not to contain the query values.
- Added a monotonic-deadline regression proving a sub-second remaining budget causes no new request.
- Rejected query-bearing page import URLs and excluded query-bearing SERP result URLs before source-library persistence. SERP query URLs used as discovery request context are not persisted.
- Replaced upward timeout rounding with floor-to-seconds behavior; when less than one second remains, collection marks remaining jobs `not_attempted`.
- Updated README, verification, learnings, technical debt, and the collection security solution note.
- Addressed QA re-review: source text containing embedded HTML tags/comments/script/style/declarations is rejected anywhere; SERP ranks persist as allowlisted `source.metadata` on imported and live source records, with aligned live job-level rank metadata.

## Current State

- Full test suite: `103 passed in 0.35s`.
- Current wheel SHA-256: `9fd2e287832cd890d1413db8954042fa3e085dd61ab5189dabc8d063bd90e59c`; fresh virtualenv install, `pip check`, and happy/no-candidate golden comparisons passed.
- README contract assertions and credential/private-key/AWS/GitHub-token scans passed.
- No live provider call, remote repository operation, push, or publication occurred.

## Open Issues / Blockers

- Independent security re-review remains P0; attempts to dispatch security, QA, and brand agents are blocked by the session subagent-depth limit.
- Python 3.11 is unavailable locally; CI metadata covers Python 3.11 and 3.12, local verification uses Python 3.12.
- Provider access, zones, billing, response shape, redirects, DNS resolution, and final destination remain unverified.

## Next Steps

1. Rebuild the final wheel after the documentation-only README adjustment, rerun all tests and byte comparisons, and update exact build evidence.
2. Run independent security, QA, and brand review in a fresh review-capable session.
3. Do not make paid requests or publish before approval and explicit authorization.

## Decisions Made

- Query-free retained source URLs take precedence over preserving SERP result tracking parameters.
- Never round remaining deadline time upward to fit an integer transport timeout.
