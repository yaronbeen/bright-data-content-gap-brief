"""Bounded optional Bright Data ingestion with injectable HTTP transport."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import re
import ssl
import time
import multiprocessing
import threading
from urllib.parse import quote, urlsplit
from urllib.request import build_opener, HTTPSHandler, ProxyHandler, Request, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

from .core import PROJECT, ValidationError, _id, _object, _string, _utc, canonical_url, normalize_source_markdown, normalize_text, redact_url

API = "https://api.brightdata.com/request"
MAX_RESPONSE = 2 * 1024 * 1024
TRANSPORT_VERSION = "1.0"


@dataclass(frozen=True)
class HttpRequest:
    method: str
    url: str
    headers: dict[str, str]
    body: bytes
    timeout_seconds: int


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: bytes


class TransportError(RuntimeError):
    def __init__(self, code="transport_error"):
        self.code = code
        super().__init__(code)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _transport_worker(connection, transport, request):
    try:
        connection.send(("response", transport(request)))
    except TransportError as exc:
        code = exc.code if exc.code == "response_too_large" else "transport_error"
        try:
            connection.send(("transport_error", code))
        except Exception:
            pass
    except BaseException:
        try:
            connection.send(("transport_error", "transport_error"))
        except Exception:
            pass
    finally:
        connection.close()


def _bounded_transport(transport, request, *, deadline, monotonic=time.monotonic):
    """Run a synchronous transport in a killable process bounded by a deadline."""
    if threading.active_count() > 1:
        raise TransportError("transport_error")
    try:
        context = multiprocessing.get_context("fork")
    except ValueError:
        raise TransportError("transport_error")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_transport_worker, args=(sender, transport, request), daemon=True)
    try:
        process.start()
    except Exception:
        receiver.close()
        sender.close()
        raise TransportError("transport_error")
    sender.close()

    def stop_worker():
        if process.is_alive():
            process.kill()
        process.join(timeout=0.1)

    try:
        remaining = deadline - monotonic()
        if remaining <= 0 or not receiver.poll(remaining):
            stop_worker()
            raise TransportError("transport_error")
        try:
            kind, value = receiver.recv()
        except (EOFError, OSError):
            stop_worker()
            raise TransportError("transport_error")
        if monotonic() >= deadline:
            stop_worker()
            raise TransportError("transport_error")
        if kind == "transport_error":
            stop_worker()
            raise TransportError(value if value == "response_too_large" else "transport_error")
        if kind != "response":
            stop_worker()
            raise TransportError("transport_error")
        process.join(timeout=0.02)
        stop_worker()
        return value
    finally:
        receiver.close()
        if process.is_alive():
            stop_worker()
        process.close()


def urllib_transport(request: HttpRequest) -> HttpResponse:
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()), _NoRedirect())
    req = Request(request.url, data=request.body or None, headers=request.headers, method=request.method)
    try:
        with opener.open(req, timeout=request.timeout_seconds) as response:
            body = response.read(MAX_RESPONSE + 1)
            if len(body) > MAX_RESPONSE:
                raise TransportError("response_too_large")
            return HttpResponse(response.status, dict(response.headers), body)
    except HTTPError as exc:
        return HttpResponse(exc.code, dict(exc.headers), b"")
    except (URLError, TimeoutError, OSError):
        raise TransportError()


def _manifest(manifest: dict, *, live=False) -> list[dict]:
    _object(manifest, "manifest", {"schema_version", "project", "jobs"}, {"schema_version", "project", "jobs"})
    if manifest["schema_version"] != "1.0" or manifest["project"] != PROJECT:
        raise ValidationError("manifest schema/project mismatch")
    jobs = manifest["jobs"]
    if not isinstance(jobs, list) or not 1 <= len(jobs) <= 9:
        raise ValidationError("manifest must contain 1..9 jobs")
    seen, source_ids, search_count, owned_count, competing_count = set(), set(), 0, 0, 0
    normalized = []
    for raw in jobs:
        if not isinstance(raw, dict) or not isinstance(raw.get("kind"), str) or raw["kind"] not in {"web_page", "serp"}:
            raise ValidationError("unsupported collection job")
        jid = _id(raw.get("id"), "job.id")
        if jid in seen:
            raise ValidationError("job IDs must be unique")
        seen.add(jid)
        if raw["kind"] == "web_page":
            _object(raw, "web job", {"id", "kind", "role", "source_id", "url", "country"}, {"id", "kind", "role", "source_id", "url"})
            if not isinstance(raw["role"], str) or raw["role"] not in {"owned_article", "competing_article"}:
                raise ValidationError("unsupported web page role")
            source_id = _id(raw["source_id"], "source_id")
            if source_id in source_ids:
                raise ValidationError("web page source IDs must be unique")
            source_ids.add(source_id)
            url = canonical_url(raw["url"], live=live)
            country = raw.get("country")
            if country is not None and (not isinstance(country, str) or not re.fullmatch(r"[a-z]{2}", country)):
                raise ValidationError("country must be two lowercase letters")
            normalized.append({**raw, "source_id": source_id, "url": url, "country": country})
            owned_count += raw["role"] == "owned_article"
            competing_count += raw["role"] == "competing_article"
        else:
            _object(raw, "serp job", {"id", "kind", "role", "source_prefix", "query", "country", "language"}, {"id", "kind", "role", "source_prefix", "query", "country", "language"})
            if (not isinstance(raw["role"], str) or raw["role"] != "discovery"
                    or not isinstance(raw["language"], str) or raw["language"] != "en"
                    or not isinstance(raw["country"], str) or not re.fullmatch(r"[a-z]{2}", raw["country"])):
                raise ValidationError("SERP role/country/language is invalid")
            prefix = _id(raw["source_prefix"], "source_prefix")
            if len(prefix) > 47:
                raise ValidationError("source_prefix is too long")
            normalized.append({**raw, "query": _string(raw["query"], "query", 1, 200)})
            search_count += 1
    if search_count > 1 or owned_count > 5 or competing_count > 3:
        raise ValidationError("manifest exceeds Content Gap Brief scope")
    return normalized


def _hash(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def plan(manifest: dict) -> dict:
    jobs = _manifest(manifest)
    targets = []
    for job in jobs:
        if job["kind"] == "web_page":
            targets.append(job["url"])
        else:
            targets.append("https://www.google.com/search?q=" + quote(job["query"], safe="") + f"&gl={job['country']}&hl=en&pws=0&brd_json=1")
    return {"schema_version": "1.0", "project": PROJECT, "manifest_sha256": _hash(manifest), "requests_planned": len(jobs), "requests_made": 0, "targets": targets, "jobs": jobs}


def _source(source_id, kind, role, url, title, text, status, observed_at, provenance, metadata=None):
    if not isinstance(title, str):
        raise ValidationError("source title must be a string")
    try:
        title.encode("utf-8")
    except UnicodeEncodeError:
        raise ValidationError("source title is not valid UTF-8") from None
    stored, _ = normalize_source_markdown(text) if kind == "page" else normalize_text(text)
    source = {"id": source_id, "kind": kind, "role": role, "url": url, "title": title[:200] or "Selected public page", "text": stored, "status": status, "observed_at": observed_at, "published_at": None, "provider_date": None, "record_id": None, "record_id_origin": "none", "provenance": provenance}
    if kind == "search_result":
        source["metadata"] = metadata or {"serp_rank": None, "serp_global_rank": None}
    return source


def _source_url(value):
    url = canonical_url(value)
    if urlsplit(url).query:
        raise ValidationError("source URLs may not contain query strings")
    return url


def _normalize_serp_records(records, *, role, observed_at, source_prefix, provenance, retain_limit=5, reserved_ids=()):
    sources, ranks, warnings = [], [], []
    excluded = 0
    seen = set()
    for item in records:
        if not isinstance(item, dict) or not isinstance(item.get("link"), str):
            excluded += 1
            continue
        try:
            url = _source_url(item["link"])
        except ValidationError:
            excluded += 1
            continue
        if url in seen:
            excluded += 1
            continue
        seen.add(url)
        if len(sources) >= retain_limit:
            excluded += 1
            continue
        text = item.get("description") if isinstance(item.get("description"), str) else ""
        if len(text) > 2000:
            text = text[:2000]
            warnings.append({"code": "text_truncated", "source_ids": [], "note": "SERP description was capped at 2,000 characters."})
        sid = source_prefix + "-" + hashlib.sha256(url.encode()).hexdigest()[:16]
        if sid in reserved_ids:
            excluded += 1
            warnings.append({"code": "conflicting_record", "source_ids": [sid], "note": "Generated search-result source ID conflicts with an already retained source."})
            continue
        rank = item.get("rank") if type(item.get("rank")) is int and item["rank"] > 0 else None
        global_rank = item.get("global_rank") if type(item.get("global_rank")) is int and item["global_rank"] > 0 else None
        try:
            source = _source(sid, "search_result", role, url, item.get("title") if isinstance(item.get("title"), str) else "Search result", text, "collected" if text.strip() else "empty", observed_at, provenance, {"serp_rank": rank, "serp_global_rank": global_rank})
        except ValidationError:
            excluded += 1
            warnings.append({"code": "unsupported_content_format", "source_ids": [sid], "note": "SERP description contained unsupported markup and was excluded."})
            continue
        sources.append(source)
        ranks.append({"source_id": sid, "organic_rank": rank, "global_rank": global_rank})
        if rank is None:
            warnings.append({"code": "rank_missing", "source_ids": [sid], "note": "Organic rank was not supplied as a positive integer."})
    if excluded:
        warnings.append({"code": "provider_limit_exceeded", "source_ids": [source["id"] for source in sources], "note": "Invalid, duplicate, or over-limit search results were excluded."})
    return sources, ranks, excluded, warnings


def _same_url(value, canonical):
    try:
        return canonical_url(value) == canonical
    except ValidationError:
        return False


def normalize_export(kind, records, *, role, source_url, observed_at, source_prefix="import") -> dict:
    _utc(observed_at, "observed_at")
    if kind == "web_page":
        source_url = _source_url(source_url)
    else:
        canonical_url(source_url)
    prefix = _id(source_prefix, "source_prefix")
    if len(prefix) > 47:
        raise ValidationError("source_prefix is too long")
    warnings, sources, returned, excluded = [], [], 0, 0
    if kind == "web_page":
        if not isinstance(role, str) or role not in {"owned_article", "competing_article"} or not isinstance(records, str):
            raise ValidationError("web_page import requires raw Markdown and an article role")
        if len(records) > 50000:
            raise ValidationError("web_page import exceeds the 50,000 character page limit")
        returned = 1
        canonical, blocks = normalize_text(records)
        status = "collected" if canonical else "empty"
        heading = next((x["text"] for x in blocks if x["heading_level"] == 1), "Selected public page")
        sid = prefix + "-" + hashlib.sha256(source_url.encode()).hexdigest()[:16]
        sources.append(_source(sid, "page", role, source_url, heading, records, status, observed_at, "operator_supplied"))
    elif kind == "serp":
        if role != "discovery" or not isinstance(records, dict) or not isinstance(records.get("organic"), list):
            raise ValidationError("serp import requires an object with organic array")
        returned = len(records["organic"])
        sources, _, excluded, warnings = _normalize_serp_records(records["organic"], role=role, observed_at=observed_at, source_prefix=prefix, provenance="operator_supplied")
    else:
        raise ValidationError("unsupported import kind")
    status = "partial" if excluded else "complete"
    receipt = {"schema_version": "1.0", "project": PROJECT, "manifest_sha256": None, "status": status, "requests_made": 0, "returned_records": returned, "retained_records": len(sources), "excluded_records": excluded, "jobs": [], "warnings": warnings, "provider_cost_usd": None}
    return {"schema_version": "1.0", "project": PROJECT, "transport_contract_version": TRANSPORT_VERSION, "sources": sources, "receipt": receipt}


def _approval(manifest, approval, now, targets, max_requests):
    fields = {"schema_version", "project", "manifest_sha256", "expires_at", "max_requests", "max_retained_records", "approved_urls", "account_budget_confirmed", "target_permissions_confirmed", "remote_resolution_risk_accepted"}
    _object(approval, "approval", fields, fields)
    if approval["schema_version"] != "1.0" or approval["project"] != PROJECT or approval["manifest_sha256"] != _hash(manifest):
        raise ValidationError("approval does not match manifest")
    _utc(approval["expires_at"], "approval.expires_at")
    _utc(now, "now")
    if datetime.fromisoformat(approval["expires_at"][:-1] + "+00:00") <= datetime.fromisoformat(now[:-1] + "+00:00"):
        raise ValidationError("approval is expired")
    if type(approval["max_requests"]) is not int or approval["max_requests"] < max_requests:
        raise ValidationError("approval request allowance is insufficient")
    if type(approval["max_retained_records"]) is not int or not 1 <= approval["max_retained_records"] <= 50:
        raise ValidationError("approval retained-record cap is invalid")
    if not isinstance(approval["approved_urls"], list) or any(not isinstance(x, str) for x in approval["approved_urls"]):
        raise ValidationError("approved_urls must be a list of exact URLs")
    for approved_url in approval["approved_urls"]:
        canonical_url(approved_url)
    if any(approval[x] is not True for x in ("account_budget_confirmed", "target_permissions_confirmed", "remote_resolution_risk_accepted")):
        raise ValidationError("all approval attestations are required")
    if set(targets) - set(approval["approved_urls"]):
        raise ValidationError("approval does not include every exact target")
    return approval["max_retained_records"]


def _receipt(manifest_hash, jobs, sources, requests, returned=0, excluded=0, status="complete", warnings=None):
    return {"schema_version": "1.0", "project": PROJECT, "transport_contract_version": TRANSPORT_VERSION, "sources": sources, "receipt": {"schema_version": "1.0", "project": PROJECT, "manifest_sha256": manifest_hash, "status": status, "requests_made": requests, "returned_records": returned, "retained_records": len(sources), "excluded_records": excluded, "jobs": jobs, "warnings": warnings or [], "provider_cost_usd": None}}


def _provider_header_error(headers):
    if not isinstance(headers, dict):
        return "invalid_response"
    normalized = {}
    for name, value in headers.items():
        if not isinstance(name, str) or not isinstance(value, str):
            return "invalid_response"
        try:
            name.encode("ascii")
            value.encode("utf-8")
        except UnicodeError:
            return "invalid_response"
        if any(ord(char) < 32 and char != "\t" or ord(char) == 127 for char in name + value):
            return "invalid_response"
        normalized[name.casefold()] = value
    status_names = ("x-brd-status-code", "x-luminati-status-code")
    embedded_name = next((name for name in status_names if name in normalized), None)
    if embedded_name is not None:
        value = normalized[embedded_name]
        if not value.isascii() or not value.isdigit() or not 100 <= int(value) <= 599:
            return "invalid_response"
        if not 200 <= int(value) < 300:
            return "provider_target_error"
    error_names = ("x-brd-error-code", "x-brd-err-code", "x-luminati-error-code", "x-brd-error", "x-brd-err-msg", "x-luminati-error")
    if any(name in normalized for name in error_names):
        return "provider_target_error"
    return None


def _web_unlocker_body(text):
    """Accept raw Markdown or the documented status/headers/body success envelope."""
    if not text.lstrip().startswith("{"):
        return text, None
    try:
        envelope = json.loads(text)
    except json.JSONDecodeError:
        return text, None
    if not isinstance(envelope, dict) or not ({"status_code", "headers", "body"} & set(envelope)):
        return text, None
    if not {"status_code", "headers", "body"} <= set(envelope):
        return None, "response_contract_mismatch"
    status = envelope["status_code"]
    body = envelope["body"]
    if type(status) is not int or not 100 <= status <= 599 or not isinstance(body, str):
        return None, "invalid_response"
    try:
        body.encode("utf-8")
    except UnicodeEncodeError:
        return None, "invalid_response"
    header_error = _provider_header_error(envelope["headers"])
    if header_error:
        return None, header_error
    if not 200 <= status < 300:
        return None, "provider_target_error"
    return body, None


def _not_attempted(jobs):
    return [{"id": job["id"], "kind": job["kind"], "state": "not_attempted", "original_job": _public_job(job), "requested_records": None, "returned_records": 0, "retained_records": 0, "excluded_records": 0, "snapshot_id": None, "error_code": None, "query_metadata": None} for job in jobs]


def _public_job(job):
    public = dict(job)
    if "url" in public:
        public["url"] = redact_url(public["url"])
    if "query" in public:
        public["query"] = "[REDACTED]"
    return public


def collect(manifest, *, approval, api_key, zones, transport=urllib_transport, now, monotonic=time.monotonic, per_request_timeout_seconds=75, overall_timeout_seconds=675):
    jobs = _manifest(manifest, live=True)
    planned = plan(manifest)
    if not isinstance(api_key, str) or not api_key or any(ord(x) < 33 or ord(x) == 127 for x in api_key) or not isinstance(zones, dict):
        raise ValidationError("API key and zones are required")
    needed = {"web_unlocker" if x["kind"] == "web_page" else "serp" for x in jobs}
    if any(not isinstance(zones.get(x), str) or not zones[x] or any(ord(c) < 32 or ord(c) == 127 for c in zones[x]) for x in needed):
        raise ValidationError("required Bright Data zone is missing")
    if type(per_request_timeout_seconds) is not int or per_request_timeout_seconds < 1 or type(overall_timeout_seconds) is not int or overall_timeout_seconds < 1:
        raise ValidationError("collection deadlines must be positive integer seconds")
    if threading.active_count() > 1:
        raise ValidationError("live collection requires a single-threaded caller for cancellable request deadlines")
    try:
        multiprocessing.get_context("fork")
    except ValueError:
        raise ValidationError("live collection requires a fork-capable platform for cancellable request deadlines") from None
    retained_limit = _approval(manifest, approval, now, planned["targets"], len(jobs))
    sources, receipts, requests, returned, excluded, warnings = [], [], 0, 0, 0, []
    overall_deadline = monotonic() + overall_timeout_seconds
    for position, job in enumerate(jobs):
        if len(sources) >= retained_limit:
            receipts.extend(_not_attempted(jobs[position:]))
            warnings.append({"code": "provider_limit_exceeded", "source_ids": [source["id"] for source in sources], "note": "The cumulative approved retained-record limit was reached; later jobs were not attempted."})
            return _receipt(planned["manifest_sha256"], receipts, sources, requests, returned, excluded, "partial", warnings)
        request_started = monotonic()
        remaining_seconds = overall_deadline - request_started
        if remaining_seconds <= 0:
            receipts.extend(_not_attempted(jobs[position:]))
            warnings.append({"code": "overall_deadline_exceeded", "source_ids": [], "note": "The overall local deadline elapsed before another request began."})
            return _receipt(planned["manifest_sha256"], receipts, sources, requests, returned, excluded, "partial", warnings)
        if remaining_seconds < 1:
            receipts.extend(_not_attempted(jobs[position:]))
            warnings.append({"code": "deadline_budget_insufficient", "source_ids": [], "note": "Less than one full second remained, so another request was not started."})
            return _receipt(planned["manifest_sha256"], receipts, sources, requests, returned, excluded, "partial", warnings)
        target = planned["targets"][position]
        payload = {"zone": zones["web_unlocker" if job["kind"] == "web_page" else "serp"], "url": target, "format": "raw" if job["kind"] == "web_page" else "json"}
        if job["kind"] == "web_page":
            payload["data_format"] = "markdown"
            if job.get("country"):
                payload["country"] = job["country"]
        timeout_seconds = min(per_request_timeout_seconds, int(remaining_seconds))
        req = HttpRequest("POST", API, {"Authorization": "Bearer " + api_key, "Content-Type": "application/json"}, json.dumps(payload, separators=(",", ":")).encode(), timeout_seconds)
        requests += 1
        base = {"id": job["id"], "kind": job["kind"], "original_job": _public_job(job), "requested_records": None, "returned_records": 0, "retained_records": 0, "excluded_records": 0, "snapshot_id": None, "error_code": None, "query_metadata": None}
        request_deadline = min(overall_deadline, request_started + timeout_seconds)
        try:
            response = _bounded_transport(transport, req, deadline=request_deadline, monotonic=monotonic)
        except TransportError as exc:
            if exc.code == "response_too_large":
                receipts.append({**base, "state": "failed", "error_code": "response_too_large"})
                receipts.extend(_not_attempted(jobs[position + 1 :]))
                return _receipt(planned["manifest_sha256"], receipts, sources, requests, returned, excluded, "failed", warnings)
            receipts.append({**base, "state": "completion_unknown", "error_code": "transport_error"})
            receipts.extend(_not_attempted(jobs[position + 1 :]))
            return _receipt(planned["manifest_sha256"], receipts, sources, requests, returned, excluded, "completion_unknown", warnings)
        except Exception:
            receipts.append({**base, "state": "completion_unknown", "error_code": "transport_error"})
            receipts.extend(_not_attempted(jobs[position + 1 :]))
            return _receipt(planned["manifest_sha256"], receipts, sources, requests, returned, excluded, "completion_unknown", warnings)
        request_finished = monotonic()
        if request_finished - request_started >= timeout_seconds or request_finished >= overall_deadline:
            receipts.append({**base, "state": "completion_unknown", "error_code": "transport_error"})
            receipts.extend(_not_attempted(jobs[position + 1 :]))
            return _receipt(planned["manifest_sha256"], receipts, sources, requests, returned, excluded, "completion_unknown", warnings)
        if not isinstance(response, HttpResponse) or type(response.status) is not int or not 100 <= response.status <= 599 or not isinstance(response.headers, dict) or not isinstance(response.body, bytes):
            receipts.append({**base, "state": "failed", "error_code": "invalid_response"})
            receipts.extend(_not_attempted(jobs[position + 1 :]))
            return _receipt(planned["manifest_sha256"], receipts, sources, requests, returned, excluded, "failed", warnings)
        if len(response.body) > MAX_RESPONSE:
            receipts.append({**base, "state": "failed", "error_code": "response_too_large"})
            receipts.extend(_not_attempted(jobs[position + 1 :]))
            return _receipt(planned["manifest_sha256"], receipts, sources, requests, returned, excluded, "failed", warnings)
        header_error = _provider_header_error(response.headers)
        if header_error == "invalid_response":
            receipts.append({**base, "state": "failed", "error_code": "invalid_response"})
            receipts.extend(_not_attempted(jobs[position + 1 :]))
            return _receipt(planned["manifest_sha256"], receipts, sources, requests, returned, excluded, "failed", warnings)
        if not 200 <= response.status < 300 or header_error:
            error_code = "provider_http_error" if not 200 <= response.status < 300 else header_error
            receipts.append({**base, "state": "failed", "error_code": error_code})
            receipts.extend(_not_attempted(jobs[position + 1 :]))
            return _receipt(planned["manifest_sha256"], receipts, sources, requests, returned, excluded, "failed", warnings)
        try:
            text = response.body.decode("utf-8")
        except UnicodeDecodeError:
            receipts.append({**base, "state": "failed", "error_code": "invalid_response"})
            receipts.extend(_not_attempted(jobs[position + 1 :]))
            return _receipt(planned["manifest_sha256"], receipts, sources, requests, returned, excluded, "failed", warnings)
        if job["kind"] == "web_page":
            text, envelope_error = _web_unlocker_body(text)
            if envelope_error:
                receipts.append({**base, "state": "failed", "error_code": envelope_error})
                receipts.extend(_not_attempted(jobs[position + 1 :]))
                return _receipt(planned["manifest_sha256"], receipts, sources, requests, returned, excluded, "failed", warnings)
            if len(text) > 50000:
                returned += 1
                excluded += 1
                receipts.append({**base, "state": "failed", "returned_records": 1, "excluded_records": 1, "error_code": "text_too_long"})
                receipts.extend(_not_attempted(jobs[position + 1 :]))
                warnings.append({"code": "text_too_long", "source_ids": [], "note": "The paid page response exceeded the analyzable page limit and was not retained."})
                return _receipt(planned["manifest_sha256"], receipts, sources, requests, returned, excluded, "partial", warnings)
            try:
                canonical, blocks = normalize_text(text)
            except ValidationError:
                receipts.append({**base, "state": "failed", "error_code": "unsupported_content_format"})
                receipts.extend(_not_attempted(jobs[position + 1 :]))
                return _receipt(planned["manifest_sha256"], receipts, sources, requests, returned, excluded, "failed", warnings)
            heading = next((x["text"] for x in blocks if x["heading_level"] == 1), "Selected public page")
            src = _source(job["source_id"], "page", job["role"], job["url"], heading, text, "collected" if canonical else "empty", now, "bright_data")
            sources.append(src)
            receipts.append({**base, "state": "complete" if canonical else "empty", "returned_records": 1, "retained_records": 1})
            returned += 1
        else:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if not isinstance(parsed, dict) or not isinstance(parsed.get("organic"), list):
                receipts.append({**base, "state": "failed", "error_code": "invalid_response"})
                receipts.extend(_not_attempted(jobs[position + 1 :]))
                return _receipt(planned["manifest_sha256"], receipts, sources, requests, returned, excluded, "failed", warnings)
            capacity = retained_limit - len(sources)
            normalized_sources, ranks, job_excluded, job_warnings = _normalize_serp_records(parsed["organic"], role="discovery", observed_at=now, source_prefix=job["source_prefix"], provenance="bright_data", retain_limit=min(5, capacity), reserved_ids={source["id"] for source in sources})
            sources.extend(normalized_sources)
            returned += len(parsed["organic"])
            excluded += job_excluded
            warnings.extend(job_warnings)
            general = parsed.get("general") if isinstance(parsed.get("general"), dict) else {}
            effective_query = general.get("query") if isinstance(general.get("query"), str) else None
            detected_query = general.get("detected_query") if isinstance(general.get("detected_query"), str) else None
            spelling_present = bool(general.get("spelling") or general.get("corrected_query"))
            metadata = {"submitted_query": "[REDACTED]", "effective_query": "[REDACTED]" if effective_query is not None else None, "detected_query": "[REDACTED]" if detected_query is not None else None, "spelling_present": spelling_present, "result_ranks": ranks}
            if effective_query and effective_query != job["query"]:
                warnings.append({"code": "query_changed", "source_ids": [x["id"] for x in normalized_sources], "note": "Provider effective query differed from the submitted query."})
            if detected_query and detected_query != (effective_query or job["query"]) and not spelling_present:
                warnings.append({"code": "query_mismatch", "source_ids": [x["id"] for x in normalized_sources], "note": "Detected query differed without an explicit spelling correction; review discovery results."})
            receipts.append({**base, "state": "complete" if normalized_sources else "empty", "returned_records": len(parsed["organic"]), "retained_records": len(normalized_sources), "excluded_records": job_excluded, "query_metadata": metadata})
            if job_excluded and len(sources) >= retained_limit:
                receipts.extend(_not_attempted(jobs[position + 1 :]))
                return _receipt(planned["manifest_sha256"], receipts, sources, requests, returned, excluded, "partial", warnings)
    return _receipt(planned["manifest_sha256"], receipts, sources, requests, returned, excluded, "partial" if excluded else "complete", warnings)


def resume(receipt, *, approval, api_key, transport=urllib_transport, now):
    raise ValidationError("resume is unsupported because Content Gap Brief has no scraper jobs")
