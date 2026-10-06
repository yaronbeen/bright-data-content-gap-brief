"""Regression tests for code and QA review findings."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tomllib

import pytest

from content_gap_brief.brightdata import HttpResponse, TransportError, collect, normalize_export, plan
from content_gap_brief.cli import main
from content_gap_brief.core import ValidationError, analyze, normalize_text
from content_gap_brief.export import render_csv, render_json, render_markdown

ROOT = Path(__file__).parents[1]
NOW = "2026-10-05T00:00:00Z"


def load_fixture(name):
    return json.loads((ROOT / "fixtures" / name).read_text(encoding="utf-8"))


def approval(value):
    planned = plan(value)
    return {
        "schema_version": "1.0",
        "project": "content-gap-brief",
        "manifest_sha256": planned["manifest_sha256"],
        "expires_at": "2026-10-06T00:00:00Z",
        "max_requests": len(value["jobs"]),
        "max_retained_records": 5,
        "approved_urls": planned["targets"],
        "account_budget_confirmed": True,
        "target_permissions_confirmed": True,
        "remote_resolution_risk_accepted": True,
    }


def test_imported_web_markdown_preserves_heading_structure():
    library = normalize_export(
        "web_page",
        "# Heading-only answer\n\nUnrelated body.",
        role="competing_article",
        source_url="https://example.com/article",
        observed_at=NOW,
    )

    _, blocks = normalize_text(library["sources"][0]["text"])
    assert [(block["text"], block["heading"]) for block in blocks] == [
        ("Heading-only answer", True),
        ("Unrelated body.", False),
    ]


def test_collected_web_markdown_preserves_heading_structure():
    value = {
        "schema_version": "1.0",
        "project": "content-gap-brief",
        "jobs": [{"id": "page", "kind": "web_page", "role": "owned_article", "source_id": "page", "url": "https://docs.python.org/3/"}],
    }
    library = collect(
        value,
        approval=approval(value),
        api_key="fake",
        zones={"web_unlocker": "web"},
        transport=lambda _: HttpResponse(200, {}, b"## Answer phrase\n\nBody text."),
        now=NOW,
    )

    _, blocks = normalize_text(library["sources"][0]["text"])
    assert blocks[0]["heading"] is True
    assert blocks[1]["heading"] is False


def test_imported_heading_only_phrase_cannot_make_candidate_eligible():
    data = load_fixture("demo.json")
    imported = normalize_export(
        "web_page",
        "# Inspect the import error log.\n\nUnrelated body.",
        role="competing_article",
        source_url="https://example.com/article",
        observed_at=NOW,
        source_prefix="candidate",
    )["sources"][0]
    imported["id"] = "competing"
    data["sources"][1] = imported
    data["questions"][1]["origin"] = "editor_inferred"
    data["questions"][1]["question_ref"] = None

    report = analyze(data)

    assert report["decision"] == "coverage_review_required"
    assert report["brief"] is None


def test_ranked_discovery_source_metadata_survives_analysis_validation():
    data = load_fixture("demo.json")
    source = normalize_export(
        "serp",
        {"organic": [{"rank": 4, "global_rank": 17, "link": "https://example.org/result", "description": "A synthetic search result."}]},
        role="discovery",
        source_url="https://www.google.com/search?q=synthetic",
        observed_at=NOW,
        source_prefix="search",
    )["sources"][0]
    data["sources"].append(source)

    report = analyze(data)

    indexed = next(item for item in report["source_index"] if item["id"] == source["id"])
    assert indexed["metadata"] == {"serp_rank": 4, "serp_global_rank": 17}


@pytest.mark.parametrize(
    "metadata",
    [
        {"serp_rank": True, "serp_global_rank": None},
        {"serp_rank": 1, "serp_global_rank": -1},
        {"serp_rank": 1, "serp_global_rank": 2, "provider_extra": "discarded"},
    ],
)
def test_search_result_metadata_is_strictly_allowlisted(metadata):
    data = load_fixture("demo.json")
    source = normalize_export(
        "serp",
        {"organic": [{"rank": 1, "link": "https://example.org/result", "description": "Synthetic result."}]},
        role="discovery",
        source_url="https://www.google.com/search?q=synthetic",
        observed_at=NOW,
        source_prefix="search",
    )["sources"][0]
    source["metadata"] = metadata
    data["sources"].append(source)
    with pytest.raises(ValidationError):
        analyze(data)


@pytest.mark.parametrize("text", ["Setext title\n=====", "Setext title\n-----"])
def test_setext_headings_are_explicitly_rejected(text):
    with pytest.raises(ValidationError, match="setext"):
        normalize_text(text)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda data: data["questions"][0].update(text=123),
        lambda data: data["questions"][0].update(text=""),
        lambda data: data["questions"][0].update(text="x" * 161),
        lambda data: data["questions"][0].update(origin=[]),
        lambda data: data["criteria"][0].update(question_id=[]),
        lambda data: data["worked_examples"][0].update(has_criteria=[[]]),
        lambda data: data["coverage_overrides"].append({"question_id": [], "source_id": "owned", "source_sha256": "0" * 64, "decision": "covers", "evidence": [], "rationale": "x"}),
        lambda data: data["sources"][0].update(role=[]),
        lambda data: data["sources"][0].update(kind=1),
        lambda data: data["sources"][0].update(status=[]),
        lambda data: data["sources"][0].update(record_id_origin=[]),
        lambda data: data["sources"][0].update(provenance=[]),
        lambda data: data["sources"][0].update(metadata=None),
    ],
)
def test_all_malformed_nested_fields_raise_validation_error(mutate):
    data = load_fixture("demo.json")
    mutate(data)
    with pytest.raises(ValidationError):
        analyze(data)


@pytest.mark.parametrize(
    "library",
    [
        [],
        {"project": "content-gap-brief", "sources": []},
        {"schema_version": "1.0", "project": "content-gap-brief", "transport_contract_version": "1.0", "sources": "not-a-list", "receipt": {}},
        {"schema_version": "1.0", "project": "content-gap-brief", "transport_contract_version": "1.0", "sources": [], "receipt": {}},
        {"schema_version": "1.0", "project": "content-gap-brief", "transport_contract_version": "1.0", "sources": [], "receipt": {"schema_version": "1.0", "project": "content-gap-brief", "manifest_sha256": None, "status": [], "requests_made": 0, "returned_records": 0, "retained_records": 0, "excluded_records": 0, "jobs": [], "warnings": [], "provider_cost_usd": None}},
        {"schema_version": "1.0", "project": "content-gap-brief", "transport_contract_version": "1.0", "sources": [], "receipt": {"schema_version": "1.0", "project": "content-gap-brief", "manifest_sha256": None, "status": "complete", "requests_made": True, "returned_records": 0, "retained_records": 0, "excluded_records": 0, "jobs": [None], "warnings": [], "provider_cost_usd": None}},
        {"schema_version": "1.0", "project": "content-gap-brief", "transport_contract_version": "1.0", "sources": [], "receipt": {}, "unexpected": True},
    ],
)
def test_invalid_source_library_returns_structured_exit_2(tmp_path, capsys, library):
    library_path = tmp_path / "library.json"
    library_path.write_text(json.dumps(library), encoding="utf-8")

    result = main(["analyze", str(ROOT / "fixtures/demo.json"), "--sources", str(library_path), "--out-dir", str(tmp_path / "out")])

    assert result == 2
    error = json.loads(capsys.readouterr().err)
    assert error == {"code": "invalid_input", "message": "Input, flags, or filesystem state is invalid; no secret or provider body was retained.", "requests_made": 0}
    assert not (tmp_path / "out").exists()


def test_provider_import_list_role_returns_structured_exit_2(tmp_path, capsys):
    source_file = tmp_path / "provider.md"
    source_file.write_text("Synthetic page text.", encoding="utf-8")

    result = main([
        "import-provider", str(source_file), "--kind", "web_page", "--role", "[]",
        "--source-url", "https://example.com/page", "--observed-at", NOW,
        "--out", str(tmp_path / "library.json"),
    ])

    assert result == 2
    error = json.loads(capsys.readouterr().err)
    assert error == {"code": "invalid_input", "message": "Input, flags, or filesystem state is invalid; no secret or provider body was retained.", "requests_made": 0}
    assert not (tmp_path / "library.json").exists()


def test_malformed_unicode_authority_returns_structured_exit_2(tmp_path, capsys):
    data = load_fixture("demo.json")
    data["sources"][0]["url"] = "https://broken\ud800host.example/page"
    input_path = tmp_path / "malformed-url.json"
    input_path.write_text(json.dumps(data, ensure_ascii=True), encoding="utf-8")

    result = main(["analyze", str(input_path), "--out-dir", str(tmp_path / "out")])

    assert result == 2
    error = json.loads(capsys.readouterr().err)
    assert error == {"code": "invalid_input", "message": "Input, flags, or filesystem state is invalid; no secret or provider body was retained.", "requests_made": 0}
    assert not (tmp_path / "out").exists()


def test_malformed_percent_approval_url_returns_structured_exit_2(tmp_path, monkeypatch, capsys):
    from content_gap_brief.brightdata import collect as real_collect, plan

    manifest = {
        "schema_version": "1.0",
        "project": "content-gap-brief",
        "jobs": [{"id": "owned", "kind": "web_page", "role": "owned_article", "source_id": "owned", "url": "https://docs.python.org/3/"}],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    planned = plan(manifest)
    approval = {
        "schema_version": "1.0",
        "project": "content-gap-brief",
        "manifest_sha256": planned["manifest_sha256"],
        "expires_at": "2099-01-01T00:00:00Z",
        "max_requests": 1,
        "max_retained_records": 5,
        "approved_urls": ["https://docs.python.org/3/", "https://example.org/page?%ZZ=bad"],
        "account_budget_confirmed": True,
        "target_permissions_confirmed": True,
        "remote_resolution_risk_accepted": True,
    }
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(json.dumps(approval), encoding="utf-8")
    calls = []

    def injected_collect(manifest_arg, **kwargs):
        return real_collect(manifest_arg, transport=calls.append, now="2026-10-05T00:00:00Z", **{k: v for k, v in kwargs.items() if k != "now"})

    monkeypatch.setattr("content_gap_brief.cli.collect", injected_collect)
    monkeypatch.setenv("BRIGHT_DATA_API_KEY", "fake")
    monkeypatch.setenv("BRIGHT_DATA_WEB_UNLOCKER_ZONE", "zone")

    result = main(["collect", str(manifest_path), "--out", str(tmp_path / "library.json"), "--live", "--accept-charges", "--approval", str(approval_path)])

    assert result == 2
    error = json.loads(capsys.readouterr().err)
    assert error == {"code": "invalid_input", "message": "Input, flags, or filesystem state is invalid; no secret or provider body was retained.", "requests_made": 0}
    assert calls == []
    assert not (tmp_path / "library.json").exists()


def test_observed_question_reference_is_preserved_in_report_and_markdown():
    report = analyze(load_fixture("demo.json"))
    rows = [row for row in report["coverage"] if row["question_id"] == "q2"]

    assert all(row["question_ref"] == {"source_id": "competing", "block_id": "b0001", "quote": "How do I check a failed import?"} for row in rows)
    markdown = render_markdown(report)
    assert "Observed question source" in markdown
    assert "competing/b0001" in markdown
    assert "How do I check a failed import?" in markdown


def test_leading_head_document_is_rejected_as_raw_html():
    with pytest.raises(ValidationError, match="unsupported_content_format"):
        normalize_text("<head><title>Raw page</title></head><body>Text</body>")


@pytest.mark.parametrize(
    "text",
    [
        "Safe prefix. <div>phrase hidden in markup</div>. Safe suffix.",
        "Safe prefix. <!-- phrase hidden in comment -->. Safe suffix.",
        "Safe prefix. <script>phrase hidden in script</script>. Safe suffix.",
        "Safe prefix. <style>.phrase { content: 'phrase hidden in style'; }</style>. Safe suffix.",
        "Safe prefix. <script src='remote.js'> hidden content",
    ],
)
def test_html_regions_anywhere_are_rejected_before_phrase_analysis(text):
    with pytest.raises(ValidationError, match="unsupported_content_format"):
        normalize_text(text)


@pytest.mark.parametrize("argv", [[], ["analyze"], ["collect"]])
def test_argparse_errors_are_structured_json(argv, capsys):
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 2
    error = json.loads(capsys.readouterr().err)
    assert error["code"] == "invalid_arguments"
    assert error["requests_made"] == 0
    assert "usage:" not in error["message"].casefold()


@pytest.mark.parametrize("name", ["demo", "no-candidate"])
def test_golden_fixture_outputs_are_exact_bytes(name):
    report = analyze(load_fixture(f"{name}.json"))
    expected = ROOT / "fixtures" / "expected" if name == "demo" else ROOT / "fixtures" / "expected" / name

    assert render_json(report).encode() == (expected / "report.json").read_bytes()
    assert render_markdown(report).encode() == (expected / "brief.md").read_bytes()
    assert render_csv(report).encode() == (expected / "coverage.csv").read_bytes()


def test_python_metadata_matches_tested_versions_and_console_entrypoint():
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert metadata["project"]["requires-python"] == ">=3.11,<3.13"
    assert metadata["project"]["classifiers"] == [
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ]
    assert metadata["project"]["scripts"] == {"content-gap-brief": "content_gap_brief.cli:main"}


@pytest.mark.parametrize(
    "job",
    [
        {"id": "bad", "kind": [], "role": "owned_article", "source_id": "bad", "url": "https://docs.python.org/3/"},
        {"id": "bad", "kind": "web_page", "role": [], "source_id": "bad", "url": "https://docs.python.org/3/"},
        {"id": "bad", "kind": "serp", "role": "discovery", "source_prefix": "search", "query": "test", "country": [], "language": "en"},
    ],
)
def test_malformed_manifest_values_raise_validation_error_before_transport(job):
    manifest = {"schema_version": "1.0", "project": "content-gap-brief", "jobs": [job]}
    with pytest.raises(ValidationError):
        plan(manifest)


@pytest.mark.parametrize(
    "transport_error,expected_status,expected_code",
    [
        (TransportError("response_too_large"), "failed", "response_too_large"),
        (TransportError("transport_error"), "completion_unknown", "transport_error"),
    ],
)
def test_transport_errors_keep_known_response_failure_distinct(transport_error, expected_status, expected_code):
    manifest = {"schema_version": "1.0", "project": "content-gap-brief", "jobs": [{"id": "page", "kind": "web_page", "role": "owned_article", "source_id": "page", "url": "https://docs.python.org/3/"}]}
    attestation = approval(manifest)

    def transport(_):
        raise transport_error

    library = collect(manifest, approval=attestation, api_key="fake", zones={"web_unlocker": "web"}, transport=transport, now=NOW)

    assert library["receipt"]["status"] == expected_status
    assert library["receipt"]["jobs"][0]["error_code"] == expected_code


def test_failed_collection_receipt_returns_exit_3(tmp_path, monkeypatch, capsys):
    manifest = {
        "schema_version": "1.0",
        "project": "content-gap-brief",
        "jobs": [{"id": "owned", "kind": "web_page", "role": "owned_article", "source_id": "owned", "url": "https://docs.python.org/3/"}],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    receipt = {
        "schema_version": "1.0",
        "project": "content-gap-brief",
        "transport_contract_version": "1.0",
        "sources": [],
        "receipt": {"schema_version": "1.0", "project": "content-gap-brief", "manifest_sha256": "0" * 64, "status": "failed", "requests_made": 1, "returned_records": 0, "retained_records": 0, "excluded_records": 0, "jobs": [], "warnings": [], "provider_cost_usd": None},
    }
    monkeypatch.setattr("content_gap_brief.cli.collect", lambda *args, **kwargs: receipt)
    monkeypatch.setenv("BRIGHT_DATA_API_KEY", "fake")
    monkeypatch.setenv("BRIGHT_DATA_WEB_UNLOCKER_ZONE", "zone")
    monkeypatch.setattr("content_gap_brief.cli.datetime", type("FixedDateTime", (), {"now": staticmethod(lambda tz: __import__("datetime").datetime(2026, 10, 5, tzinfo=tz))}))

    result = main(["collect", str(manifest_path), "--out", str(tmp_path / "library.json"), "--live", "--accept-charges", "--approval", str(manifest_path)])

    assert result == 3
    assert json.loads(capsys.readouterr().out) == {"status": "failed", "requests_made": 1}


@pytest.mark.parametrize("status", ["partial", "pending", "completion_unknown"])
def test_uncertain_or_partial_collection_returns_exit_4(tmp_path, monkeypatch, capsys, status):
    manifest = {
        "schema_version": "1.0",
        "project": "content-gap-brief",
        "jobs": [{"id": "owned", "kind": "web_page", "role": "owned_article", "source_id": "owned", "url": "https://docs.python.org/3/"}],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    library = {"receipt": {"status": status, "requests_made": 1}}
    monkeypatch.setattr("content_gap_brief.cli.collect", lambda *args, **kwargs: library)
    monkeypatch.setenv("BRIGHT_DATA_API_KEY", "fake")
    monkeypatch.setenv("BRIGHT_DATA_WEB_UNLOCKER_ZONE", "zone")
    monkeypatch.setattr("content_gap_brief.cli.datetime", type("FixedDateTime", (), {"now": staticmethod(lambda tz: __import__("datetime").datetime(2026, 10, 5, tzinfo=tz))}))

    result = main(["collect", str(manifest_path), "--out", str(tmp_path / "library.json"), "--live", "--accept-charges", "--approval", str(manifest_path)])

    assert result == 4
    assert json.loads(capsys.readouterr().out) == {"status": status, "requests_made": 1}


def test_collection_write_error_reports_requests_already_made(tmp_path, monkeypatch, capsys):
    manifest = {
        "schema_version": "1.0",
        "project": "content-gap-brief",
        "jobs": [{"id": "owned", "kind": "web_page", "role": "owned_article", "source_id": "owned", "url": "https://docs.python.org/3/"}],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    approval_path = tmp_path / "approval.json"
    approval_path.write_text("{}", encoding="utf-8")
    receipt = {
        "schema_version": "1.0",
        "project": "content-gap-brief",
        "transport_contract_version": "1.0",
        "sources": [],
        "receipt": {"schema_version": "1.0", "project": "content-gap-brief", "manifest_sha256": "0" * 64, "status": "failed", "requests_made": 1, "returned_records": 0, "retained_records": 0, "excluded_records": 0, "jobs": [], "warnings": [], "provider_cost_usd": None},
    }
    monkeypatch.setattr("content_gap_brief.cli.collect", lambda *args, **kwargs: receipt)
    monkeypatch.setattr("content_gap_brief.cli._atomic", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full")))
    monkeypatch.setenv("BRIGHT_DATA_API_KEY", "fake")
    monkeypatch.setenv("BRIGHT_DATA_WEB_UNLOCKER_ZONE", "zone")
    monkeypatch.setattr("content_gap_brief.cli.datetime", type("FixedDateTime", (), {"now": staticmethod(lambda tz: __import__("datetime").datetime(2026, 10, 5, tzinfo=tz))}))

    result = main(["collect", str(manifest_path), "--out", str(tmp_path / "library.json"), "--live", "--accept-charges", "--approval", str(approval_path)])

    assert result == 2
    error = json.loads(capsys.readouterr().err)
    assert error["requests_made"] == 1
    assert error["code"] == "filesystem_error"


def test_collection_destination_race_preserves_file_and_reports_request_count(tmp_path, monkeypatch, capsys):
    manifest = {
        "schema_version": "1.0",
        "project": "content-gap-brief",
        "jobs": [{"id": "owned", "kind": "web_page", "role": "owned_article", "source_id": "owned", "url": "https://docs.python.org/3/"}],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    approval_path = tmp_path / "approval.json"
    approval_path.write_text("{}", encoding="utf-8")
    destination = tmp_path / "library.json"
    library = {"receipt": {"status": "complete", "requests_made": 1}}
    monkeypatch.setattr("content_gap_brief.cli.collect", lambda *args, **kwargs: library)
    real_link = os.link

    def race(source, target):
        destination.write_text("racer", encoding="utf-8")
        return real_link(source, target)

    monkeypatch.setattr("content_gap_brief.cli.os.link", race)
    monkeypatch.setenv("BRIGHT_DATA_API_KEY", "fake")
    monkeypatch.setenv("BRIGHT_DATA_WEB_UNLOCKER_ZONE", "zone")
    monkeypatch.setattr("content_gap_brief.cli.datetime", type("FixedDateTime", (), {"now": staticmethod(lambda tz: __import__("datetime").datetime(2026, 10, 5, tzinfo=tz))}))

    result = main(["collect", str(manifest_path), "--out", str(destination), "--live", "--accept-charges", "--approval", str(approval_path)])

    assert result == 2
    assert destination.read_text(encoding="utf-8") == "racer"
    error = json.loads(capsys.readouterr().err)
    assert error["code"] == "filesystem_error"
    assert error["requests_made"] == 1


def test_atomic_single_file_no_clobber_survives_destination_race(tmp_path, monkeypatch):
    destination = tmp_path / "result.json"
    real_link = os.link

    def race(source, target):
        destination.write_text("racer", encoding="utf-8")
        return real_link(source, target)

    monkeypatch.setattr("content_gap_brief.cli.os.link", race)
    with pytest.raises(FileExistsError):
        from content_gap_brief.cli import _atomic

        _atomic(destination, "generated", overwrite=False)
    assert destination.read_text(encoding="utf-8") == "racer"


def test_readme_examples_exit_codes_synthetic_export_and_canonical_docs():
    readme = (ROOT / "docs" / "technical-guide.md").read_text(encoding="utf-8")
    blocks = [json.loads(value) for value in __import__("re").findall(r"```json\n(.*?)\n```", readme, __import__("re").S)]
    manifest, approval = blocks[0], blocks[1]
    planned = plan(manifest)
    assert planned["manifest_sha256"] == approval["manifest_sha256"]
    assert planned["targets"] == approval["approved_urls"]
    assert "receipt status `failed`" in readme and "returns exit code `3`" in readme
    assert "`completion_unknown`" in readme and "Exit `4` means" in readme
    assert "invented `fixtures/web-page.md`" in readme
    assert "Any HTML tag, comment, declaration" in readme
    assert "metadata.serp_rank" in readme and "metadata.serp_global_rank" in readme
    assert "live collection also emits a job-level rank list" in readme
    assert "killable worker process" in readme
    assert "fails closed unless the platform supports `fork`" in readme
    assert "documented JSON success envelope" in readme
    assert "https://docs.brightdata.com/api-reference/rest-api/unlocker/unlock-website\n" in readme
    assert "https://docs.brightdata.com/api-reference/rest-api/serp/serp-api\n" in readme
