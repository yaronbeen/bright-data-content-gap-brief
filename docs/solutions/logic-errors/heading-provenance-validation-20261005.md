# Heading, Provenance, And Validation Boundaries

## Problem

Provider page ingestion normalized Markdown to canonical text and then passed that stripped text through the source constructor. ATX heading markers were lost, so a later analysis replay treated former headings as body evidence. Several nested fields also reached set/dictionary membership before type validation, and observed question citations were discarded after validation.

## Symptoms

- A heading-only answer from an imported or collected page could become eligible body evidence.
- Setext headings had no explicit support policy.
- Malformed list/object field values could raise `TypeError` instead of a structured exit `2`.
- Source libraries with incomplete or unknown envelope fields were accepted or crashed.
- Reports retained `question_origin` but lost the exact observed `question_ref`.
- Argparse syntax errors emitted unstructured usage text despite the JSON error contract.

## Failed Approach

Canonical text was reused as a storage format even though canonicalization deliberately removes heading syntax. Validation relied on later Python operations to imply types, and citations were considered validation-only data.

## Solution

- Normalize provider pages into a replayable Markdown representation that retains ATX heading level while still using canonical block text for hashes and matching.
- Reject Setext heading syntax explicitly.
- Validate every nested string/ID/enum before set or dictionary operations.
- Require the exact versioned source-library envelope before appending sources.
- Include observed `question_ref` in coverage rows, Markdown provenance, and the evidence appendix.
- Override argparse errors with a fixed safe JSON object and exit code `2`.
- Lock behavior with exact-byte happy-path and no-candidate golden fixtures.

## Root Cause

The implementation conflated canonical analysis text with replayable source text and treated schema validation as incidental to downstream operations.

## Prevention

Test every data transformation through a second analysis pass, include malformed JSON types for every nested identifier/enum, and treat provenance fields as required output whenever they influence a decision.
