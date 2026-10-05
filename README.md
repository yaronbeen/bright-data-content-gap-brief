# Content Gap Brief

**Do not commission the article you already have.**

The future distribution and repository name is brand-neutral: `content-gap-brief`. An existing checkout may keep its legacy local folder name until a separately reviewed migration or publication.

Content Gap Brief checks a small, explicitly selected set of owned and competing article snapshots. It suppresses questions already answered by declared literal checks, surfaces uncertain owned coverage for review, and creates a cited assignment only when a real competing body passage and an operator-defined checklist support it.

The invented demo suppresses `Can I import a CSV file?` because the selected owned page says `CSV files can be imported.` It proposes this assignment for the remaining question:

```text
How do I check a failed import: a practical checklist

- Get a per-row error log. (required)
- Retry only corrected rows. (required)
- Team A is missing: retry
- Team B is missing: none
```

That is a scoped editorial candidate, not proof of search demand, ranking potential, or an internet-wide content gap.

## Offline Quickstart

Requirements: Python 3.11 or 3.12. Runtime dependencies: none.

```bash
cd /path/to/content-gap-brief
python3 -m content_gap_brief --version
python3 -m content_gap_brief analyze fixtures/demo.json --out-dir /tmp/content-gap-brief-demo
```

The module command works directly from the repository without installation, credentials, or network. It writes:

- `report.json`: complete structured decision, coverage rows, citations, hashes, scope, and warnings.
- `brief.md`: reviewable brief or an actionable coverage-review/already-covered result.
- `coverage.csv`: one fixed-schema question/page coverage row per selected article.

For an installed CLI:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/content-gap-brief analyze fixtures/demo.json --out-dir /tmp/content-gap-brief-installed
```

Use `--dry-run` to validate an analysis without writing reports. The three report files are staged and committed as one lock-protected set. Without `--overwrite`, atomic no-clobber links prevent a race from replacing an existing file; a failed commit removes only files created by that transaction. With `--overwrite`, existing files are backed up and restored if the new set cannot be committed.

## What It Decides

Coverage uses only operator-declared phrases and hash-bound overrides:

- `answer_phrase_found`: an exact answer phrase appears in an article body block.
- `related_passage_only`: a related phrase appears, but the declared answer check does not.
- `no_related_passage_found_in_selected_text`: no declared phrase appears in that selected snapshot.
- `unavailable`: the selected source cannot support either a positive or absence conclusion.
- `operator_confirmed_covers` / `operator_confirmed_does_not_cover`: an explicit human decision tied to the exact source SHA-256; coverage requires body evidence.

Titles and Markdown headings never establish coverage or competing-article fit by themselves. ATX headings (`#` through `######`) are preserved through provider import/collection. Setext headings are explicitly rejected rather than risk treating their text as body evidence. Matching is case-insensitive, phrase-boundary based, and does not stem, translate, fuzzy-match, or infer synonyms. Any HTML tag, comment, declaration, processing-instruction opener, or document markup anywhere in source text is rejected as `unsupported_content_format`; inline markup is not stripped and cannot become phrase evidence.

A question is eligible only when:

1. All selected owned pages support a scoped gap rather than unresolved related/unavailable evidence.
2. At least one criterion belongs to the question.
3. A selected competing article contains a related or answer phrase in a body block.

The first eligible question in input order wins. If none qualifies, the tool returns `coverage_review_required` and preserves the rows needed to resolve it. It never manufactures an assignment to fill an empty report.

## Input Contract

The top-level JSON uses `schema_version: "1.0"`, `project: "content-gap-brief"`, a topic, reader task, one to eight questions, up to six criteria, one or two synthetic worked examples, zero or more coverage overrides, and selected sources. The checked-in `fixtures/demo.json` is the complete reproducible example; `fixtures/no-candidate.json` verifies the actionable no-brief state.

Sources are explicit snapshots with status, observation timestamp, URL, role, provenance, and optional provider record identity. Supported roles are:

- One to five `owned_article` pages.
- Zero to three `competing_article` pages.
- Zero to five `discovery` search results, which never substitute for article body evidence.
- Zero to five `context_note` operator notes.

Every source-backed output quote is an exact contiguous substring of a normalized block. Reports identify the source URL, observation time, content hash, and provider record ID when available. `as_of` defaults deterministically to the latest supplied observation timestamp, never wall-clock time.

Observed questions retain their original `question_ref` in every coverage row and in the Markdown question-provenance/evidence sections. Editor-inferred questions keep `question_ref: null` and remain explicitly labeled.

## Negative Example

If an owned page contains only `Open the import error log`, the tool labels that row `related_passage_only`. Without a valid override, the question remains in `review_question_ids` and no brief is generated. This is intentionally different from claiming the selected page does not answer the question.

