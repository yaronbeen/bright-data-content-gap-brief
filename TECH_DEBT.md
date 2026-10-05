# Technical Debt

## P0 (Next Session)

- None. Latest-revision reviewer dispositions dated 2026-10-05 are recorded in `/home/yaron/projects/bright-data-content-gap-brief/VERIFICATION.md`; live provider behavior and publication authorization remain separate, unverified matters.

## P1 (This Week)

- Add broader recording-transport tests for every failure header and redirect behavior before calling the live adapter verified.
- Confirm the selected raw Web Unlocker response contract with an explicitly authorized, budgeted smoke test.

## P2 (When Convenient)

- Add property-based validation tests if the runtime dependency policy changes.

## P3 (Nice To Have)

- Add richer operator guidance for authoring narrow answer phrases without implying semantic coverage.

## Resolved Items

- 2026-10-05: Implemented the deterministic candidate eligibility contract and offline CLI artifacts.
- 2026-10-05: Added cumulative retention enforcement, normalized URL credential rejection/redaction, atomic SERP/rank normalization, 50,000-character page limits, monotonic deadlines, and transactional report output.
- 2026-10-05: Preserved ATX headings through collection/import, rejected Setext headings, tightened nested/library validation, retained observed-question citations, added structured argparse errors, and added exact-byte positive/no-candidate goldens.
- 2026-10-05: Deduplicated the brand-review retention/rank P1 findings against the already resolved cumulative-retention and atomic SERP/rank security work; they are not tracked as separate debt.
- 2026-10-05: Added atomic no-clobber to collection/import output, preserved actual request counts on local receipt-write failure, and hardened malformed manifest/transport-error validation.
- 2026-10-05: Excluded SERP records whose generated IDs collide with retained page IDs, keeping the matching rank row excluded in the same normalization pass.
- 2026-10-05: Rejected query-bearing provider page URLs and excluded query-bearing SERP result URLs before source-library persistence; removed deadline timeout ceiling rounding and skip calls with under one second remaining.
- 2026-10-05: Rejected HTML markup anywhere in source text and stored organic/global SERP ranks in allowlisted source metadata for both import and collection, with the live job-level rank summary retained.
- 2026-10-05: Rejected inline HTML/comment/script/style/declaration markup anywhere in source text and attached allowlisted organic/global SERP ranks to retained search-result source metadata for both import and live collection.
- 2026-10-05: Enforced monotonic transport/body deadlines by running synchronous transports in killable workers; live collection fails closed without `fork` or from a multithreaded caller.
- 2026-10-05: Recorded final independent latest-revision dispositions: QA SHIP after malformed-Unicode fix; Security APPROVE; Bright Data brand APPROVE of the documented envelope. Reviewer report artifact paths were not available in this checkout; see `/home/yaron/projects/bright-data-content-gap-brief/VERIFICATION.md` for the session-supplied verdicts and corroborating local evidence. These approvals do not establish live provider behavior.
- 2026-10-05: Provider export role values are type-checked before enum membership; CLI regression verifies structured JSON exit `2` for malformed role input.
- 2026-10-05: Accepted validated documented Web Unlocker `{status_code, headers, body}` envelopes while retaining raw Markdown; malformed approval URL escapes and provider Unicode now become safe validation/provider failures.
- 2026-10-05: Wrapped URL parser/hostname/reconstruction ValueError and UnicodeError failures into `ValidationError`; added CLI no-traceback coverage for malformed Unicode authorities.
- 2026-10-05: Accepted and validated the documented Web Unlocker JSON response envelope while retaining raw Markdown; malformed approval percent escapes and malformed provider Unicode now stay within structured failure handling.
- 2026-10-05: Enforced monotonic transport/body deadlines by running synchronous transports in killable workers; live collection fails closed without `fork` or from a multithreaded caller.
