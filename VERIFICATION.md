# Verification

Last updated: 2026-10-05.

## Verified Locally

- All tests run with no provider credentials and injected transports only.
- The offline fixture creates a populated scoped brief with byte-stable JSON, Markdown, and CSV.
- The future distribution name is `content-gap-brief`; the import module and CLI remain `content_gap_brief` and `content-gap-brief`.
- Live page manifests reject query strings. Credential/signature query keys are rejected in every URL mode after decoding and normalization.
- Console plans and analysis artifacts redact query values; private approvals continue to bind the exact canonical manifest hash.
- Cumulative retained-record limits stop later calls and count excluded provider rows.
- Imported/collected source libraries contain no query-bearing page or SERP-result URLs; page imports reject them and SERP result normalization excludes them before persistence.
- SERP sources and rank metadata survive invalid/duplicate filtering as one atomic normalization result.
- Imported and live search-result source records carry allowlisted `metadata.serp_rank` / `metadata.serp_global_rank`; live job receipt ranks are generated atomically from the same retained records.
- Any embedded HTML tag/comment/script/style region causes `unsupported_content_format`; no markup contents are analyzed as visible text.
- Markup-bearing SERP descriptions are excluded as records, preserving the following retained source/rank mapping.
- Page import and collection reject output over 50,000 characters.
- Monotonic request/overall deadlines are enforced by a killable worker process around the entire synchronous transport/body read; slow custom transport and local slow-drip HTTP regressions are covered and late operations become `completion_unknown`.
- Live collection fails closed in multithreaded callers and where the platform lacks `fork`.
- Web Unlocker accepts raw Markdown and validates the documented JSON `{status_code, headers, body}` success envelope; malformed and embedded target-error envelopes return safe failure receipts.
- Malformed percent escapes in approval URLs become structured validation errors; unpaired Unicode in SERP records is safely excluded.
- URL splitting, port/hostname/userinfo extraction, and URL reconstruction translate ValueError/UnicodeError into `ValidationError`; regression coverage includes a simulated UnicodeError from `.hostname` and a malformed Unicode authority through the CLI.
- Remaining deadline budget is floored to integer timeout seconds; with under one second left, the next call is not started.
- Three-file report output rolls back on failure and preserves a racing no-clobber destination.
- Markdown scalars are rendered as inert single-line text.

## Commands

```bash
python3 -m pytest -q
python3 -m compileall -q content_gap_brief
python3 -m content_gap_brief analyze fixtures/demo.json --out-dir /tmp/content-gap-brief-security-demo
```

Build/install verification uses a locally built wheel and a fresh virtual environment with no runtime dependencies. Exact final command output is recorded in the latest handover.

## Final Evidence

- `python3 -m pytest -q`: `130 passed in 3.72s`.
- Current wheel: `content_gap_brief-0.1.0-py3-none-any.whl`, SHA-256 `d579f9a0e5567f6b06d607a96e766df444573320a98ba28de511697b18e38de6`.
- Regression tests verify query-bearing page import URLs are rejected, query-bearing SERP result URLs are excluded from imported/collected libraries, and no query value reaches source-library serialization.
- Sub-second deadline budget test verifies no timeout is rounded upward and no extra request starts.
- Fresh virtualenv install: `Successfully installed content-gap-brief-0.1.0`; `pip check`: `No broken requirements found.`
- Installed CLI: `content-gap-brief 0.1.0`.
- Installed happy-path and no-candidate JSON, Markdown, and CSV matched the checked-in golden artifacts byte-for-byte using `cmp`.
- Installed console syntax failure returned JSON code `invalid_arguments`, no stdout, and exit `2`.
- README example hash/approved-target, source URL query policy, exit-code, deadline, synthetic import, and canonical docs assertions passed.
- README HTML-rejection and SERP source-rank metadata assertions passed.
- Slow custom-transport cancellation, local slow-drip response-body cancellation, and fail-closed fork/thread-context tests passed.
- Provider-import `role=[]` direct API input raises `ValidationError`; CLI `--role []` returns structured JSON exit `2` without traceback or output artifact.
- Malformed-percent approval URL regression returns structured exit `2` before transport; unpaired Unicode SERP response is excluded without encoding traceback.
- Credential/private-key/AWS/GitHub-token scans returned no matches.
- README exit-code documentation matches the implemented collection mapping: confirmed `failed` receipt -> `3`; `partial`, `pending`, or `completion_unknown` -> `4`.
- Collection/import single-file output uses atomic no-clobber; local write failures after collection preserve the known `requests_made` in structured JSON errors.
- Canonical Web Unlocker and SERP API-reference URLs without `.md` suffix were fetched successfully on 2026-10-05.
- Python 3.11 was not installed locally; package metadata and CI are bounded to 3.11-3.12, while the final local build/install ran on Python 3.12.
- Current verification artifacts are under `/tmp/content-gap-brief-unicode-wheels`, `/tmp/content-gap-brief-unicode-venv`, `/tmp/content-gap-brief-unicode-demo`, and `/tmp/content-gap-brief-unicode-no-candidate`.

## Independent Reviews (2026-10-05)

- QA: **SHIP** on the latest revision after the malformed-Unicode fix. The matching local regression evidence is in `tests/test_qa_regressions.py` and `tests/test_security_regressions.py` (malformed Unicode authority/hostname cases, including structured CLI failure without a traceback). The reviewer report artifact path was not present in this checkout; this disposition is recorded from the final reviewer result supplied in the session.
- Security: **APPROVE** on the latest implementation. The corresponding local security regression evidence is in `tests/test_security_regressions.py`; URL parser/hostname/reconstruction guards are in `content_gap_brief/brightdata.py`. The reviewer report artifact path was not present in this checkout; this disposition is recorded from the final reviewer result supplied in the session.
- Bright Data brand: **APPROVE** on the latest documented Web Unlocker envelope. Contract evidence is the documented `{status_code, headers, body}` adapter validation in `content_gap_brief/brightdata.py`, its malformed/embedded-error cases in `tests/test_security_regressions.py`, and the documented contract in this file above. This is approval of the documented envelope, not confirmation of live provider behavior. The reviewer report artifact path was not present in this checkout; this disposition is recorded from the final reviewer result supplied in the session.
- These latest-revision dispositions supersede stale outstanding-review claims in the local status record. Earlier handover entries describe the review status at their own dates and are historical, not the latest disposition.

## Not Verified

- No live Bright Data call was made.
- Provider account access, zones, billing, actual response shape, remote DNS resolution, provider-side redirect behavior, and final destination are not verified.
- The documented Web Unlocker envelope is mocked and verified; no real target request was made.
- Local request/retention caps do not prove or enforce provider spend.
- Reviewer approval does not verify live provider behavior, account access, billing, zones, redirects, DNS resolution, or final destination; these remain unverified.
