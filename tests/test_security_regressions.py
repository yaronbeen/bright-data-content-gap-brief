"""Regression tests for the security review blockers."""

from __future__ import annotations

import json
import hashlib
import multiprocessing
from pathlib import Path
import threading
import time
import tomllib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote

import pytest

import content_gap_brief.cli as cli
import content_gap_brief.core as core
from content_gap_brief.brightdata import HttpRequest, HttpResponse, TransportError, _bounded_transport, collect, normalize_export, plan, urllib_transport
from content_gap_brief.core import ValidationError, analyze, canonical_url
from content_gap_brief.export import render_json, render_markdown

ROOT = Path(__file__).parents[1]
NOW = "2026-10-05T00:00:00Z"


def demo():
    return json.loads((ROOT / "fixtures/demo.json").read_text())


def web_job(job_id, source_id, url="https://docs.python.org/3/"):
    return {"id": job_id, "kind": "web_page", "role": "owned_article", "source_id": source_id, "url": url}


def serp_job():
    return {"id": "search", "kind": "serp", "role": "discovery", "source_prefix": "result", "query": "private launch phrase", "country": "us", "language": "en"}


def manifest(*jobs):
    return {"schema_version": "1.0", "project": "content-gap-brief", "jobs": list(jobs)}


def exact_targets(value):
    targets = []
    for job in value["jobs"]:
        if job["kind"] == "web_page":
            targets.append(job["url"])
        else:
            targets.append("https://www.google.com/search?q=" + quote(job["query"], safe="") + f"&gl={job['country']}&hl=en&pws=0&brd_json=1")
    return targets


def approval(value, *, retained, requests=None):
    return {
        "schema_version": "1.0",
        "project": "content-gap-brief",
        "manifest_sha256": plan(value)["manifest_sha256"],
        "expires_at": "2026-10-06T00:00:00Z",
        "max_requests": requests or len(value["jobs"]),
        "max_retained_records": retained,
        "approved_urls": exact_targets(value),
        "account_budget_confirmed": True,
        "target_permissions_confirmed": True,
        "remote_resolution_risk_accepted": True,
    }


def test_cumulative_retention_cap_trims_serp_and_stops_later_calls():
    value = manifest(
        web_job("page-one", "page-one"),
        serp_job(),
        web_job("page-two", "page-two", "https://www.python.org/about/"),
    )
    responses = [
        HttpResponse(200, {}, b"# Page\n\nUseful body."),
        HttpResponse(
            200,
            {},
            json.dumps(
                {
                    "organic": [
                        {"rank": 1, "link": "https://docs.python.org/3/library/", "description": "One"},
                        {"rank": 2, "link": "https://docs.python.org/3/tutorial/", "description": "Two"},
                        {"rank": 3, "link": "https://docs.python.org/3/reference/", "description": "Three"},
                    ]
                }
            ).encode(),
        ),
    ]

    def transport(request):
        request_body = json.loads(request.body)
        return responses[0] if request_body["zone"] == "web" else responses[1]

    library = collect(
        value,
        approval=approval(value, retained=2),
        api_key="fake",
        zones={"web_unlocker": "web", "serp": "serp"},
        transport=transport,
        now=NOW,
    )

    assert library["receipt"]["requests_made"] == 2
    assert len(library["sources"]) == 2
    assert library["receipt"]["returned_records"] == 4
    assert library["receipt"]["retained_records"] == 2
    assert library["receipt"]["excluded_records"] == 2
    assert library["receipt"]["jobs"][1]["retained_records"] == 1
    assert library["receipt"]["jobs"][1]["excluded_records"] == 2
    assert library["receipt"]["jobs"][2]["state"] == "not_attempted"
    assert library["receipt"]["status"] == "partial"


