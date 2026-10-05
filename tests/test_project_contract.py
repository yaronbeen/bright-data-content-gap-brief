"""Implementation-side checks for shared offline and provider boundaries."""

import copy
import hashlib
import json
import multiprocessing
from pathlib import Path

import pytest

from content_gap_brief.brightdata import HttpResponse, collect, normalize_export, plan, resume
from content_gap_brief.cli import main
from content_gap_brief.core import ValidationError, analyze, canonical_url
from content_gap_brief.export import render_csv, render_json, render_markdown

ROOT = Path(__file__).parents[1]


def demo():
    return json.loads((ROOT / "fixtures/demo.json").read_text())


def test_demo_is_populated_cited_and_deterministic(monkeypatch):
    monkeypatch.setenv("BRIGHT_DATA_API_KEY", "must-not-be-read")
    first = analyze(demo())
    second = analyze(demo())
    assert first == second
    assert first["brief"]["question_id"] == "q2"
    assert first["suppressed_question_ids"] == ["q1"]
    assert first["brief"]["worked_example_rows"][0]["missing_required_criteria_ids"] == ["retry"]
    assert first["brief"]["angle_basis_refs"][0]["quote"] == "Inspect the import error log."
    assert render_json(first) == render_json(second)


def test_invalid_reference_and_unknown_key_fail():
    bad = demo()
    bad["questions"][1]["question_ref"]["quote"] = "invented quote"
    with pytest.raises(ValidationError):
        analyze(bad)
    bad = demo()
    bad["unexpected"] = True
    with pytest.raises(ValidationError):
        analyze(bad)


def test_heading_only_owned_answer_does_not_suppress():
    data = demo()
    data["sources"][0]["text"] = "## CSV files can be imported.\n\nUnrelated body."
    report = analyze(data)
    owned = next(x for x in report["coverage"] if x["question_id"] == "q1" and x["source_id"] == "owned")
    assert owned["coverage_state"] == "no_related_passage_found_in_selected_text"


def test_renderers_escape_evidence_and_protect_csv_formulas():
    data = demo()
    data["questions"][0]["text"] = "=IMPORTXML(<script>)"
    data["criteria"][0]["label"] = "Check <script>alert(1)</script> [click](javascript:alert(1))"
    report = analyze(data)
    assert "&lt;script>" in render_markdown(report)
    assert "\\[click\\]\\(javascript:alert\\(1\\)\\)" in render_markdown(report)
    assert "'=IMPORTXML" in render_csv(report)
    assert "'  -formula" == __import__("content_gap_brief.export", fromlist=["_safe_csv"])._safe_csv("  -formula")