## Optional Bright Data Ingestion

Bright Data is optional. Offline analysis and provider-export import never read credentials or make network requests.

Supported retrieval is deliberately narrow:

- Web Unlocker: one exact operator-approved owned or competing article URL per job.
- SERP API: one Google result page for discovery, at most five distinct result URLs retained.
- At most nine calls in a manifest: one search, five owned pages, and three competing pages.
- At most the approval's cumulative `max_retained_records` across every page and SERP job. Once full, later jobs are not called; over-returned SERP rows are excluded and counted.

Web Unlocker accepts raw Markdown and the documented JSON success envelope `{ "status_code": 200, "headers": {...}, "body": "..." }`. The adapter validates integer status, string headers, and string body, checks embedded target errors, and analyzes only the body. Confirmed target errors never become page text; incomplete or malformed envelopes are safe failures.

Discovery is two-pass. A search result never authorizes or automatically fetches its destination. Select candidate URLs, create a new manifest, and approve those exact URLs separately.

Complete page-collection manifest example:

```json
{
  "schema_version": "1.0",
  "project": "content-gap-brief",
  "jobs": [
    {
      "id": "owned-page",
      "kind": "web_page",
      "role": "owned_article",
      "source_id": "owned-page",
      "url": "https://owned.your-company.tld/import-guide"
    },
    {
      "id": "competing-page",
      "kind": "web_page",
      "role": "competing_article",
      "source_id": "competing-page",
      "url": "https://publisher.your-company.tld/selected-article"
    }
  ]
}
```

Matching approval example:

```json
{
  "schema_version": "1.0",
  "project": "content-gap-brief",
  "manifest_sha256": "997dc124423a32b698beb94eba7b1397cfd0d7351d875aa71495c4e7b82ee511",
  "expires_at": "2026-10-06T00:00:00Z",
  "max_requests": 2,
  "max_retained_records": 2,
  "approved_urls": [
    "https://owned.your-company.tld/import-guide",
    "https://publisher.your-company.tld/selected-article"
  ],
  "account_budget_confirmed": true,
  "target_permissions_confirmed": true,
  "remote_resolution_risk_accepted": true
}
```

These are schema examples, not authorization to collect those placeholder hosts. Replace every URL, choose a short future expiry, confirm each attestation yourself, then regenerate the hash from the exact final manifest with `content_gap_brief.brightdata.plan`. Never reuse the example approval unchanged.

Preview a validated zero-request plan:

```bash
content-gap-brief collect manifest.json --out private/library.json --dry-run
```

Live collection additionally requires `--live`, `--accept-charges`, an approval JSON, and existing environment variables:

```bash
export BRIGHT_DATA_API_KEY='...'
export BRIGHT_DATA_WEB_UNLOCKER_ZONE='...'
export BRIGHT_DATA_SERP_ZONE='...'
content-gap-brief collect manifest.json --out private/library.json \
  --live --accept-charges --approval private/approval.json
```

The approval binds the exact canonical manifest hash, approved URLs, expiry, local request/retention caps, budget confirmation, target-permission confirmation, and remote-resolution risk acknowledgement. The private approval keeps the exact hash and exact approved URLs. Console plans, collection job receipts, and analysis reports redact query values. Credential-bearing query keys are rejected after percent decoding, Unicode normalization, and separator removal.

Live Web Unlocker page targets reject every query string, not only known credential names. Provider page imports also reject query-bearing source URLs, and SERP result URLs with any query string are excluded before they enter an imported or collected source library. SERP query URLs are used only to make the approved discovery request; the query URL itself is not persisted as a source. Select query-free canonical page/result URLs before retaining them. SERP queries are generated locally for the pinned Google endpoint and are never promoted into destination fetches.

These are local safety gates, not cryptographic authorization, legal advice, provider entitlement, or an account-enforced budget. Caps bound retained local data and client request count, not provider work or dollar cost. The client makes sequential calls with no retries, polling, fallback, or automatic destination fetches. Each synchronous transport runs in a killable worker process; the parent terminates it at the earlier of the monotonic 75-second request deadline and overall run deadline, including while response bytes are arriving. Remaining time is floored to whole seconds, never rounded upward; with less than one second left, the next request is not started. Live collection fails closed unless the platform supports `fork` and the caller is single-threaded. A timeout or response arriving after either applicable deadline is `completion_unknown`; the remote provider may already have completed the request, so inspect receipts and do not retrigger automatically.

Import an already authorized downloaded export without network. The command below uses the checked-in, invented `fixtures/web-page.md`; both its contents and `example.com` source URL are synthetic and do not represent a real download:

```bash
content-gap-brief import-provider fixtures/web-page.md --kind web_page \
  --role competing_article --source-url https://example.com/selected \
  --observed-at 2026-10-04T10:00:00Z --out /tmp/import-library.json
```

