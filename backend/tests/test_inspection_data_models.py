"""Tests for the shared schema layer extracted from the notebook.

These tests intentionally stay small and deterministic. They verify that the
main notebook-shaped image assessment and final report objects can be created,
and that invalid controlled-label values fail validation before downstream code
uses model output.
"""

import pytest
from pydantic import ValidationError

from school_safety_validator.inspection_data_models import (
    CategoryFinalFeedback,
    FinalInspectionLLMReport,
    ImageAssessment,
    OfficerCommentAssessment,
    RecommendedAction,
    RiskAssessment,
    VisualFinding,
)


def test_image_assessment_accepts_notebook_schema_shape() -> None:
    assessment = ImageAssessment(
        image_name="classroom_001.jpg",
        category="classroom",
        visual_findings=[
            VisualFinding(
                issue_type="damaged furniture",
                visibility="visible",
                severity="medium",
                evidence="A damaged desk edge is visible near the seating area.",
                confidence=0.82,
            )
        ],
        risk_assessment=RiskAssessment(
            severity="medium",
            requires_human_review=False,
            reason="Visible maintenance issue observed.",
        ),
        officer_comment_assessment=OfficerCommentAssessment(
            text="desk broken",
            status="present",
            agreement="supports_visual_evidence",
            reason="Comment aligns with visible desk damage.",
            documentation_gap=False,
        ),
        recommended_action=RecommendedAction(
            action_type="maintenance_review",
            action_text="Review and repair the damaged desk.",
        ),
        uncertainties=[],
    )

    dumped = assessment.model_dump()

    assert dumped["image_name"] == "classroom_001.jpg"
    assert dumped["visual_findings"][0]["severity"] == "medium"
    assert dumped["recommended_action"]["action_type"] == "maintenance_review"


def test_schema_rejects_invalid_literal_values() -> None:
    with pytest.raises(ValidationError):
        VisualFinding(
            issue_type="damaged furniture",
            visibility="visible",
            severity="critical",
            evidence="A damaged desk edge is visible.",
            confidence=0.82,
        )


def test_final_report_schema_accepts_validated_category_feedback() -> None:
    report = FinalInspectionLLMReport(
        overall_status="maintenance_attention_required",
        provisional=True,
        executive_summary="Visible medium-severity maintenance issues were observed.",
        key_risks=["Damaged furniture in classroom."],
        category_feedback=[
            CategoryFinalFeedback(
                category="classroom",
                status="attention_required",
                priority="medium",
                short_summary="Visible furniture damage requires maintenance review.",
                main_concerns=["Damaged desk edge."],
                recommended_next_steps=["Review and repair the damaged desk."],
                evidence_refs=["classroom_001.jpg"],
            )
        ],
        immediate_actions=[],
        maintenance_actions=["Review and repair the damaged desk."],
        documentation_followups=[],
        human_review_notes=[],
        limitations=[],
    )

    assert report.category_feedback[0].category == "classroom"
    assert report.overall_status == "maintenance_attention_required"
