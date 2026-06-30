"""Tests for compact one-category summary creation."""

from school_safety_validator.single_category_inspection_runner import classify_category, summarize_category


def completed_result(
    image_id: str,
    severity: str,
    requires_human_review: bool = False,
) -> dict:
    return {
        "image_id": image_id,
        "status": "completed",
        "final_assessment": {
            "risk_assessment": {
                "severity": severity,
                "requires_human_review": requires_human_review,
            },
            "officer_comment_assessment": {
                "documentation_gap": False,
                "reason": "Comment aligns with visible evidence.",
            },
            "recommended_action": {
                "action_text": "Review the visible maintenance concern.",
            },
            "visual_findings": [
                {
                    "visibility": "visible",
                    "severity": severity,
                    "issue_type": "damaged furniture",
                    "evidence": "Visible damaged desk edge.",
                }
            ],
        },
    }


def test_classify_category_attention_required_for_medium_issue() -> None:
    assert classify_category([completed_result("classroom_001.jpg", "medium")]) == "attention_required"


def test_classify_category_insufficient_when_failed_result_is_present() -> None:
    results = [
        completed_result("classroom_001.jpg", "low"),
        {
            "image_id": "classroom_002.jpg",
            "status": "failed",
            "error": {"error_message": "model failed"},
        },
    ]

    assert classify_category(results) == "insufficient_evidence"


def test_summarize_category_keeps_compact_findings_and_actions() -> None:
    summary = summarize_category(
        "classroom",
        [completed_result("classroom_001.jpg", "medium")],
        "Overall classroom comment.",
    )

    assert summary["category"] == "classroom"
    assert summary["image_count"] == 1
    assert summary["issue_counts"] == {"high": 0, "medium": 1, "low": 0}
    assert summary["category_status"] == "attention_required"
    assert summary["key_findings"][0]["image_id"] == "classroom_001.jpg"
    assert summary["recommended_actions"] == ["Review the visible maintenance concern."]