SERP import expects a parsed JSON object with an `organic` array. Every retained search-result source carries allowlisted `metadata.serp_rank` and `metadata.serp_global_rank` values (or `null` if unavailable); live collection also emits a job-level rank list. Source and rank metadata are normalized atomically, so rejected or duplicate records cannot shift ranks onto another source. HTML-bearing SERP descriptions are excluded rather than analyzed. Page import and live page collection enforce the same 50,000-character analyzable limit. Imported data is labeled `operator_supplied`; the tool does not certify its origin. Content Gap Brief has no asynchronous dataset scraper jobs, so `resume` is intentionally unsupported.

## Privacy And Safety

Provider normalizers retain only allowlisted source fields. They do not retain profile names, handles, profile links, avatars, reactions, replies, addresses, or raw provider response metadata. Raw live responses are not saved.

Free text can still contain names, contact details, sensitive information, or hostile instructions. Metadata minimization does not anonymize text. A human privacy review of every selected excerpt and generated artifact is required before sharing or publication. Keep real libraries/reports private, follow source terms, confirm target permissions, and delete retained artifacts when no longer needed. Markdown scalar fields are collapsed to one escaped line, evidence delimiters are inert, and CSV formula-leading cells are prefixed with an apostrophe. There is no telemetry or automatic publishing.

## Limits And Truthful Claims

- Deterministic rules only; no LLM, embeddings, hidden model key, semantic SEO scoring, or search-volume estimate.
- Selected snapshots only; no completeness, freshness, privacy, accuracy, ranking, traffic, or business-outcome guarantee.
- `stale_source` warns when an explicit `as_of` is more than 30 days after observation; it does not erase evidence.
- Search snippets are discovery records only and cannot establish destination-page claims.
- URL checks reduce obvious risk but cannot guarantee remote DNS resolution. The local client does not follow HTTP redirects, but a provider may resolve or follow a target redirect remotely; the tool does not observe or guarantee the final destination. This residual risk must be accepted in the private approval.
- Provider dollar cost is always `null`; the tool does not fabricate spend estimates.

Errors are structured JSON, including argparse syntax/required-argument failures. Exit `0` means a valid output or plan, including honest business unknowns. Exit `2` means invalid input, flags, approval, or filesystem state. If a local receipt write fails after collection, the JSON error includes the number of requests already made; inspect the destination before retrying. A confirmed provider/response failure recorded as receipt status `failed` returns exit code `3`. Exit `4` means `partial`, `pending`, or `completion_unknown`; transport timeouts and late responses are deliberately `completion_unknown`, not confirmed provider failures.

## Differentiation

The nearest adjacent concept is a generic content-gap/topic finder. This project instead joins selected owned-page body checks, uncertainty-preserving human overrides, selected competing body evidence, question-specific acceptance criteria, and computed synthetic worked examples. It intentionally does not claim universal novelty, crawl the web, estimate keyword demand, or rank generic topics.

## Testing And Verification

```bash
python3 -m pytest -q
```

The suite covers candidate eligibility, provider heading round-trips, heading/body separation, strict nested/source-library validation, observed-question provenance, exact-byte positive/no-candidate goldens, structured CLI errors, cumulative retention, URL credential defenses, atomic SERP/rank filtering, collection deadlines, transactional output, output safety, and injected request serialization. Package metadata intentionally targets only Python 3.11 and 3.12, matching the CI matrix. The final local wheel run used Python 3.12 because Python 3.11 was not installed on that machine. CI runs without provider secrets.

Verification status as of 2026-10-05:

- Offline deterministic analysis and CLI: locally verified.
- Invented fixtures and expected artifacts: locally verified.
- Mock-transport Web Unlocker/SERP serialization: locally verified.
- Independent reviewer disposition on the latest revision: QA **SHIP**, Security **APPROVE**, and Bright Data brand **APPROVE** of the documented response envelope; see [`VERIFICATION.md`](VERIFICATION.md) for scope, local evidence, and artifact-path limitation. These reviews do not verify live provider behavior.
- Authorized live Bright Data retrieval, account access, zones, billing, and target responses: **not verified**.

Provider references reviewed for the 2026-10-04 build contract:

- https://docs.brightdata.com/api-reference/rest-api/unlocker/unlock-website
- https://docs.brightdata.com/api-reference/rest-api/serp/serp-api

If live collection fails, inspect only the safe receipt code. Do not retry a timeout blindly: the remote operation may have completed. Revalidate the manifest/approval, exact zones, and current official documentation before another authorized attempt.

## Attribution

Uses Bright Data for optional public-data retrieval. Analysis and decisions are local application logic. Not affiliated with or endorsed by Bright Data.

License: MIT for project code and invented fixtures. It does not grant rights to third-party source content.
