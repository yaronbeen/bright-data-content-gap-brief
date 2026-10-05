# Handover 005

Date: 2026-10-05

## What Was Done

- Added test-first regressions for embedded HTML tags/comments/scripts/styles anywhere in source text.
- Added source metadata rank tests for both offline SERP import and live SERP collection, including invalid and duplicate records; live job-level `result_ranks` is asserted to match retained sources.
- Rejects any HTML markup opener/region anywhere in page text as `unsupported_content_format`; markup-bearing SERP descriptions are excluded without shifting later ranks.
- SERP `search_result` sources now carry only allowlisted `metadata.serp_rank` and `metadata.serp_global_rank`, each positive integer or null.
- Synchronous transports now execute inside a killable worker process; request and response-body work is terminated at the absolute monotonic deadline. Live mode refuses multithreaded callers and platforms without `fork` before sending requests.
- Added slow custom-transport cancellation and local slow-drip HTTP body tests.
- Synchronous transports now execute inside a killable worker process; request and response-body work is terminated at the absolute monotonic deadline. Live mode refuses multithreaded callers and platforms without `fork` before sending requests.
- Added slow custom-transport cancellation and local slow-drip HTTP body tests.
- Updated README and provider contract documentation to clarify the markup rejection and rank representation.

## Current State

- Full suite: `115 passed in 0.33s` on the latest run.
- Wheel SHA-256: `4f1fc9d7d76d2f3a7e6e3c781e21934cc3dd60a0694d1d53d2134011b0980a44`.
- Fresh isolated wheel installation, `pip check`, installed CLI, and happy/no-candidate golden byte comparisons passed.
- No live provider calls, remote operations, pushes, or publication occurred.

## Open Issues / Blockers

- Independent security re-review remains P0. Reviewer-agent dispatch is still blocked by session subagent-depth limits; local regression testing is not independent approval.
- Python 3.11 is unavailable locally. The package/CI target Python 3.11 and 3.12; build verification ran under Python 3.12.
- Live provider access, billing, zones, response shape, remote redirects, DNS resolution, and final destination remain unverified.

## Next Steps

1. Run separate security, QA, and brand reviews in a fresh review-capable session.
2. Resolve any further findings test-first and rerun tests/build/install/docs verification.
3. Do not make paid requests or publish before explicit authorization and reviewer approval.

## Decisions Made

- Reject rather than strip HTML so markup text cannot become unverified body evidence.
- Use `source.metadata.serp_rank` and `source.metadata.serp_global_rank` for per-source organic/global rank; keep live job-level ranks generated from the same normalized retained rows.