def test_cli_dry_run_and_collision_are_safe(tmp_path, capsys):
    assert main(["analyze", str(ROOT / "fixtures/demo.json"), "--out-dir", str(tmp_path), "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["requests_made"] == 0
    assert not list(tmp_path.iterdir())
    assert main(["analyze", str(ROOT / "fixtures/demo.json"), "--out-dir", str(tmp_path)]) == 0
    original = (tmp_path / "report.json").read_bytes()
    assert main(["analyze", str(ROOT / "fixtures/demo.json"), "--out-dir", str(tmp_path)]) == 2
    assert (tmp_path / "report.json").read_bytes() == original


def test_provider_import_is_allowlisted_and_offline():
    records = {"organic": [{"link": "https://docs.python.org/3/", "title": "Python", "description": "=A result", "username": "drop", "profile_url": "drop", "address": "drop"}]}
    library = normalize_export("serp", records, role="discovery", source_url="https://www.google.com/search?q=python", observed_at="2026-10-04T10:00:00Z", source_prefix="result")
    assert library["receipt"]["requests_made"] == 0
    assert set(library["sources"][0]) == {"id", "kind", "role", "url", "title", "text", "status", "observed_at", "published_at", "provider_date", "record_id", "record_id_origin", "provenance", "metadata"}
    assert "username" not in json.dumps(library)


def test_live_url_rejects_ip_fixture_and_sensitive_query():
    for url in ("https://127.0.0.1/page", "https://example.com/page", "https://docs.python.org/page?token=x"):
        with pytest.raises(ValidationError):
            canonical_url(url, live=True)


def test_collect_serializes_web_unlocker_once():
    manifest = {"schema_version": "1.0", "project": "content-gap-brief", "jobs": [{"id": "owned", "kind": "web_page", "role": "owned_article", "source_id": "owned", "url": "https://docs.python.org/3/"}]}
    planned = plan(manifest)
    approval = {"schema_version": "1.0", "project": "content-gap-brief", "manifest_sha256": planned["manifest_sha256"], "expires_at": "2026-10-06T00:00:00Z", "max_requests": 1, "max_retained_records": 5, "approved_urls": ["https://docs.python.org/3/"], "account_budget_confirmed": True, "target_permissions_confirmed": True, "remote_resolution_risk_accepted": True}
    manager = multiprocessing.Manager()
    calls = manager.list()

    def transport(request):
        calls.append(request)
        return HttpResponse(200, {}, json.dumps({"status_code": 200, "headers": {"content-type": "text/plain; charset=utf-8"}, "body": "# Python\n\nSelected body text."}).encode())

    try:
        library = collect(manifest, approval=approval, api_key="fake", zones={"web_unlocker": "zone"}, transport=transport, now="2026-10-05T00:00:00Z")
        assert len(calls) == 1
        assert calls[0].url == "https://api.brightdata.com/request"
        body = json.loads(calls[0].body)
    finally:
        manager.shutdown()
    assert body == {"zone": "zone", "url": "https://docs.python.org/3/", "format": "raw", "data_format": "markdown"}
    assert library["receipt"]["requests_made"] == 1
    assert library["sources"][0]["provenance"] == "bright_data"
    assert library["sources"][0]["text"] == "# Python\n\nSelected body text."


@pytest.mark.parametrize(
    "envelope,error_code",
    [
        ({"status_code": "200", "headers": {}, "body": "# Markdown"}, "invalid_response"),
        ({"status_code": 200, "headers": [], "body": "# Markdown"}, "invalid_response"),
        ({"status_code": 200, "headers": {}, "body": []}, "invalid_response"),
        ({"status_code": 429, "headers": {}, "body": "provider detail must not be kept"}, "provider_target_error"),
        ({"status_code": 200, "headers": {"X-Brd-Status-Code": "429"}, "body": "provider detail must not be kept"}, "provider_target_error"),
    ],
)
def test_web_unlocker_documented_envelope_is_validated(envelope, error_code):
    manifest = {"schema_version": "1.0", "project": "content-gap-brief", "jobs": [{"id": "owned", "kind": "web_page", "role": "owned_article", "source_id": "owned", "url": "https://docs.python.org/3/"}]}
    planned = plan(manifest)
    approval = {"schema_version": "1.0", "project": "content-gap-brief", "manifest_sha256": planned["manifest_sha256"], "expires_at": "2026-10-06T00:00:00Z", "max_requests": 1, "max_retained_records": 5, "approved_urls": planned["targets"], "account_budget_confirmed": True, "target_permissions_confirmed": True, "remote_resolution_risk_accepted": True}
    library = collect(manifest, approval=approval, api_key="fake", zones={"web_unlocker": "zone"}, transport=lambda _: HttpResponse(200, {}, json.dumps(envelope).encode()), now="2026-10-05T00:00:00Z")
    assert library["sources"] == []
    assert library["receipt"]["jobs"][0]["error_code"] == error_code
    assert "provider detail" not in json.dumps(library)


def test_collect_serializes_serp_and_retains_rank_metadata():
    manifest = {"schema_version": "1.0", "project": "content-gap-brief", "jobs": [{"id": "search", "kind": "serp", "role": "discovery", "source_prefix": "result", "query": "project import errors", "country": "us", "language": "en"}]}
    planned = plan(manifest)
    approval = {"schema_version": "1.0", "project": "content-gap-brief", "manifest_sha256": planned["manifest_sha256"], "expires_at": "2026-10-06T00:00:00Z", "max_requests": 1, "max_retained_records": 5, "approved_urls": planned["targets"], "account_budget_confirmed": True, "target_permissions_confirmed": True, "remote_resolution_risk_accepted": True}
    manager = multiprocessing.Manager()
    calls = manager.list()

    def transport(request):
        calls.append(request)
        body = {"organic": [{"rank": 2, "global_rank": 99, "title": "Guide", "link": "https://docs.python.org/3/", "description": "Import guide."}], "general": {"query": "project import errors"}}
        return HttpResponse(200, {}, json.dumps(body).encode())

    try:
        library = collect(manifest, approval=approval, api_key="fake", zones={"serp": "serp-zone"}, transport=transport, now="2026-10-05T00:00:00Z")
        request_body = json.loads(calls[0].body)
    finally:
        manager.shutdown()
    assert request_body == {"zone": "serp-zone", "url": planned["targets"][0], "format": "json"}
    assert library["receipt"]["jobs"][0]["query_metadata"]["result_ranks"][0]["organic_rank"] == 2
    assert library["sources"][0]["provenance"] == "bright_data"
    assert library["sources"][0]["metadata"] == {"serp_rank": 2, "serp_global_rank": 99}


def test_mismatched_approval_makes_zero_requests():
    manifest = {"schema_version": "1.0", "project": "content-gap-brief", "jobs": [{"id": "owned", "kind": "web_page", "role": "owned_article", "source_id": "owned", "url": "https://docs.python.org/3/"}]}
    approval = {"schema_version": "1.0", "project": "content-gap-brief", "manifest_sha256": "0" * 64, "expires_at": "2026-10-06T00:00:00Z", "max_requests": 1, "max_retained_records": 5, "approved_urls": ["https://docs.python.org/3/"], "account_budget_confirmed": True, "target_permissions_confirmed": True, "remote_resolution_risk_accepted": True}
    with pytest.raises(ValidationError):
        collect(manifest, approval=approval, api_key="fake", zones={"web_unlocker": "zone"}, transport=lambda _request: pytest.fail("transport must not be called"), now="2026-10-05T00:00:00Z")


def test_all_owned_answers_return_already_covered():
    data = demo()
    data["sources"][0]["text"] += "\n\nInspect the import error log."
    report = analyze(data)
    assert report["decision"] == "already_covered_by_declared_checks"
    assert report["brief"] is None
    assert report["suppressed_question_ids"] == ["q1", "q2"]


def test_related_owned_passage_requires_review():
    data = demo()
    data["sources"][0]["text"] += "\n\nOpen the import error log."
    report = analyze(data)
    assert report["decision"] == "coverage_review_required"
    assert report["status"] == "needs_review"
    assert "q2" in report["review_question_ids"]


def test_unavailable_owned_source_cannot_establish_gap():
    data = demo()
    data["sources"][0]["status"] = "unavailable"
    data["sources"][0]["text"] = ""
    report = analyze(data)
    assert report["brief"] is None
    assert report["decision"] == "coverage_review_required"


def test_stale_override_hash_and_dangling_example_fail():
    data = demo()
    data["coverage_overrides"] = [{"question_id": "q2", "source_id": "owned", "source_sha256": "0" * 64, "decision": "does_not_cover", "evidence": [], "rationale": "Reviewed manually."}]
    with pytest.raises(ValidationError):
        analyze(data)
    data = demo()
    data["worked_examples"][0]["has_criteria"] = ["missing"]
    with pytest.raises(ValidationError):
        analyze(data)


def test_raw_html_document_is_rejected():
    data = demo()
    data["sources"][0]["text"] = "<html><body>not Markdown</body></html>"
    with pytest.raises(ValidationError, match="unsupported_content_format"):
        analyze(data)


def test_serp_plan_uses_percent_encoding_and_no_requests():
    manifest = {"schema_version": "1.0", "project": "content-gap-brief", "jobs": [{"id": "search", "kind": "serp", "role": "discovery", "source_prefix": "result", "query": "import & retry #1", "country": "us", "language": "en"}]}
    result = plan(manifest)
    assert result["requests_made"] == 0
    assert result["targets"] == ["https://www.google.com/search?q=import%20%26%20retry%20%231&gl=us&hl=en&pws=0&brd_json=1"]


def test_embedded_provider_error_stops_without_echoing_secret():
    manifest = {"schema_version": "1.0", "project": "content-gap-brief", "jobs": [{"id": "one", "kind": "web_page", "role": "owned_article", "source_id": "one", "url": "https://docs.python.org/3/"}, {"id": "two", "kind": "web_page", "role": "owned_article", "source_id": "two", "url": "https://www.python.org/about/"}]}
    planned = plan(manifest)
    approval = {"schema_version": "1.0", "project": "content-gap-brief", "manifest_sha256": planned["manifest_sha256"], "expires_at": "2026-10-06T00:00:00Z", "max_requests": 2, "max_retained_records": 5, "approved_urls": planned["targets"], "account_budget_confirmed": True, "target_permissions_confirmed": True, "remote_resolution_risk_accepted": True}
    manager = multiprocessing.Manager()
    calls = manager.list()

    def transport(request):
        calls.append(request)
        return HttpResponse(200, {"X-Brd-Status-Code": "429", "X-Brd-Error": "sensitive provider text"}, b"sensitive body")

    try:
        library = collect(manifest, approval=approval, api_key="fake-" + "key", zones={"web_unlocker": "zone"}, transport=transport, now="2026-10-05T00:00:00Z")
    finally:
        manager.shutdown()
    serialized = json.dumps(library)
    assert library["receipt"]["requests_made"] == 1
    assert library["receipt"]["jobs"][1]["state"] == "not_attempted"
    assert "sensitive" not in serialized
    assert library["sources"] == []


@pytest.mark.parametrize(
    "response,error_code",
    [
        (HttpResponse(200, {}, b'{"status_code":200,"body":"wrapped"}'), "response_contract_mismatch"),
        (HttpResponse(200, {}, b"x" * (2 * 1024 * 1024 + 1)), "response_too_large"),
        (HttpResponse(200, {}, b"<html>raw html</html>"), "unsupported_content_format"),
    ],
)
def test_invalid_web_responses_never_become_evidence(response, error_code):
    manifest = {"schema_version": "1.0", "project": "content-gap-brief", "jobs": [{"id": "owned", "kind": "web_page", "role": "owned_article", "source_id": "owned", "url": "https://docs.python.org/3/"}]}
    planned = plan(manifest)
    approval = {"schema_version": "1.0", "project": "content-gap-brief", "manifest_sha256": planned["manifest_sha256"], "expires_at": "2026-10-06T00:00:00Z", "max_requests": 1, "max_retained_records": 5, "approved_urls": planned["targets"], "account_budget_confirmed": True, "target_permissions_confirmed": True, "remote_resolution_risk_accepted": True}
    library = collect(manifest, approval=approval, api_key="fake", zones={"web_unlocker": "zone"}, transport=lambda _: response, now="2026-10-05T00:00:00Z")
    assert library["sources"] == []
    assert library["receipt"]["jobs"][0]["error_code"] == error_code


def test_resume_is_rejected_before_transport():
    calls = []
    with pytest.raises(ValidationError, match="unsupported"):
        resume({}, approval={}, api_key="fake", transport=calls.append, now="2026-10-05T00:00:00Z")
    assert calls == []
