"""Stable Markdown and CSV renderers."""

from __future__ import annotations

import csv
import io
import json
import re


def _md(value) -> str:
    text = "" if value is None else " ".join(str(value).split())
    text = re.sub(r"<", "&lt;", text)
    for character in ("\\", "`", "*", "_", "{", "}", "[", "]", "(", ")", "#", "+", "-", "!", "|"):
        text = text.replace(character, "\\" + character)
    return text


def render_markdown(report: dict) -> str:
    lines = ["# Content Gap Brief", ""]
    if any(x.get("provenance") == "synthetic_fixture" for x in report["source_index"]):
        lines += ["> **Synthetic demonstration:** This report contains invented fixture data, not market evidence.", ""]
    lines += [f"**Decision:** `{report['decision']}`", f"**Status:** `{report['status']}`", f"**Method:** `{report['analysis_method']}`", "", "## Bounded scope", "", f"Topic: {_md(report['scope']['topic'])}", f"Reader task: {_md(report['scope']['reader_task'])}", f"Selected sources: {', '.join(f'`{x}`' for x in report['scope']['source_ids'])}", ""]
    if report["brief"]:
        brief = report["brief"]
        lines += [f"## {_md(brief['title'])}", "", f"Reader decision: {_md(brief['reader_task'])}", "", "### Requirements checklist", ""]
        for row in brief["checklist_rows"]:
            marker = "required" if row["required"] else "optional"
            lines.append(f"- **{_md(row['label'])}** ({marker}): {_md(row['acceptance_check'])}")
        lines += ["", "### Worked examples", ""]
        for row in brief["worked_example_rows"]:
            missing = ", ".join(row["missing_required_criteria_ids"]) or "none"
            lines += [f"- **{_md(row['label'])}:** {_md(row['scenario'])} Missing required checks: {_md(missing)}."]
        lines += ["", "### Limits and expert checks", ""] + [f"- {_md(x)}" for x in brief["expert_checks"]]
    elif report["decision"] == "already_covered_by_declared_checks":
        lines += ["## No assignment proposed", "", "Every declared question has an owned-page answer phrase or operator-confirmed coverage. Review the cited rows before deciding no article is needed."]
    else:
        lines += ["## Coverage review required", "", "No eligible assignment was forced. Add a criterion, inspect related owned passages, resolve unavailable pages, or provide a competing-article body passage for: " + ", ".join(f"`{x}`" for x in report["review_question_ids"])]
    lines += ["", "## Coverage evidence", ""]
    for row in report["coverage"]:
        excerpt = f' Quote: "{_md(row["excerpt"])}"' if row["excerpt"] else ""
        lines.append(f"- `{row['question_id']}` / `{row['source_id']}`: `{row['coverage_state']}`.{excerpt}")
    observed_questions = {}
    for row in report["coverage"]:
        if row.get("question_ref"):
            observed_questions.setdefault(row["question_id"], (row["question"], row["question_ref"]))
    if observed_questions:
        lines += ["", "## Question provenance", ""]
        for question_id, (question, ref) in observed_questions.items():
            lines.append(f"- `{question_id}` {_md(question)} Observed question source: `{ref['source_id']}/{ref['block_id']}` \"{_md(ref['quote'])}\"")
    lines += ["", "## Evidence appendix", ""]
    index = {x["id"]: x for x in report["source_index"]}
    seen = set()
    refs = [ref for row in report["coverage"] for ref in row["evidence"]]
    refs += [reference for _, reference in observed_questions.values()]
    if report["brief"]:
        refs += report["brief"]["angle_basis_refs"]
    for ref in refs:
        key = (ref["source_id"], ref["block_id"], ref["quote"])
        if key in seen:
            continue
        seen.add(key)
        src = index[ref["source_id"]]
        record = f"; record `{_md(src['record_id'])}`" if src["record_id"] else ""
        lines.append(f"- `{ref['source_id']}/{ref['block_id']}`: \"{_md(ref['quote'])}\" ({_md(src['url'])}{record}; observed {src['observed_at']}; SHA-256 `{src['content_sha256']}`)")
    lines += ["", "## Limitations", "", "Coverage means literal declared-phrase checks or a labeled human override within selected snapshots. It is not semantic SEO analysis, search demand, internet-wide coverage, or an outcome forecast.", ""]
    return "\n".join(lines)


def _safe_csv(value) -> str:
    text = "" if value is None else str(value)
    first = next((character for character in text if ord(character) > 32), "")
    if first in ("=", "+", "-", "@"):
        return "'" + text
    return text


def render_csv(report: dict) -> str:
    output = io.StringIO(newline="")
    fields = ["question_id", "question", "question_origin", "source_id", "source_role", "coverage_state", "coverage_method", "matched_answer_phrase", "excerpt", "source_url", "observed_at"]
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in report["coverage"]:
        writer.writerow({key: _safe_csv(row.get(key, "")) for key in fields})
    return output.getvalue()


def render_json(report: dict) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
