"""Contract tests for Content Gap Brief candidate selection."""

import pytest

from content_gap_brief.core import analyze


def citation(source_id, block_id, quote):
    return {"source_id": source_id, "block_id": block_id, "quote": quote}


def source(source_id, role, text, status="collected", title=None):
    return {
        "id": source_id,
        "kind": "page",
        "role": role,
        "url": f"https://example.com/{source_id}",
        "title": title or source_id,
        "text": text,
        "status": status,
        "observed_at": "2026-10-04T10:00:00Z",
        "published_at": None,
        "provider_date": None,
        "record_id": None,
        "record_id_origin": None,
        "provenance": "synthetic_fixture",
    }


def question(question_id, text, related):
    return {
        "id": question_id,
        "text": text,
        "origin": "editor_inferred",
        "question_ref": None,
        "related_phrases": [related],
        "answer_phrases": [f"Answer for {question_id}"],
    }


def payload(questions, competing_text, criteria_by_question):
    criteria = [
        {
            "id": f"criterion-{question_id}",
            "question_id": question_id,
            "label": f"Check {question_id}",
            "acceptance_check": f"Verify {question_id}",
            "required": True,
        }
        for question_id in criteria_by_question
    ]
    return {
        "topic": "Synthetic import workflow",
        "reader_task": "Choose a safe import workflow.",
        "questions": questions,
        "criteria": criteria,
        "worked_examples": [
            {
                "label": "Synthetic example",
                "scenario": "A fictional import case.",
                "has_criteria": [],
                "provenance": "synthetic_operator_example",
            }
        ],
        "coverage_overrides": [],
        "sources": [
            source("owned", "owned_article", "Owned page has no relevant passage."),
            source("competitor", "competing_article", competing_text),
        ],
    }


def qid_rows(report):
    return {row["question_id"]: row for row in report["coverage"]}


@pytest.mark.parametrize("match_location", ["title", "heading"])
def test_competing_title_or_heading_without_body_passage_is_not_eligible(
    match_location,
):
    data = payload(
        [question("q1", "How do I recover an import?", "retry steps")],
        (
            "## How do I recover an import?\n\nAn unrelated article body."
            if match_location == "heading"
            else "An unrelated article body."
        ),
        {"q1"},
    )
    if match_location == "title":
        data["sources"][1]["title"] = "A guide to retry steps"

    report = analyze(data)

    assert report["decision"] == "coverage_review_required"
    assert report["status"] == "needs_review"
    assert report["brief"] is None
    assert "q1" in report["review_question_ids"]
    assert report["coverage"]


def test_coverage_rows_report_body_match_and_availability_states():
    data = payload(
        [question("q1", "How do I inspect an error?", "import error log")],
        "Inspect the import error log.",
        {"q1"},
    )
    data["questions"][0]["answer_phrases"] = ["Inspect the import error log."]
    data["sources"] = [
        source("owned-answer", "owned_article", "Inspect the import error log."),
        source("owned-related", "owned_article", "Open the import error log."),
        source("owned-none", "owned_article", "An unrelated body passage."),
        source("owned-missing", "owned_article", "", status="unavailable"),
        source(
            "competitor",
            "competing_article",
            "Inspect the import error log.",
        ),
    ]

    report = analyze(data)
    states = {row["source_id"]: row["coverage_state"] for row in report["coverage"]}

    assert states == {
        "owned-answer": "answer_phrase_found",
        "owned-related": "related_passage_only",
        "owned-none": "no_related_passage_found_in_selected_text",
        "owned-missing": "unavailable",
        "competitor": "answer_phrase_found",
    }


def test_first_eligible_question_in_input_order_wins_over_review_question():
    report = analyze(
        payload(
            [
                question("q-review", "How do I retry?", "retry steps"),
                question("q-first", "How do I validate?", "validation steps"),
                question("q-second", "How do I recover?", "recovery steps"),
            ],
            "## A guide\n\nFollow the validation steps, then follow the recovery steps.",
            {"q-first", "q-second"},
        )
    )

    assert report["decision"] == "scoped_brief"
    assert report["brief"]["question_id"] == "q-first"
    assert "q-review" in report["review_question_ids"]
    assert "q-second" in qid_rows(report)


@pytest.mark.parametrize(
    "competing_text, criteria_by_question",
    [
        ("## Recovery\n\nUnrelated body text.", {"q1"}),
        ("## Recovery\n\nFollow the recovery steps.", set()),
    ],
)
def test_no_eligible_candidate_retains_coverage_and_requires_review(
    competing_text, criteria_by_question
):
    report = analyze(
        payload(
            [question("q1", "How do I recover?", "recovery steps")],
            competing_text,
            criteria_by_question,
        )
    )

    assert report["decision"] == "coverage_review_required"
    assert report["status"] == "needs_review"
    assert report["brief"] is None
    assert len(report["coverage"]) == 2
    assert {row["question_id"] for row in report["coverage"]} == {"q1"}
    assert {row["source_id"] for row in report["coverage"]} == {
        "owned",
        "competitor",
    }
    assert "q1" in report["review_question_ids"]
