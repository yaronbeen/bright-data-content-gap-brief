# Learnings

## Current Skills-Only Workflow - 2026-10-06

- The user explicitly retired the Python product in favor of one simple Bright Data-backed business skill. Historical application decisions below are not current operating instructions.
- Source evidence must be retrieved through configured Bright Data tools in the current agent session. Missing access means connect and stop, not use an export, mock, or another provider.
- Coverage comparison is semantic: differently worded answers can count, while a heading or keyword alone cannot. Missing/truncated bodies require review, not a no-commission verdict.
- The pre-existing local correction in the retired validation document was preserved byte-for-byte at `/home/yaron/.claude/data/brightdata-drafts/2026-10-06-content-gap-validation-preserved.md`; SHA-256 `43bb63a8eb77f008dd07a9083a94fe5cf181f16e0dd5ff1d9857db39f5bf2b63`. It is historical evidence, not a dependency of the current skill.
- Official MCP setup and tools documentation was fetched on 2026-10-06. `chub` was unavailable, so current official pages were read directly. Static documentation checks do not establish live functionality.

- Independent real-data exercise: PARTIAL. An empty search discovered no candidate URLs; genuinely collected directly selected pages can still support a scoped comparison, but must not be labeled search discoveries.
- Check where truncation occurs: an incomplete footer/widget does not erase body evidence; incomplete relevant article sections block absence claims. Older articles support editorial comparison, not verified current product instructions. Capture instants/timezones remain unknown where not supplied or observed.
- External evidence remains at `/home/yaron/.claude/data/brightdata-drafts/2026-10-06-brightdata-real-business-validation.md`. The public validation business is not the user's business. No source excerpts or dataset were copied into the repository, and no calls were repeated for the rule clarification.
- 2026-10-07: Release approval, static documentation validation, and public-byte verification are separate from live branch coverage. The user reports all three reviewers APPROVE for publication; the empty-search discovery outcome remains PARTIAL, not a fabricated search success or a newly validated branch.

## Historical Application Learnings

- Heading blocks must stay distinct from body blocks. A phrase in a source title or Markdown heading cannot establish article-body coverage or competing fit.
- A scoped gap is not automatically brief-worthy. It additionally needs at least one assigned criterion and a real competing body passage.
- Literal answer phrases are operator-declared checks, not semantic understanding. Related-only owned evidence stays unresolved unless an exact, hash-bound override resolves it.
- The original candidate-selection tests intentionally allow zero criteria so the report can return a useful `coverage_review_required` state rather than reject the input.
- Content Gap Brief uses synchronous Web Unlocker and SERP only, so snapshot resume is deliberately unsupported.
- Setuptools 81 rejects an MIT license expression combined with the superseded `License :: OSI Approved :: MIT License` classifier; keep `license = "MIT"` and omit that classifier.
- Retention approval is cumulative across heterogeneous jobs. Check remaining capacity before each paid call and trim an accepted response before appending; source and rank records must be produced by the same filtering pass.
- URL credential checks must decode repeatedly, normalize Unicode, case-fold, and remove separators before comparing keys. Public artifacts redact query values, while private approval integrity comes from the exact manifest hash.
- A transport timeout is not the only uncertain state: a syntactically successful response received after a monotonic deadline must also be discarded as `completion_unknown`.
- Three individually atomic writes are not a transaction. Stage the complete report set, use atomic no-clobber links, track inode ownership during rollback, and back up overwrite targets before replacement.
- Markdown escaping alone does not neutralize multiline scalar structure. Collapse untrusted scalar whitespace to one line before escaping delimiters.
- Canonical analysis text intentionally strips heading markers, so provider adapters must retain a normalized Markdown representation for replay instead of feeding stripped canonical text back through the parser.
- Validate nested IDs and enum values before set/dictionary membership; otherwise malformed JSON arrays can escape the validation boundary as `TypeError` rather than the promised structured input error.
- Observed-question citations are provenance, not temporary validation data. Preserve them in structured coverage rows and rendered evidence.
- Documentation must distinguish confirmed provider failure (`3`) from uncertain completion (`4`), and any downloaded-export quickstart must label checked-in examples as synthetic at the point of use.
- A provider call followed by local receipt-write failure is a separate dangerous retry path: report the known request count and protect any racing destination with atomic no-clobber semantics.
- Redacting report URLs is not enough if the private collection library persists query-bearing SERP result URLs. Enforce the URL retention policy at normalization, before serializing any source library.
- An integer-second transport timeout must be floored against monotonic remaining time; if under one second remains, skip the request rather than round upward.
- Reject embedded HTML markup before text block matching; checking only document prefixes still allows script/comment/tag text to become false evidence.
- Keep rank data attached to each retained SERP source as allowlisted metadata and derive live receipt rank rows from the same normalization output.
- Checking elapsed time after a synchronous call returns is not a deadline. Use a killable boundary around request and body handling; fail closed where the runtime cannot provide that boundary.
- Treat provider-documented response envelopes as actual supported shapes: validate status/headers/body and normalize only the body, while retaining raw Markdown compatibility when documented.
- `urlsplit` accepts malformed percent escapes; explicitly validate percent triplets before approvals, and validate provider-derived Unicode before storing strings.
- Guard all parsed URL component access, not only `urlsplit()` and `.port`; `.hostname` normalization can raise a UnicodeError outside that narrow try block.
- Checking elapsed time after a synchronous call returns is not a deadline. Use a killable boundary around request and body handling; fail closed where the runtime cannot provide that boundary.