def test_cumulative_retention_cap_is_checked_before_next_page_call():
    value = manifest(web_job("one", "one"), web_job("two", "two", "https://www.python.org/about/"))
    def transport(_request):
        return HttpResponse(200, {}, b"Body")

    library = collect(value, approval=approval(value, retained=1), api_key="fake", zones={"web_unlocker": "web"}, transport=transport, now=NOW)

    assert library["receipt"]["requests_made"] == 1
    assert library["receipt"]["jobs"][1]["state"] == "not_attempted"
    assert library["receipt"]["status"] == "partial"


@pytest.mark.parametrize(
    "url",
    [
        "https://docs.python.org/3/?campaign=normal",
        "https://docs.python.org/3/?%58%2d%41%6dz%2dSignature=signed",
        "https://docs.python.org/3/?x_amz_credential=signed",
        "https://docs.python.org/3/?AUTHORIZATION=Bearer",
        "https://docs.python.org/3/?session%2Did=value",
    ],
)
def test_live_page_targets_reject_all_queries_and_encoded_credentials(url):
    with pytest.raises(ValidationError):
        canonical_url(url, live=True)


def test_url_hostname_unicode_error_is_wrapped_as_validation_error(monkeypatch):
    class ParsedUrl:
        scheme = "https"
        username = None
        password = None
        fragment = ""
        port = None
        path = "/page"
        query = ""

        @property
        def hostname(self):
            raise UnicodeError("malformed authority")

    monkeypatch.setattr(core, "urlsplit", lambda _value: ParsedUrl())

    with pytest.raises(ValidationError, match="url is invalid"):
        canonical_url("https://synthetic.example/page")


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/page?%61pi%5Fkey=value",
        "https://example.com/page?X-Amz-%43redential=value",
        "https://example.com/page?x-goog-signature=value",
        "https://example.com/page?session%2Did=value",
        "https://example.com/page?%2561pi%255Fkey=value",
        "https://example.com/page?AWSAccessKeyId=value",
        "https://example.com/page?%EF%BD%81%EF%BD%90%EF%BD%89_key=value",
    ],
)
def test_offline_urls_reject_normalized_percent_decoded_credential_keys(url):
    with pytest.raises(ValidationError):
        canonical_url(url)


def test_approval_rejects_extra_credential_bearing_url_before_request():
    value = manifest(web_job("page", "page"))
    private_approval = approval(value, retained=5)
    private_approval["approved_urls"].append("https://docs.python.org/3/?X-Amz-Signature=signed")
    calls = []

    with pytest.raises(ValidationError):
        collect(value, approval=private_approval, api_key="fake", zones={"web_unlocker": "web"}, transport=calls.append, now=NOW)

    assert calls == []


def test_query_values_are_redacted_from_console_and_report_but_hash_is_exact(tmp_path, capsys):
    value = manifest(serp_job())
    planned = plan(value)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(value), encoding="utf-8")
    assert cli.main(["collect", str(manifest_path), "--out", str(tmp_path / "library.json"), "--dry-run"]) == 0
    assert "private" not in capsys.readouterr().out

    changed = manifest({**serp_job(), "query": "different private phrase"})
    assert planned["manifest_sha256"] != plan(changed)["manifest_sha256"]

    data = demo()
    data["sources"][0]["url"] = "https://example.com/owned?campaign=top-secret-value"
    report = analyze(data)
    rendered = render_json(report) + render_markdown(report)
    assert "top-secret-value" not in rendered
    assert "campaign" in rendered


