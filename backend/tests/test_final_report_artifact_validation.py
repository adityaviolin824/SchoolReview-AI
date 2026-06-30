"""Tests for final rendered report artifact validation."""

import json
from pathlib import Path

import pytest

from school_safety_validator.final_report_artifact_validation import validate_rendered_report
from school_safety_validator.final_report_content_generation import REPORT_DISCLAIMER
from school_safety_validator.inspection_data_models import FinalReportCategorySection, FinalReportContent


def report_content() -> FinalReportContent:
    return FinalReportContent(
        title="School Safety Visual Inspection Summary",
        overall_status="insufficient_evidence",
        provisional=True,
        executive_summary=["A classroom issue was observed."],
        scope_and_inputs=["Processed category: classroom.", "Not inspected category: ceiling."],
        category_sections=[
            FinalReportCategorySection(
                category="classroom",
                status="attention_required",
                priority="medium",
                summary="The classroom has a visible maintenance concern.",
                evidence_refs=["classroom_001.jpg"],
                recommended_actions=["Review the visible maintenance concern."],
            )
        ],
        immediate_actions=[],
        maintenance_actions=["Review the visible maintenance concern."],
        documentation_followups=[],
        human_review_notes=["Human review is required."],
        limitations=["Not inspected categories: ceiling"],
        disclaimer=REPORT_DISCLAIMER,
    )


def test_validate_rendered_report_rejects_missing_artifact(tmp_path: Path) -> None:
    content = report_content()
    json_path = tmp_path / "content.json"
    json_path.write_text(json.dumps(content.model_dump(mode="json")), encoding="utf-8")
    paths = {
        "markdown_report": tmp_path / "missing.md",
        "html_report": tmp_path / "missing.html",
        "pdf_report": tmp_path / "missing.pdf",
        "report_content_json": json_path,
        "report_generation_payload": tmp_path / "missing-payload.json",
    }

    with pytest.raises(ValueError, match="missing or empty"):
        validate_rendered_report(
            content,
            paths,
            [{"category": "classroom"}],
            {"not_inspected_categories": ["ceiling"]},
        )
