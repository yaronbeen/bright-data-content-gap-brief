"""Command-line interface and atomic local file handling."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile

from . import __version__
from .brightdata import _manifest, collect, normalize_export, plan
from .core import MAX_BYTES, PROJECT, ValidationError, analyze, redact_url
from .export import render_csv, render_json, render_markdown


class StructuredArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, json.dumps({"code": "invalid_arguments", "message": "Invalid command-line arguments.", "requests_made": 0}, sort_keys=True) + "\n")


def _json(path: str):
    target = Path(path)
    if target.stat().st_size > MAX_BYTES:
        raise ValidationError("input file exceeds 2 MiB")
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError("unable to read valid UTF-8 JSON input") from None


def _source_library(value):
    fields = {"schema_version", "project", "transport_contract_version", "sources", "receipt"}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValidationError("source library envelope is invalid")
    if value["schema_version"] != "1.0" or value["project"] != PROJECT or value["transport_contract_version"] != "1.0":
        raise ValidationError("source library schema/project mismatch")
    if not isinstance(value["sources"], list) or any(not isinstance(source, dict) for source in value["sources"]) or not isinstance(value["receipt"], dict):
        raise ValidationError("source library sources/receipt are invalid")
    receipt = value["receipt"]
    receipt_fields = {"schema_version", "project", "manifest_sha256", "status", "requests_made", "returned_records", "retained_records", "excluded_records", "jobs", "warnings", "provider_cost_usd"}
    if set(receipt) != receipt_fields or receipt.get("schema_version") != "1.0" or receipt.get("project") != PROJECT:
        raise ValidationError("source library receipt envelope is invalid")
    if not isinstance(receipt.get("status"), str) or receipt["status"] not in {"complete", "partial", "failed", "pending", "completion_unknown"}:
        raise ValidationError("source library receipt status is invalid")
    if any(type(receipt.get(field)) is not int or receipt[field] < 0 for field in ("requests_made", "returned_records", "retained_records", "excluded_records")):
        raise ValidationError("source library receipt counts are invalid")
    manifest_hash = receipt.get("manifest_sha256")
    if manifest_hash is not None and (not isinstance(manifest_hash, str) or len(manifest_hash) != 64 or any(character not in "0123456789abcdef" for character in manifest_hash)):
        raise ValidationError("source library receipt manifest hash is invalid")
    if (not isinstance(receipt.get("jobs"), list) or any(not isinstance(job, dict) for job in receipt["jobs"])
            or not isinstance(receipt.get("warnings"), list) or any(not isinstance(warning, dict) for warning in receipt["warnings"])
            or receipt.get("provider_cost_usd") is not None):
        raise ValidationError("source library receipt details are invalid")
    if (receipt["requests_made"] > 12 or receipt["retained_records"] != len(value["sources"])
            or receipt["returned_records"] < receipt["retained_records"]):
        raise ValidationError("source library receipt counts are inconsistent")
    return value


def _atomic(path: Path, text: str, overwrite: bool):
    if path.exists() and not overwrite:
        raise ValidationError(f"output already exists: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".content-gap-brief-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        if overwrite:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)
            os.unlink(temporary)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _same_file(left: Path, right: Path) -> bool:
    try:
        left_stat, right_stat = left.stat(), right.stat()
    except OSError:
        return False
    return (left_stat.st_dev, left_stat.st_ino) == (right_stat.st_dev, right_stat.st_ino)


def _write_report_set(out: Path, rendered: dict[str, str], overwrite: bool) -> None:
    """Stage and commit all report files, rolling back partial commits."""
    out.mkdir(parents=True, exist_ok=True)
    lock_path = out / ".content-gap-brief-lock"
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValidationError("another report writer is active") from None
    os.close(lock_fd)
    staged: dict[Path, Path] = {}
    created: list[tuple[Path, Path]] = []
    backups: dict[Path, Path] = {}
    committed: list[Path] = []
    completed = False
    try:
        destinations = [out / name for name in rendered]
        if not overwrite and any(path.exists() for path in destinations):
            raise ValidationError("one or more report files already exist")
        for name, text in rendered.items():
            descriptor, temporary = tempfile.mkstemp(prefix=".content-gap-brief-stage-", dir=out)
            temporary_path = Path(temporary)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            staged[out / name] = temporary_path
        if not overwrite:
            for destination, temporary in staged.items():
                os.link(temporary, destination)
                created.append((destination, temporary))
        else:
            for destination in staged:
                if destination.exists():
                    descriptor, backup = tempfile.mkstemp(prefix=".content-gap-brief-backup-", dir=out)
                    os.close(descriptor)
                    os.unlink(backup)
                    backup_path = Path(backup)
                    os.replace(destination, backup_path)
                    backups[destination] = backup_path
            for destination, temporary in staged.items():
                os.replace(temporary, destination)
                committed.append(destination)
        directory_fd = os.open(out, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        completed = True
    except Exception:
        for destination, temporary in reversed(created):
            if _same_file(destination, temporary):
                try:
                    destination.unlink()
                except OSError:
                    pass
        for destination in reversed(committed):
            try:
                destination.unlink()
            except OSError:
                pass
        for destination, backup in backups.items():
            if backup.exists():
                try:
                    os.replace(backup, destination)
                except OSError:
                    pass
        raise
    finally:
        for temporary in staged.values():
            try:
                temporary.unlink()
            except OSError:
                pass
        if completed:
            for backup in backups.values():
                try:
                    backup.unlink()
                except OSError:
                    pass
        try:
            lock_path.unlink()
        except OSError:
            pass


def _public_plan(planned: dict) -> dict:
    public = json.loads(json.dumps(planned))
    public["targets"] = [redact_url(target) for target in public["targets"]]
    for job in public["jobs"]:
        if "url" in job:
            job["url"] = redact_url(job["url"])
        if "query" in job:
            job["query"] = "[REDACTED]"
    return public


def _error(code, message, requests=0):
    print(json.dumps({"code": code, "message": message, "requests_made": requests}, sort_keys=True), file=sys.stderr)


def parser():
    root = StructuredArgumentParser(prog=PROJECT, description="Build a cited, deterministic article brief from selected page snapshots.")
    root.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = root.add_subparsers(dest="command", required=True)
    a = commands.add_parser("analyze")
    a.add_argument("input")
    a.add_argument("--out-dir", required=True)
    a.add_argument("--sources")
    a.add_argument("--dry-run", action="store_true")
    a.add_argument("--overwrite", action="store_true")
    c = commands.add_parser("collect")
    c.add_argument("manifest")
    c.add_argument("--out", required=True)
    c.add_argument("--live", action="store_true")
    c.add_argument("--accept-charges", action="store_true")
    c.add_argument("--approval")
    c.add_argument("--dry-run", action="store_true")
    c.add_argument("--overwrite", action="store_true")
    i = commands.add_parser("import-provider")
    i.add_argument("file")
    i.add_argument("--kind", required=True, choices=("web_page", "serp"))
    i.add_argument("--role", required=True)
    i.add_argument("--source-url", required=True)
    i.add_argument("--observed-at", required=True)
    i.add_argument("--source-prefix", default="import")
    i.add_argument("--out", required=True)
    i.add_argument("--overwrite", action="store_true")
    r = commands.add_parser("resume")
    r.add_argument("receipt")
    r.add_argument("--out", required=True)
    r.add_argument("--live", action="store_true")
    r.add_argument("--accept-charges", action="store_true")
    r.add_argument("--approval", required=True)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    requests_made = 0
    try:
        if args.command == "analyze":
            payload = _json(args.input)
            if args.sources:
                library = _source_library(_json(args.sources))
                existing = {x.get("id") for x in payload.get("sources", [])}
                incoming = {x.get("id") for x in library["sources"]}
                if existing & incoming:
                    raise ValidationError("source library contains duplicate source IDs")
                payload["sources"] = payload.get("sources", []) + library["sources"]
            report = analyze(payload)
            if args.dry_run:
                print(json.dumps({"input_questions": len(payload["questions"]), "input_sources": len(payload["sources"]), "requests_made": 0}, sort_keys=True))
                return 0
            out = Path(args.out_dir)
            _write_report_set(out, {"report.json": render_json(report), "brief.md": render_markdown(report), "coverage.csv": render_csv(report)}, args.overwrite)
            print(json.dumps({"decision": report["decision"], "status": report["status"], "out_dir": str(out), "requests_made": 0}, sort_keys=True))
            return 0
        if args.command == "collect":
            manifest = _json(args.manifest)
            if args.live:
                _manifest(manifest, live=True)
            planned = plan(manifest)
            if args.dry_run:
                print(json.dumps(_public_plan(planned), sort_keys=True))
                return 0
            if not args.live or not args.accept_charges or not args.approval:
                raise ValidationError("collection requires --live, --accept-charges, and --approval; otherwise use --dry-run")
            if Path(args.out).exists() and not args.overwrite:
                raise ValidationError("collection output already exists")
            now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            library = collect(manifest, approval=_json(args.approval), api_key=os.environ.get("BRIGHT_DATA_API_KEY", ""), zones={"web_unlocker": os.environ.get("BRIGHT_DATA_WEB_UNLOCKER_ZONE", ""), "serp": os.environ.get("BRIGHT_DATA_SERP_ZONE", "")}, now=now)
            requests_made = library["receipt"]["requests_made"]
            _atomic(Path(args.out), json.dumps(library, ensure_ascii=False, indent=2, sort_keys=True) + "\n", args.overwrite)
            print(json.dumps({"status": library["receipt"]["status"], "requests_made": library["receipt"]["requests_made"]}, sort_keys=True))
            return 4 if library["receipt"]["status"] in {"partial", "pending", "completion_unknown"} else (3 if library["receipt"]["status"] == "failed" else 0)
        if args.command == "import-provider":
            if Path(args.out).exists() and not args.overwrite:
                raise ValidationError("import output already exists")
            path = Path(args.file)
            if path.stat().st_size > MAX_BYTES:
                raise ValidationError("provider export exceeds 2 MiB")
            raw = path.read_text(encoding="utf-8")
            records = raw if args.kind == "web_page" else json.loads(raw)
            library = normalize_export(args.kind, records, role=args.role, source_url=args.source_url, observed_at=args.observed_at, source_prefix=args.source_prefix)
            _atomic(Path(args.out), json.dumps(library, ensure_ascii=False, indent=2, sort_keys=True) + "\n", args.overwrite)
            print(json.dumps({"status": library["receipt"]["status"], "requests_made": 0}, sort_keys=True))
            return 4 if library["receipt"]["status"] == "partial" else 0
        raise ValidationError("resume is unsupported because this project has no scraper jobs")
    except (ValidationError, OSError, UnicodeError, json.JSONDecodeError):
        if requests_made:
            _error("filesystem_error", "Collection ran but the local receipt could not be written; inspect the destination before retrying.", requests_made)
        else:
            _error("invalid_input", "Input, flags, or filesystem state is invalid; no secret or provider body was retained.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