def test_serp_sources_and_rank_metadata_are_filtered_atomically():
    value = manifest(serp_job())
    response = {
        "organic": [
            {"rank": 99, "link": "http://invalid.example/path", "description": "Invalid"},
            {"rank": 2, "global_rank": 20, "link": "https://docs.python.org/3/", "description": "First"},
            {"rank": 3, "global_rank": 30, "link": "https://docs.python.org/3/", "description": "Duplicate"},
            {"link": "https://www.python.org/about/", "description": "Second"},
        ]
    }
    library = collect(
        value,
        approval=approval(value, retained=5),
        api_key="fake",
        zones={"serp": "serp"},
        transport=lambda _: HttpResponse(200, {}, json.dumps(response).encode()),
        now=NOW,
    )

    ranks = library["receipt"]["jobs"][0]["query_metadata"]["result_ranks"]
    assert [source["url"] for source in library["sources"]] == ["https://docs.python.org/3/", "https://www.python.org/about/"]
    assert [rank["organic_rank"] for rank in ranks] == [2, None]
    assert [rank["global_rank"] for rank in ranks] == [20, None]
    assert [rank["source_id"] for rank in ranks] == [source["id"] for source in library["sources"]]
    assert library["receipt"]["excluded_records"] == 2


def test_serp_generated_id_collision_with_page_source_is_excluded_atomically():
    candidate_url = "https://docs.python.org/3/"
    generated_id = "result-" + hashlib.sha256(candidate_url.encode()).hexdigest()[:16]
    value = manifest(web_job("page", generated_id), serp_job())
    response = {"organic": [{"rank": 1, "link": candidate_url, "description": "Duplicate source identity."}]}
    def transport(request):
        if json.loads(request.body)["zone"] == "web":
            return HttpResponse(200, {}, b"Page body.")
        return HttpResponse(200, {}, json.dumps(response).encode())

    library = collect(value, approval=approval(value, retained=5), api_key="fake", zones={"web_unlocker": "web", "serp": "serp"}, transport=transport, now=NOW)

    assert [source["id"] for source in library["sources"]] == [generated_id]
    assert library["receipt"]["retained_records"] == 1
    assert library["receipt"]["excluded_records"] == 1
    assert library["receipt"]["jobs"][1]["query_metadata"]["result_ranks"] == []
    assert library["receipt"]["jobs"][1]["excluded_records"] == 1


def test_page_import_rejects_text_over_50000_characters():
    with pytest.raises(ValidationError, match="50,000"):
        normalize_export(
            "web_page",
            "x" * 50001,
            role="owned_article",
            source_url="https://example.com/page",
            observed_at=NOW,
        )


def test_page_import_list_role_raises_validation_error():
    with pytest.raises(ValidationError):
        normalize_export(
            "web_page",
            "Synthetic page text.",
            role=[],
            source_url="https://example.com/page",
            observed_at=NOW,
        )


def test_imported_page_library_rejects_query_bearing_source_url():
    with pytest.raises(ValidationError):
        normalize_export(
            "web_page",
            "Synthetic imported page body.",
            role="owned_article",
            source_url="https://example.com/page?token=private-import-token",
            observed_at=NOW,
        )


def test_imported_serp_library_never_persists_query_bearing_result_url():
    library = normalize_export(
        "serp",
        {"organic": [{"rank": 1, "link": "https://example.com/article?token=private-serp-token", "description": "Synthetic result."}]},
        role="discovery",
        source_url="https://www.google.com/search?q=synthetic",
        observed_at=NOW,
    )

    serialized = json.dumps(library)
    assert library["sources"] == []
    assert library["receipt"]["excluded_records"] == 1
    assert "private-serp-token" not in serialized
    assert ("?" + "to" + "ken=") not in serialized


def test_imported_serp_library_preserves_retained_rank_on_each_source():
    library = normalize_export(
        "serp",
        {"organic": [
            {"rank": 90, "link": "http://invalid.example/path", "description": "Invalid."},
            {"rank": 2, "global_rank": 12, "link": "https://example.com/one", "description": "One."},
            {"rank": 3, "global_rank": 13, "link": "https://example.com/one", "description": "Duplicate."},
            {"rank": 4, "global_rank": 14, "link": "https://example.org/two", "description": "Two."},
        ]},
        role="discovery",
        source_url="https://www.google.com/search?q=synthetic",
        observed_at=NOW,
        source_prefix="imported",
    )

    assert [source["metadata"] for source in library["sources"]] == [
        {"serp_rank": 2, "serp_global_rank": 12},
        {"serp_rank": 4, "serp_global_rank": 14},
    ]
    assert library["receipt"]["excluded_records"] == 2


