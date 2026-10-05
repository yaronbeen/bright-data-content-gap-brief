# Bright Data Adapter Contract Snapshot

Reviewed: 2026-10-04. Transport contract version: `1.0`.

This project adapts two optional Bright Data products:

- Web Unlocker synchronous request API: `POST https://api.brightdata.com/request` with an existing zone, one exact approved target URL, `format: raw`, and `data_format: markdown`.
- SERP API through the same endpoint with an existing SERP zone and one encoded Google search URL using `gl`, `hl=en`, `pws=0`, and `brd_json=1`.

Official references reviewed:

- https://docs.brightdata.com/api-reference/rest-api/unlocker/unlock-website
- https://docs.brightdata.com/api-reference/rest-api/serp/serp-api

## Local Adaptation

Web Unlocker raw Markdown is accepted directly. Its documented JSON response envelope `{status_code, headers, body}` is also accepted after validating integer HTTP status, string header map, and string body. Non-2xx embedded target status/error headers become safe provider-target failures; only the body text is normalized as page content.

The client pins `api.brightdata.com`, standard TLS verification, a monotonic per-request deadline of at most 75 seconds, a monotonic overall run deadline, no proxies, no client redirects, no retry, a 2 MiB response limit, and at most nine sequential calls. Each complete synchronous request and body read executes in a killable worker process; its parent terminates the worker at the absolute monotonic deadline, rather than waiting for the socket's per-operation timeout. Live mode fails closed on platforms without `fork` and in multithreaded callers. It inspects Bright Data status/error header aliases before parsing an outer HTTP 200 response. Provider error text and raw bodies are not retained. Late responses and transport timeouts become `completion_unknown` and are never automatically retriggered.

SERP discovery retains at most five distinct valid HTTPS URLs and is also bounded by the approval's cumulative retained-record limit across all jobs. Source and rank records are normalized together. Invalid, duplicate, and over-cap rows are excluded with truthful counts; later jobs are not called after the cumulative cap is full. Search snippets remain `discovery` sources and cannot establish destination-page facts. Fetching a selected destination requires a separate exact manifest and approval.

Every retained `search_result` source has a narrow `metadata` object with `serp_rank` and `serp_global_rank`, each a positive integer or null. Imported and live libraries use this same source-level representation. Live job receipts additionally carry `query_metadata.result_ranks`; both are generated from the same atomic record-normalization pass. These two metadata keys are the only accepted source metadata fields.

Live page targets reject all query strings. Every URL mode rejects known credential/signature keys after repeated percent decoding, Unicode normalization, case folding, and separator removal. The private manifest and approval retain exact hashes/URLs; public console plans, report URLs, and receipt job fields redact query values.

The local HTTP client refuses redirects. Bright Data may resolve or follow a redirect remotely while fetching an approved target, so this client cannot inspect or guarantee the final destination. DNS rebinding and provider-side redirect resolution remain explicit residual risks.

Page responses and imports are limited to 50,000 characters so every retained page remains valid analysis input. The 2 MiB response cap is a separate transport bound.

The Markdown/text adapter rejects any HTML tag, comment, declaration, processing-instruction opener, or document markup anywhere in supplied page text. It does not strip HTML into text, so words inside markup cannot qualify as body evidence. A SERP record whose description contains such markup is excluded as a record, preserving source/rank alignment for later results.

## Verification Boundary

Injected recording transports verify local request serialization, response parsing, hard cancellation of slow custom transports, cumulative retention, and redaction. A local slow-drip HTTP server verifies cancellation during body reads. No authorized real provider call was made, so account access, zone compatibility, billing, provider-side redirect behavior, final target destination, and the selected raw Web Unlocker response shape remain unverified. Local caps do not establish or enforce provider spend.
