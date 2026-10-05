# Collection Security Boundary Hardening

## Problem

The optional collection adapter enforced several limits per job rather than across the run. URL credential checks were narrow, SERP ranks were attached after record filtering, successful late responses could be trusted, and the CLI wrote its three report files independently.

## Symptoms

- A run could retain more records than `max_retained_records` by combining page and SERP jobs.
- Percent-encoded signed URL parameters were not consistently rejected and query values appeared in public plans/reports.
- Invalid or duplicate SERP rows shifted rank metadata onto the wrong retained source.
- A paid page longer than the analysis schema limit could be retained but fail later analysis.
- A response arriving after the intended timeout could be interpreted as success.
- A filesystem failure could leave a mixed or partially overwritten report set.

## Failed Approach

Per-job caps, a short exact sensitive-key set, zipping retained sources with the original SERP array, relying only on the transport timeout, and three calls to an individually atomic writer each covered the happy path but did not enforce the end-to-end invariants.

## Solution

- Track cumulative retained capacity before each call and pass only remaining capacity into the SERP normalizer.
- Normalize SERP source and rank rows in one filtering loop; count invalid, duplicate, and over-cap rows as excluded.
- Repeatedly percent-decode query keys, apply NFKC normalization/case folding, remove separators, and reject credential/signature keys in all modes. Reject every query string on live page targets.
- Keep the private manifest hash exact while redacting query values from console plans, receipt job fields, and analysis URLs.
- Apply the 50,000-character page limit at import and immediately after paid retrieval.
- Bound each call and the run with an injected monotonic clock; discard late responses as `completion_unknown`.
- Stage all report files under an exclusive lock. Use atomic hard links for no-clobber commits and backup/restore for overwrite commits.
- Collapse Markdown scalar whitespace before escaping delimiters.
- Reject query-bearing page source URLs and exclude query-bearing SERP result URLs before writing imported/collected source libraries. The SERP query endpoint URL is request context only and is not persisted.
- Floor the remaining monotonic deadline to integer seconds; if under one second remains, mark jobs not attempted rather than ceiling-rounding into an overrun.

## Root Cause

The first implementation treated transport, normalization, retention, and file output as independent helpers. Security properties such as budgets, metadata alignment, deadlines, and transactional publication are run-level invariants and cannot be established by isolated per-item checks.

## Prevention

Maintain regression tests for mixed job sequences, encoded credential keys, invalid/duplicate SERP ordering, late successful responses, over-limit paid pages, output commit failures, and destination races. Keep live collection and publication blocked until independent security re-review.