def test_imported_serp_markup_description_is_excluded_without_losing_rank_alignment():
    library = normalize_export(
        "serp",
        {"organic": [
            {"rank": 1, "link": "https://example.com/markup", "description": "<script>hidden phrase</script>"},
            {"rank": 2, "global_rank": 8, "link": "https://example.org/valid", "description": "Visible text."},
        ]},
        role="discovery",
        source_url="https://www.google.com/search?q=synthetic",
        observed_at=NOW,
    )

    assert len(library["sources"]) == 1
    assert library["sources"][0]["url"] == "https://example.org/valid"
    assert library["sources"][0]["metadata"] == {"serp_rank": 2, "serp_global_rank": 8}
    assert library["receipt"]["excluded_records"] == 1


def test_collected_serp_unpaired_unicode_is_safely_excluded():
    value = manifest(serp_job())
    invalid_unicode_response = b'{"organic":[{"rank":1,"link":"https://example.com/bad","description":"\\ud800"}]}'
    library = collect(
        value,
        approval=approval(value, retained=5),
        api_key="fake",
        zones={"serp": "serp"},
        transport=lambda _: HttpResponse(200, {}, invalid_unicode_response),
        now=NOW,
    )

    serialized = json.dumps(library, ensure_ascii=False).encode("utf-8")
    assert library["sources"] == []
    assert library["receipt"]["status"] == "partial"
    assert library["receipt"]["excluded_records"] == 1
    assert b"\\ud800" not in serialized


def test_collected_serp_library_never_persists_query_bearing_result_url():
    value = manifest(serp_job())
    response = {"organic": [{"rank": 1, "link": "https://example.org/article?session=private-collected-token", "description": "Synthetic result."}]}
    library = collect(
        value,
        approval=approval(value, retained=5),
        api_key="fake",
        zones={"serp": "serp"},
        transport=lambda _: HttpResponse(200, {}, json.dumps(response).encode()),
        now=NOW,
    )

    serialized = json.dumps(library)
    assert library["sources"] == []
    assert library["receipt"]["retained_records"] == 0
    assert library["receipt"]["excluded_records"] == 1
    assert "private-collected-token" not in serialized
    assert "?session=" not in serialized


def test_paid_page_over_limit_is_excluded_and_stops_collection():
    value = manifest(web_job("large", "large"), web_job("later", "later", "https://www.python.org/about/"))

    def transport(_request):
        return HttpResponse(200, {}, b"x" * 50001)

    library = collect(value, approval=approval(value, retained=5), api_key="fake", zones={"web_unlocker": "web"}, transport=transport, now=NOW)

    assert library["receipt"]["requests_made"] == 1
    assert library["sources"] == []
    assert library["receipt"]["returned_records"] == 1
    assert library["receipt"]["excluded_records"] == 1
    assert library["receipt"]["jobs"][0]["error_code"] == "text_too_long"
    assert library["receipt"]["jobs"][1]["state"] == "not_attempted"


def test_monotonic_per_request_deadline_discards_late_success():
    value = manifest(web_job("page", "page"))

    def transport(request):
        time.sleep(1.5)
        return HttpResponse(200, {}, b"Late success must not be trusted")

    started = time.monotonic()
    library = collect(
        value,
        approval=approval(value, retained=5),
        api_key="fake",
        zones={"web_unlocker": "web"},
        transport=transport,
        now=NOW,
        monotonic=time.monotonic,
        per_request_timeout_seconds=1,
        overall_timeout_seconds=3,
    )

    assert time.monotonic() - started < 1.35
    assert library["receipt"]["requests_made"] == 1
    assert library["sources"] == []
    assert library["receipt"]["status"] == "completion_unknown"
    assert library["receipt"]["jobs"][0]["state"] == "completion_unknown"


