"""Tests for deterministic assessment rules extracted from the notebook."""

from school_safety_validator.deterministic_assessment_rules import (
    apply_rule_based_risk_updates,
    clean_uncertainties,
    should_use_review_model,
)
from school_safety_validator.inspection_data_models import (
    ImageAssessment,
    OfficerCommentAssessment,
    RecommendedAction,
    RiskAssessment,
    VisualFinding,
)


def make_assessment(
    finding_severity: str = "medium",
    risk_severity: str = "none",
    action_type: str = "none",
    confidence: float = 0.9,
    uncertainty: str | None = None,
) -> ImageAssessment:
    return ImageAssessment(
        image_name="classroom_001.jpg",
        category="classroom",
        visual_findings=[
            VisualFinding(
                issue_type="damaged furniture",
                visibility="visible",
                severity=finding_severity,
                evidence="Visible damaged desk edge.",
                confidence=confidence,
            )
        ],
        risk_assessment=RiskAssessment(
            severity=risk_severity,
            requires_human_review=False,
            reason="Initial model risk.",
        ),
        officer_comment_assessment=OfficerCommentAssessment(
            text="desk broken",
            status="present",
            agreement="supports_visual_evidence",
            reason="Comment aligns with visible evidence.",
            documentation_gap=False,
        ),
        recommended_action=RecommendedAction(action_type=action_type, action_text=""),
        uncertainties=[uncertainty] if uncertainty else [],
    )


def test_clean_uncertainties_removes_placeholder_values() -> None:
    assert clean_uncertainties(["none", "N/A", "", "needs closer review"]) == ["needs closer review"]


def test_rule_based_updates_raise_risk_to_visible_finding_severity() -> None:
    assessment = make_assessment(finding_severity="high", risk_severity="low", action_type="monitor")

    updated = apply_rule_based_risk_updates(assessment)

    assert updated.risk_assessment.severity == "high"
    assert updated.recommended_action.action_type == "urgent_attention"


def test_rule_based_updates_queue_human_review_for_uncertainty() -> None:
    assessment = make_assessment(uncertainty="image is partially obstructed")

    updated = apply_rule_based_risk_updates(assessment)

    assert updated.risk_assessment.requires_human_review is True
    assert should_use_review_model(updated) is True


def test_low_confidence_finding_uses_review_model() -> None:
    assessment = make_assessment(confidence=0.4)

    assert should_use_review_model(assessment, confidence_threshold=0.6) is True
