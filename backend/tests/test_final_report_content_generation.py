"""Tests for report-content payload and validation logic."""

import pytest

from school_safety_validator.final_report_content_generation import (
    REPORT_DISCLAIMER,
    build_report_generation_payload,
    validate_final_report_content,
)
from school_safety_validator.inspection_data_models import (
    CategoryFinalFeedback,
    FinalInspectionLLMReport,
    FinalReportCategorySection,
    FinalReportContent,
)


def aggregation_report() -> FinalInspectionLLMReport:
    """Build a validated final aggregation response."""

    return FinalInspectionLLMReport(
        overall_status="insufficient_evidence",
        provisional=True,
        executive_summary="A classroom issue was observed and some categories were not inspected.",
        key_risks=["Classroom maintenance concern."],
        category_feedback=[
            CategoryFinalFeedback(
                category="classroom",
                status="attention_required",
                priority="medium",
                short_summary="The classroom has a visible maintenance concern.",
                main_concerns=["Damaged surface."],
                recommended_next_steps=["Review the visible maintenance concern."],
                evidence_refs=["classroom_001.jpg"],
            )
        ],
        immediate_actions=[],
        maintenance_actions=["Review the visible maintenance concern."],
        documentation_followups=[],
        human_review_notes=["Human review is required."],
        limitations=["Not inspected categories: ceiling"],
    )


def report_content(
    overall_status: str = "insufficient_evidence",
    disclaimer: str = REPORT_DISCLAIMER,
) -> FinalReportContent:
    """Build report-ready content for validation tests."""

    return FinalReportContent(
        title="School Safety Visual Inspection Summary",
        overall_status=overall_status,
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
        disclaimer=disclaimer,
    )


def category_packets() -> list[dict]:
    return [
        {
            "category": "classroom",
            "image_count": 1,
            "category_status": "attention_required",
            "issue_counts": {"high": 0, "medium": 1, "low": 0},
            "human_review_required": True,
            "key_findings": [],
            "documentation_gaps": [],
            "recommended_actions": ["Review the visible maintenance concern."],
        }
    ]


def global_rollup() -> dict:
    return {
        "processed_categories": ["classroom"],
        "not_inspected_categories": ["ceiling"],
        "total_images": 1,
        "deterministic_status_floor": "insufficient_evidence",
    }


def test_report_generation_payload_preserves_validated_verdict_and_rules() -> None:
    payload = build_report_generation_payload(aggregation_report(), category_packets(), global_rollup(), [])

    assert payload["validated_final_verdict"]["overall_status"] == "insufficient_evidence"
    assert payload["categories"][0]["category"] == "classroom"
    assert REPORT_DISCLAIMER in payload["rules"][-1]


def test_validate_final_report_content_accepts_matching_content() -> None:
    validated = validate_final_report_content(
        report_content(),
        aggregation_report(),
        category_packets(),
        global_rollup(),
    )

    assert validated.disclaimer == REPORT_DISCLAIMER


def test_validate_final_report_content_repairs_missing_not_inspected_limitation() -> None:
    rollup = global_rollup()
    rollup["not_inspected_categories"] = ["ceiling", "fire_extinguisher"]

    validated = validate_final_report_content(
        report_content(),
        aggregation_report(),
        category_packets(),
        rollup,
    )

    assert validated.limitations[-1] == "Not inspected categories: fire_extinguisher"


def test_validate_final_report_content_rejects_status_changes() -> None:
    with pytest.raises(ValueError, match="overall_status"):
        validate_final_report_content(
            report_content(overall_status="acceptable_with_minor_issues"),
            aggregation_report(),
            category_packets(),
            global_rollup(),
        )


def test_validate_final_report_content_rejects_changed_disclaimer() -> None:
    with pytest.raises(ValueError, match="disclaimer"):
        validate_final_report_content(
            report_content(disclaimer="Different disclaimer."),
            aggregation_report(),
            category_packets(),
            global_rollup(),
        )