def test_slow_custom_transport_is_killed_at_deadline():
    value = manifest(web_job("page", "page"))
    manager = multiprocessing.Manager()
    completed = manager.Value("i", 0)

    def slow_transport(_request):
        time.sleep(1.5)
        completed.value = 1
        return HttpResponse(200, {}, b"too late")

    started = time.monotonic()
    try:
        library = collect(
            value,
            approval=approval(value, retained=5),
            api_key="fake",
            zones={"web_unlocker": "web"},
            transport=slow_transport,
            now=NOW,
            per_request_timeout_seconds=1,
            overall_timeout_seconds=3,
        )
        elapsed = time.monotonic() - started
        time.sleep(0.7)
        assert elapsed < 1.35
        assert completed.value == 0
        assert library["receipt"]["status"] == "completion_unknown"
        assert library["sources"] == []
    finally:
        manager.shutdown()


def test_slow_drip_local_http_body_is_cancelled_at_deadline():
    class SlowDripHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", "5")
            self.end_headers()
            try:
                for char in b"12345":
                    self.wfile.write(bytes([char]))
                    self.wfile.flush()
                    time.sleep(0.2)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *_args):
            pass

    context = multiprocessing.get_context("fork")
    port_queue = context.Queue()

    def serve():
        server = ThreadingHTTPServer(("127.0.0.1", 0), SlowDripHandler)
        port_queue.put(server.server_port)
        server.serve_forever()

    server_process = context.Process(target=serve, daemon=True)
    server_process.start()
    port = port_queue.get(timeout=2)
    request = HttpRequest("GET", f"http://127.0.0.1:{port}/slow", {}, b"", 1)
    started = time.monotonic()
    try:
        with pytest.raises(TransportError):
            _bounded_transport(urllib_transport, request, deadline=started + 0.45, monotonic=time.monotonic)
        elapsed = time.monotonic() - started
        assert elapsed < 0.9
    finally:
        server_process.terminate()
        server_process.join(timeout=2)
        port_queue.close()


def test_overall_deadline_bounds_transport_timeout():
    value = manifest(web_job("page", "page"))
    manager = multiprocessing.Manager()
    observed = manager.list()

    def transport(request):
        observed.append(request.timeout_seconds)
        raise TimeoutError

    try:
        library = collect(
            value,
            approval=approval(value, retained=5),
            api_key="fake",
            zones={"web_unlocker": "web"},
            transport=transport,
            now=NOW,
            monotonic=lambda: 0.0,
            per_request_timeout_seconds=75,
            overall_timeout_seconds=30,
        )
        assert list(observed) == [30]
        assert library["receipt"]["status"] == "completion_unknown"
    finally:
        manager.shutdown()


def test_live_collection_fails_closed_from_multithreaded_caller():
    value = manifest(web_job("page", "page"))
    calls = []
    failures = []

    def run_collection():
        try:
            collect(value, approval=approval(value, retained=5), api_key="fake", zones={"web_unlocker": "web"}, transport=calls.append, now=NOW)
        except Exception as exc:
            failures.append(exc)

    worker = threading.Thread(target=run_collection)
    worker.start()
    worker.join(timeout=3)

    assert not worker.is_alive()
    assert calls == []
    assert len(failures) == 1
    assert isinstance(failures[0], ValidationError)


def test_live_collection_fails_closed_without_fork(monkeypatch):
    value = manifest(web_job("page", "page"))
    calls = []
    monkeypatch.setattr("content_gap_brief.brightdata.multiprocessing.get_context", lambda _method: (_ for _ in ()).throw(ValueError("unsupported")))

    with pytest.raises(ValidationError, match="fork-capable"):
        collect(value, approval=approval(value, retained=5), api_key="fake", zones={"web_unlocker": "web"}, transport=calls.append, now=NOW)

    assert calls == []


