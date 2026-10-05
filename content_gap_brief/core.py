"""Validation and deterministic analysis for Content Gap Brief."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from urllib.parse import parse_qsl, unquote_plus, urlencode, urlsplit, urlunsplit

PROJECT = "content-gap-brief"
METHOD = "deterministic_rules_v1"
MAX_BYTES = 2 * 1024 * 1024
ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
BLOCK_RE = re.compile(r"^b\d{4}$")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
HTML_MARKUP_RE = re.compile(r"<!--|</?[A-Za-z][^<>]*>|</?[A-Za-z][A-Za-z0-9:-]*(?=\s|/|$)|<!|<\?", re.I)
SENSITIVE_QUERY_KEYS = {
    "accesskeyid",
    "accesstoken",
    "apikey",
    "auth",
    "authorization",
    "awsaccesskeyid",
    "clientsecret",
    "credential",
    "googleaccessid",
    "keypairid",
    "password",
    "passcode",
    "policy",
    "secret",
    "session",
    "sessionid",
    "sig",
    "signature",
    "token",
    "xamzcredential",
    "xamzsecuritytoken",
    "xamzsignature",
    "xgoogcredential",
    "xgoogsignature",
}


def _normalized_query_key(value: str) -> str:
    for _ in range(3):
        decoded = unquote_plus(value)
        if decoded == value:
            break
        value = decoded
    return "".join(character for character in unicodedata.normalize("NFKC", value).casefold() if character.isalnum())


class ValidationError(ValueError):
    """A safe, operator-correctable input error."""

    code = "invalid_input"


def _fail(message: str) -> None:
    raise ValidationError(message)


def _object(value, name: str, allowed: set[str], required: set[str] = frozenset()):
    if not isinstance(value, dict):
        _fail(f"{name} must be an object")
    unknown = set(value) - allowed
    if unknown:
        _fail(f"{name} has unknown keys: {', '.join(sorted(unknown))}")
    missing = required - set(value)
    if missing:
        _fail(f"{name} is missing keys: {', '.join(sorted(missing))}")
    return value


def _string(value, name: str, low: int, high: int) -> str:
    if not isinstance(value, str) or not (low <= len(value) <= high) or not value.strip():
        _fail(f"{name} must be a non-blank string of {low}..{high} characters")
    if CONTROL_RE.search(value):
        _fail(f"{name} contains unsupported control characters")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        _fail(f"{name} is not valid UTF-8 text")
    return value


def _id(value, name: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        _fail(f"{name} must match {ID_RE.pattern}")
    return value


def _list(value, name: str, low: int, high: int):
    if not isinstance(value, list) or not (low <= len(value) <= high):
        _fail(f"{name} must contain {low}..{high} items")
    return value


def _utc(value, name: str) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        _fail(f"{name} must be a UTC RFC3339 timestamp ending in Z")
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        _fail(f"{name} must be a valid UTC RFC3339 timestamp")
    return value


def canonical_url(value: str, *, live: bool = False) -> str:
    _string(value, "url", 1, 2048)
    if re.search(r"%(?![0-9A-Fa-f]{2})", value):
        _fail("url contains a malformed percent escape")
    try:
        parts = urlsplit(value)
        port = parts.port
        scheme = parts.scheme
        hostname = parts.hostname
        username = parts.username
        password = parts.password
        fragment = parts.fragment
        path = parts.path
        query = parts.query
    except (ValueError, UnicodeError):
        _fail("url is invalid")
    if scheme != "https" or not hostname or username or password or fragment:
        _fail("url must be credential-free HTTPS without a fragment")
    if port not in (None, 443):
        _fail("url may not use a non-443 port")
    host = hostname.lower().rstrip(".")
    labels = host.split(".")
    if any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", x) for x in labels):
        _fail("url hostname is invalid")
    for key, _ in parse_qsl(query, keep_blank_values=True):
        normalized_key = _normalized_query_key(key)
        if normalized_key in SENSITIVE_QUERY_KEYS:
            _fail("credential-bearing query keys are not allowed")
    if live:
        import ipaddress

        try:
            parsed_ip = ipaddress.ip_address(host)
        except ValueError:
            parsed_ip = None
        if parsed_ip is not None:
            _fail("IP-literal live targets are not allowed")
        blocked = (".localhost", ".local", ".internal", ".invalid", ".example", ".test")
        if len(labels) < 2 or labels[-1].isdigit() or host == "localhost" or host.endswith(blocked):
            _fail("reserved or local live targets are not allowed")
        if host in {"example.com", "example.org", "example.net"} or any(
            host.endswith("." + x) for x in ("example.com", "example.org", "example.net")
        ):
            _fail("fixture hosts are not allowed in live mode")
        if query:
            _fail("live page targets may not contain a query string")
    netloc = host if port in (None, 443) else f"{host}:{port}"
    try:
        return urlunsplit(("https", netloc, path, query, ""))
    except (ValueError, UnicodeError):
        _fail("url is invalid")


def redact_url(value: str | None) -> str | None:
    """Remove query values from a validated URL before public rendering."""
    if value is None:
        return None
    parts = urlsplit(value)
    if not parts.query:
        return value
    redacted = urlencode([(key, "[REDACTED]") for key, _ in parse_qsl(parts.query, keep_blank_values=True)])
    return urlunsplit((parts.scheme, parts.netloc, parts.path, redacted, ""))


def normalize_text(text: str) -> tuple[str, list[dict]]:
    if not isinstance(text, str):
        _fail("source text must be a string")
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        _fail("source text is not valid UTF-8")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if CONTROL_RE.search(text):
        _fail("source text contains unsupported control characters")
    if HTML_MARKUP_RE.search(text):
        _fail("unsupported_content_format")
    lines = text.split("\n")
    for index, line in enumerate(lines[1:], 1):
        if re.fullmatch(r" {0,3}(?:=+|-+)\s*", line) and lines[index - 1].strip():
            _fail("unsupported_setext_heading")
    raw_blocks: list[tuple] = []
    pending: list[str] = []

    def flush():
        if pending:
            raw_blocks.append((" ".join(pending), False))
            pending.clear()

    for line in text.split("\n"):
        heading = HEADING_RE.match(line.strip())
        if heading:
            flush()
            raw_blocks.append((heading.group(2), True, len(heading.group(1))))
        elif not line.strip():
            flush()
        else:
            pending.append(line)
    flush()
    blocks = []
    for item in raw_blocks:
        raw, heading = item[:2]
        level = item[2] if len(item) == 3 else None
        value = " ".join(raw.split()).strip()
        if value:
            blocks.append({"id": f"b{len(blocks) + 1:04d}", "text": value, "heading": heading, "heading_level": level})
    return "\n\n".join(x["text"] for x in blocks), blocks


def normalize_source_markdown(text: str) -> tuple[str, list[dict]]:
    """Normalize page text while retaining ATX heading structure for replay."""
    _, blocks = normalize_text(text)
    stored = "\n\n".join(
        (("#" * (block["heading_level"] or 1)) + " " if block["heading"] else "") + block["text"]
        for block in blocks
    )
    return stored, blocks


def _phrase_hit(text: str, phrase: str):
    pattern = re.compile(r"(?<![0-9A-Za-z])" + re.escape(" ".join(phrase.split())) + r"(?![0-9A-Za-z])", re.I)
    return pattern.search(" ".join(text.split()))


def _excerpt(block: str, hit, limit: int = 240) -> str:
    if len(block) <= limit:
        return block
    start = max(0, hit.start() - 80)
    start = min(start, max(0, hit.end() - limit))
    return block[start : start + limit]


def _citation(source_id: str, block: dict, hit=None) -> dict:
    return {"source_id": source_id, "block_id": block["id"], "quote": _excerpt(block["text"], hit) if hit else block["text"][:240]}


def _validate_citation(ref, name: str, sources: dict, *, body=False) -> dict:
    _object(ref, name, {"source_id", "block_id", "quote"}, {"source_id", "block_id", "quote"})
    sid = _id(ref["source_id"], f"{name}.source_id")
    if sid not in sources or sources[sid]["status"] != "collected":
        _fail(f"{name} references a missing or unavailable source")
    if not isinstance(ref["block_id"], str) or not BLOCK_RE.fullmatch(ref["block_id"]):
        _fail(f"{name}.block_id is invalid")
    block = next((x for x in sources[sid]["blocks"] if x["id"] == ref["block_id"]), None)
    if not block or (body and block["heading"]):
        _fail(f"{name} must reference an existing body block")
    quote = _string(ref["quote"], f"{name}.quote", 1, 240)
    if quote not in block["text"]:
        _fail(f"{name}.quote is stale or not contiguous")
    return dict(ref)


def _normalize_source(raw: dict, index: int) -> dict:
    fields = {"id", "kind", "role", "url", "title", "text", "status", "observed_at", "published_at", "provider_date", "record_id", "record_id_origin", "provenance", "metadata"}
    _object(raw, f"sources[{index}]", fields, fields - {"metadata"})
    sid = _id(raw["id"], f"sources[{index}].id")
    role = raw["role"]
    allowed = {"owned_article": "page", "competing_article": "page", "discovery": "search_result", "context_note": "operator_note"}
    if not isinstance(role, str) or not isinstance(raw["kind"], str) or role not in allowed or raw["kind"] != allowed[role]:
        _fail(f"source {sid} has an unsupported kind/role pair")
    status = raw["status"]
    if not isinstance(status, str) or status not in {"collected", "empty", "unavailable", "pending"}:
        _fail(f"source {sid} status is invalid")
    max_text = 50000 if raw["kind"] == "page" else 2000
    if not isinstance(raw["text"], str) or len(raw["text"]) > max_text:
        _fail(f"source {sid} text is invalid or too long")
    if status == "collected" and not raw["text"].strip():
        _fail(f"collected source {sid} needs text")
    if status != "collected" and raw["text"] != "":
        _fail(f"non-collected source {sid} must have empty text")
    if raw["url"] is None:
        if raw["kind"] != "operator_note":
            _fail(f"source {sid} requires a URL")
        url = None
    else:
        url = canonical_url(raw["url"])
    canonical, blocks = normalize_text(raw["text"])
    title = _string(raw["title"], f"source {sid}.title", 1, 200)
    published = raw["published_at"]
    if published is not None:
        _utc(published, f"source {sid}.published_at")
    provider_date = raw["provider_date"]
    if provider_date is not None and (not isinstance(provider_date, str) or len(provider_date) > 100):
        _fail(f"source {sid}.provider_date is invalid")
    origin = raw["record_id_origin"] if raw["record_id_origin"] is not None else "none"
    if not isinstance(origin, str) or origin not in {"provider", "operator", "content_hash", "none"}:
        _fail(f"source {sid} record_id_origin is invalid")
    if (origin == "none") != (raw["record_id"] is None):
        _fail(f"source {sid} record ID and origin disagree")
    if raw["record_id"] is not None and (not isinstance(raw["record_id"], str) or not 1 <= len(raw["record_id"]) <= 200 or not raw["record_id"].strip()):
        _fail(f"source {sid} record_id is invalid")
    if not isinstance(raw["provenance"], str) or raw["provenance"] not in {"synthetic_fixture", "operator_supplied", "bright_data"}:
        _fail(f"source {sid} provenance is invalid")
    metadata = raw.get("metadata")
    if role == "discovery":
        if metadata is None:
            metadata = {"serp_rank": None, "serp_global_rank": None}
        if not isinstance(metadata, dict) or set(metadata) != {"serp_rank", "serp_global_rank"}:
            _fail(f"source {sid} SERP metadata is invalid")
        for rank_name, rank_value in metadata.items():
            if rank_value is not None and (type(rank_value) is not int or rank_value < 1):
                _fail(f"source {sid} {rank_name} must be a positive integer or null")
    elif "metadata" in raw:
        _fail(f"source {sid} does not allow metadata")
    return {
        **raw,
        "title": title,
        "url": url,
        **({"metadata": metadata} if role == "discovery" else {}),
        "record_id_origin": origin,
        "canonical_text": canonical,
        "blocks": blocks,
        "content_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
        "observed_at": _utc(raw["observed_at"], f"source {sid}.observed_at"),
    }


def analyze(payload: dict) -> dict:
    """Validate and turn selected pages into a bounded editorial brief."""
    if not isinstance(payload, dict):
        _fail("input must be a JSON object")
    try:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    except (TypeError, ValueError, UnicodeError):
        _fail("input must be JSON serializable")
    if len(encoded) > MAX_BYTES:
        _fail("input exceeds 2 MiB")
    allowed = {"schema_version", "project", "as_of", "sources", "topic", "reader_task", "questions", "criteria", "worked_examples", "coverage_overrides"}
    required = {"sources", "topic", "reader_task", "questions", "criteria", "worked_examples", "coverage_overrides"}
    _object(payload, "input", allowed, required)
    if payload.get("schema_version", "1.0") != "1.0" or payload.get("project", PROJECT) != PROJECT:
        _fail("schema_version or project is not supported")
    topic = _string(payload["topic"], "topic", 1, 160)
    reader_task = _string(payload["reader_task"], "reader_task", 1, 200)
    sources_list = _list(payload["sources"], "sources", 1, 100)
    sources = {}
    role_counts = {"owned_article": 0, "competing_article": 0, "discovery": 0, "context_note": 0}
    for i, raw in enumerate(sources_list):
        src = _normalize_source(raw, i)
        if src["id"] in sources:
            _fail("source IDs must be unique")
        sources[src["id"]] = src
        role_counts[src["role"]] += 1
    if not 1 <= role_counts["owned_article"] <= 5 or role_counts["competing_article"] > 3 or role_counts["discovery"] > 5 or role_counts["context_note"] > 5:
        _fail("source role count exceeds project limits")
    as_of = payload.get("as_of")
    if as_of is not None:
        _utc(as_of, "as_of")
    else:
        as_of = max(x["observed_at"] for x in sources.values()) if sources else None

    questions = []
    question_ids = set()
    for i, raw in enumerate(_list(payload["questions"], "questions", 1, 8)):
        fields = {"id", "text", "origin", "question_ref", "related_phrases", "answer_phrases"}
        _object(raw, f"questions[{i}]", fields, fields)
        qid = _id(raw["id"], f"questions[{i}].id")
        if qid in question_ids:
            _fail("question IDs must be unique")
        question_ids.add(qid)
        question_text = _string(raw["text"], f"question {qid}.text", 1, 160)
        if not isinstance(raw["origin"], str) or raw["origin"] not in {"observed", "editor_inferred"}:
            _fail(f"question {qid} origin is invalid")
        if raw["origin"] == "observed":
            if raw["question_ref"] is None:
                _fail(f"observed question {qid} requires question_ref")
            qref = _validate_citation(raw["question_ref"], f"question {qid}.question_ref", sources)
            if sources[qref["source_id"]]["role"] != "competing_article":
                _fail("observed question must cite an actual competing article")
        else:
            if raw["question_ref"] is not None:
                _fail(f"editor-inferred question {qid} must not have question_ref")
            qref = None
        related = [_string(x, f"question {qid}.related_phrases", 1, 80) for x in _list(raw["related_phrases"], "related_phrases", 1, 8)]
        answers = [_string(x, f"question {qid}.answer_phrases", 1, 240) for x in _list(raw["answer_phrases"], "answer_phrases", 1, 6)]
        questions.append({**raw, "text": question_text, "question_ref": qref, "related_phrases": related, "answer_phrases": answers})

    criteria = []
    criterion_ids = set()
    for i, raw in enumerate(_list(payload["criteria"], "criteria", 0, 6)):
        fields = {"id", "question_id", "label", "acceptance_check", "required"}
        _object(raw, f"criteria[{i}]", fields, fields)
        cid = _id(raw["id"], f"criteria[{i}].id")
        criterion_question_id = _id(raw["question_id"], f"criterion {cid}.question_id")
        if cid in criterion_ids or criterion_question_id not in question_ids:
            _fail("criterion IDs must be unique and reference a question")
        if type(raw["required"]) is not bool:
            _fail("criterion required must be boolean")
        criterion_ids.add(cid)
        criteria.append({**raw, "question_id": criterion_question_id, "label": _string(raw["label"], "criterion label", 1, 100), "acceptance_check": _string(raw["acceptance_check"], "acceptance_check", 1, 200)})

    examples = []
    for i, raw in enumerate(_list(payload["worked_examples"], "worked_examples", 1, 2)):
        fields = {"label", "scenario", "has_criteria", "provenance"}
        _object(raw, f"worked_examples[{i}]", fields, fields)
        if raw["provenance"] != "synthetic_operator_example":
            _fail("worked example provenance must be synthetic_operator_example")
        has = [_id(value, "worked example criterion ID") for value in _list(raw["has_criteria"], "has_criteria", 0, 6)]
        if len(has) != len(set(has)) or any(x not in criterion_ids for x in has):
            _fail("worked example has dangling or duplicate criterion IDs")
        examples.append({**raw, "has_criteria": has, "label": _string(raw["label"], "example label", 1, 100), "scenario": _string(raw["scenario"], "example scenario", 1, 300)})

    overrides = {}
    for i, raw in enumerate(_list(payload["coverage_overrides"], "coverage_overrides", 0, 40)):
        fields = {"question_id", "source_id", "source_sha256", "decision", "evidence", "rationale"}
        _object(raw, f"coverage_overrides[{i}]", fields, fields)
        key = (_id(raw["question_id"], "override.question_id"), _id(raw["source_id"], "override.source_id"))
        if key in overrides or key[0] not in question_ids or key[1] not in sources:
            _fail("coverage override is duplicate or dangling")
        src = sources[key[1]]
        if not isinstance(raw["source_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", raw["source_sha256"]) or src["role"] != "owned_article" or src["status"] != "collected" or raw["source_sha256"] != src["content_sha256"]:
            _fail("coverage override source/hash is stale or ineligible")
        if not isinstance(raw["decision"], str) or raw["decision"] not in {"covers", "does_not_cover"}:
            _fail("coverage override decision is invalid")
        evidence = [_validate_citation(x, "override evidence", sources, body=True) for x in _list(raw["evidence"], "override evidence", 0, 3)]
        if raw["decision"] == "covers" and not evidence:
            _fail("covers override requires body evidence")
        if any(x["source_id"] != key[1] for x in evidence):
            _fail("override evidence must cite its source")
        overrides[key] = {**raw, "evidence": evidence, "rationale": _string(raw["rationale"], "override rationale", 1, 200)}

    coverage = []
    by_question = {}
    page_sources = [x for x in sources.values() if x["role"] in {"owned_article", "competing_article"}]
    for q in questions:
        qrows = []
        for src in page_sources:
            override = overrides.get((q["id"], src["id"]))
            refs, matched_answer, method = [], None, "declared_phrase_check"
            if src["status"] != "collected":
                state, method = "unavailable", "source_status"
            elif override:
                state = "operator_confirmed_" + ("covers" if override["decision"] == "covers" else "does_not_cover")
                refs, method = override["evidence"], "operator_override"
            else:
                answer_hits, related_hits = [], []
                for block in src["blocks"]:
                    if block["heading"]:
                        continue
                    for phrase in q["answer_phrases"]:
                        hit = _phrase_hit(block["text"], phrase)
                        if hit:
                            answer_hits.append((_citation(src["id"], block, hit), phrase))
                    for phrase in q["related_phrases"]:
                        hit = _phrase_hit(block["text"], phrase)
                        if hit:
                            related_hits.append((_citation(src["id"], block, hit), phrase))
                if answer_hits:
                    state, refs, matched_answer = "answer_phrase_found", [x[0] for x in answer_hits[:2]], answer_hits[0][1]
                elif related_hits:
                    state, refs = "related_passage_only", [x[0] for x in related_hits[:2]]
                else:
                    state = "no_related_passage_found_in_selected_text"
            row = {"question_id": q["id"], "question": q["text"], "question_origin": q["origin"], "question_ref": q["question_ref"], "source_id": src["id"], "source_role": src["role"], "coverage_state": state, "coverage_method": method, "matched_answer_phrase": matched_answer, "evidence": refs, "excerpt": refs[0]["quote"] if refs else "", "source_url": redact_url(src["url"]), "observed_at": src["observed_at"]}
            coverage.append(row)
            qrows.append(row)
        by_question[q["id"]] = qrows

    suppressed, review, gap = [], [], []
    for q in questions:
        owned = [x for x in by_question[q["id"]] if x["source_role"] == "owned_article"]
        if any(x["coverage_state"] in {"answer_phrase_found", "operator_confirmed_covers"} for x in owned):
            suppressed.append(q["id"])
        elif any(x["coverage_state"] in {"related_passage_only", "unavailable"} for x in owned):
            review.append(q["id"])
        else:
            gap.append(q["id"])

    selected = None
    for q in questions:
        qcriteria = [x for x in criteria if x["question_id"] == q["id"]]
        competing_fit = any(x["source_role"] == "competing_article" and x["coverage_state"] in {"answer_phrase_found", "related_passage_only"} for x in by_question[q["id"]])
        if q["id"] in gap and qcriteria and competing_fit:
            selected = (q, qcriteria)
            break

    for q in questions:
        qcriteria = any(x["question_id"] == q["id"] for x in criteria)
        competing_fit = any(x["source_role"] == "competing_article" and x["coverage_state"] in {"answer_phrase_found", "related_passage_only"} for x in by_question[q["id"]])
        if q["id"] in gap and (not qcriteria or not competing_fit):
            review.append(q["id"])

    if selected:
        q, qcriteria = selected
        angle_refs = [ref for row in by_question[q["id"]] if row["source_role"] == "competing_article" for ref in row["evidence"]][:2]
        example_rows = []
        for ex in examples:
            relevant = [x for x in qcriteria if x["id"] in ex["has_criteria"]]
            missing = [x["id"] for x in qcriteria if x["required"] and x["id"] not in ex["has_criteria"]]
            example_rows.append({"label": ex["label"], "scenario": ex["scenario"], "present_criteria_ids": [x["id"] for x in relevant], "missing_required_criteria_ids": missing, "provenance": ex["provenance"]})
        brief = {"question_id": q["id"], "title": q["text"].rstrip("?") + ": a practical checklist", "reader_task": reader_task, "angle_basis_refs": angle_refs, "outline_sections": [f"The decision: {reader_task}", "Requirements checklist", f"Worked example: {examples[0]['label']}", "Limits and expert checks"], "checklist_rows": [{"criterion_id": x["id"], "label": x["label"], "acceptance_check": x["acceptance_check"], "required": x["required"]} for x in qcriteria], "worked_example_rows": example_rows, "expert_checks": ["Confirm declared phrases still represent the intended answer checks.", "Verify synthetic example assumptions before publication.", "Review cited source excerpts and any stale or unavailable evidence."], "interpretation": "scoped_editorial_candidate"}
        decision = "scoped_brief"
    elif len(suppressed) == len(questions):
        brief, decision = None, "already_covered_by_declared_checks"
    else:
        brief, decision = None, "coverage_review_required"
        review = list(dict.fromkeys(review + [q["id"] for q in questions if q["id"] not in suppressed]))

    warnings = []
    if as_of:
        as_dt = datetime.fromisoformat(as_of[:-1] + "+00:00")
        stale = [x["id"] for x in sources.values() if (as_dt - datetime.fromisoformat(x["observed_at"][:-1] + "+00:00")).days > 30]
        if stale:
            warnings.append({"code": "stale_source", "source_ids": stale, "note": "Source observation is more than 30 days before as_of."})
    unavailable = [x["id"] for x in sources.values() if x["status"] != "collected"]
    if unavailable:
        warnings.append({"code": "source_unavailable", "source_ids": unavailable, "note": "Selected source could not support a coverage conclusion."})
    status = "needs_review" if decision == "coverage_review_required" or unavailable else "ok"
    source_index = [{**{k: src[k] for k in ("id", "kind", "role", "status", "observed_at", "published_at", "provider_date", "record_id", "record_id_origin", "provenance", "content_sha256")}, **({"metadata": src["metadata"]} if "metadata" in src else {}), "url": redact_url(src["url"])} for src in sources.values()]
    return {"schema_version": "1.0", "project": PROJECT, "analysis_method": METHOD, "status": status, "decision": decision, "scope": {"topic": topic, "reader_task": reader_task, "as_of": as_of, "source_ids": list(sources), "source_roles": [x["role"] for x in sources.values()]}, "summary": {"questions_analyzed": len(questions), "sources_analyzed": len(page_sources), "sources_excluded": 0, "coverage_rows": len(coverage), "suppressed_questions": len(suppressed), "review_questions": len(review), "briefs_created": int(brief is not None)}, "warnings": warnings, "source_index": source_index, "coverage": coverage, "brief": brief, "suppressed_question_ids": suppressed, "review_question_ids": review}
