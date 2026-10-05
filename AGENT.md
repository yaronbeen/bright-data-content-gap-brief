# Agent Guide

## Start Here

Read the latest file in `/home/yaron/projects/bright-data-content-gap-brief/handover/`, review P0 items in `/home/yaron/projects/bright-data-content-gap-brief/TECH_DEBT.md`, and skim `/home/yaron/projects/bright-data-content-gap-brief/LEARNINGS.md` before changing code.

## Purpose & Context

This Python 3.11+ CLI compares operator-declared literal answer checks against selected owned and competing article snapshots. It creates a cited checklist brief only when owned coverage is sufficiently resolved and a competing body passage plus question criteria support the assignment. It is offline-first and deterministic; optional Bright Data retrieval is explicitly gated.

## Architecture / Design

```
JSON input -> core validation/normalization -> coverage rows -> candidate decision
                                                     |-> JSON / Markdown / CSV
approved manifest -> Bright Data adapter -> source library -> explicit --sources
```

`core.py` is pure. `export.py` only renders reports. `brightdata.py` owns provider DTOs, validation, normalization, and HTTP. `cli.py` owns environment and atomic files.

## Decisions Log

| Date | Decision | Rationale |
| --- | --- | --- |
| 2026-10-05 | Use deterministic literal phrase checks only | Keeps every conclusion reproducible and exposes unsupported semantic cases. |
| 2026-10-05 | Keep retrieval optional and two-pass | A SERP result never authorizes a destination-page request. |
| 2026-10-05 | No scraper-job resume support | This project enables only synchronous Web Unlocker and SERP jobs. |
| 2026-10-05 | Publish under `content-gap-brief` | Keep the future distribution/repository brand-neutral while optional Bright Data retrieval remains an adapter. |
| 2026-10-05 | Redact public query values | Private approval hashes exact inputs; console plans and reports must not expose query values. |
| 2026-10-05 | Commit report files transactionally | A failure or no-clobber race must not leave a mixed three-file report set. |

## Runbook / Operations

- Test: `python3 -m pytest -q`
- Offline demo: `python3 -m content_gap_brief analyze /home/yaron/projects/bright-data-content-gap-brief/fixtures/demo.json --out-dir /tmp/content-gap-brief-demo`
- Safe plan: `python3 -m content_gap_brief collect MANIFEST --out LIBRARY --dry-run`
- Never run live collection without exact approval, account budget confirmation, target permission, API key, and required zones.

## API References

- Bright Data Web Unlocker API reference: https://docs.brightdata.com/api-reference/rest-api/unlocker/unlock-website
- Bright Data SERP API reference: https://docs.brightdata.com/api-reference/rest-api/serp/serp-api
- Adapter contract reviewed in the build contract dated 2026-10-04; live response shape remains unverified.

## Project File Structure

- `/home/yaron/projects/bright-data-content-gap-brief/content_gap_brief/`: runtime package.
- `/home/yaron/projects/bright-data-content-gap-brief/tests/`: contract and implementation tests.
- `/home/yaron/projects/bright-data-content-gap-brief/fixtures/`: invented offline inputs and provider-shaped examples.
- `/home/yaron/projects/bright-data-content-gap-brief/fixtures/expected/`: verified generated demo outputs.
- `/home/yaron/projects/bright-data-content-gap-brief/handover/`: session state.

## References

See `/home/yaron/projects/bright-data-content-gap-brief/LEARNINGS.md`, `/home/yaron/projects/bright-data-content-gap-brief/TECH_DEBT.md`, and the latest numbered handover.