def test_subsecond_remaining_budget_does_not_round_timeout_up_or_request():
    value = manifest(web_job("page", "page"))
    clock_values = iter([0.0, 29.25])
    calls = []

    library = collect(
        value,
        approval=approval(value, retained=5),
        api_key="fake",
        zones={"web_unlocker": "web"},
        transport=calls.append,
        now=NOW,
        monotonic=lambda: next(clock_values),
        per_request_timeout_seconds=75,
        overall_timeout_seconds=30,
    )

    assert calls == []
    assert library["receipt"]["requests_made"] == 0
    assert library["receipt"]["status"] == "partial"
    assert library["receipt"]["jobs"][0]["state"] == "not_attempted"


def test_analysis_outputs_roll_back_if_second_commit_fails(tmp_path, monkeypatch):
    real_link = cli.os.link
    commits = 0

    def fail_second_commit(source, destination):
        nonlocal commits
        if Path(destination).name in {"report.json", "brief.md", "coverage.csv"}:
            commits += 1
            if commits == 2:
                raise OSError("simulated commit failure")
        return real_link(source, destination)

    monkeypatch.setattr(cli.os, "link", fail_second_commit)
    result = cli.main(["analyze", str(ROOT / "fixtures/demo.json"), "--out-dir", str(tmp_path)])

    assert result == 2
    assert not any((tmp_path / name).exists() for name in ("report.json", "brief.md", "coverage.csv"))
    assert not list(tmp_path.glob(".content-gap-brief-*"))


def test_analysis_no_clobber_survives_destination_race(tmp_path, monkeypatch):
    real_link = cli.os.link
    raced = False

    def race_link(source, destination):
        nonlocal raced
        if not raced:
            raced = True
            Path(destination).write_text("racer", encoding="utf-8")
        return real_link(source, destination)

    monkeypatch.setattr(cli.os, "link", race_link)
    result = cli.main(["analyze", str(ROOT / "fixtures/demo.json"), "--out-dir", str(tmp_path)])

    assert result == 2
    assert (tmp_path / "report.json").read_text() == "racer"
    assert not (tmp_path / "brief.md").exists()
    assert not (tmp_path / "coverage.csv").exists()


def test_analysis_overwrite_restores_original_set_on_commit_failure(tmp_path, monkeypatch):
    originals = {"report.json": "old report", "brief.md": "old brief", "coverage.csv": "old coverage"}
    for name, value in originals.items():
        (tmp_path / name).write_text(value, encoding="utf-8")
    real_replace = cli.os.replace
    commits = 0

    def fail_second_staged_commit(source, destination):
        nonlocal commits
        if Path(source).name.startswith(".content-gap-brief-stage-") and Path(destination).name in originals:
            commits += 1
            if commits == 2:
                raise OSError("simulated overwrite failure")
        return real_replace(source, destination)

    monkeypatch.setattr(cli.os, "replace", fail_second_staged_commit)
    result = cli.main(["analyze", str(ROOT / "fixtures/demo.json"), "--out-dir", str(tmp_path), "--overwrite"])

    assert result == 2
    assert {name: (tmp_path / name).read_text(encoding="utf-8") for name in originals} == originals
    assert not list(tmp_path.glob(".content-gap-brief-*"))


def test_markdown_scalar_fields_are_inert_single_lines():
    data = demo()
    data["topic"] = "Safe topic\n## Injected heading"
    data["criteria"][0]["label"] = "First line\n- injected item"
    markdown = render_markdown(analyze(data))

    assert "Safe topic \\#\\# Injected heading" in markdown
    assert "First line \\- injected item" in markdown
    assert "\n## Injected heading" not in markdown
    assert "\n- injected item" not in markdown


def test_distribution_name_is_brand_neutral():
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert metadata["project"]["name"] == "content-gap-brief"
