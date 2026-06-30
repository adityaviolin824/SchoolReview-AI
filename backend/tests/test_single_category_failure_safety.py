"""Regression tests for preserving failed image jobs during category runs."""

import asyncio
from pathlib import Path

from school_safety_validator.inspection_data_models import (
    ImageAssessment,
    OfficerCommentAssessment,
    RecommendedAction,
    RiskAssessment,
    VisualFinding,
)
from school_safety_validator.inspection_runtime_settings import ValidatorSettings
from school_safety_validator.single_category_inspection_runner import run_category_inspection


def fake_assessment(image_name: str) -> ImageAssessment:
    """Build a valid completed assessment for fake graph success cases."""

    return ImageAssessment(
        image_name=image_name,
        category="classroom",
        visual_findings=[
            VisualFinding(
                issue_type="no visible issue",
                visibility="not_visible",
                severity="none",
                evidence="No visible issue is asserted in this fake response.",
                confidence=0.9,
            )
        ],
        risk_assessment=RiskAssessment(
            severity="none",
            requires_human_review=False,
            reason="Fake completed assessment.",
        ),
        officer_comment_assessment=OfficerCommentAssessment(
            text="",
            status="missing",
            agreement="no_comment",
            reason="No officer comment is used in this fake response.",
            documentation_gap=False,
        ),
        recommended_action=RecommendedAction(
            action_type="none",
            action_text="No action in fake response.",
        ),
        uncertainties=[],
    )


class FakeImageAssessmentGraph:
    """Fake graph that succeeds for one image and raises for another."""

    async def ainvoke(self, image_state: dict, config: dict) -> dict:
        image_name = image_state["raw_image_path"].name
        if image_name == "broken.jpg":
            raise ValueError("Unable to read image: broken.jpg")

        return {
            **image_state,
            "status": "completed",
            "final_assessment": fake_assessment(image_name),
            "final_assessment_source": "primary_model",
            "backup_used": False,
            "review_used": False,
            "human_review_required": False,
            "human_review_status": "not_required",
            "human_review_item": None,
        }


def create_category_dataset(input_root: Path) -> None:
    """Create a tiny category folder with two discovered image files."""

    images_path = input_root / "classroom" / "images"
    comments_path = input_root / "classroom" / "comments"
    images_path.mkdir(parents=True)
    comments_path.mkdir(parents=True)
    (images_path / "broken.jpg").write_bytes(b"not used by fake graph")
    (images_path / "working.jpg").write_bytes(b"not used by fake graph")
    (comments_path / "overall_comments.txt").write_text("Overall comment.", encoding="utf-8")


def test_category_run_preserves_failed_image_when_graph_raises(monkeypatch, tmp_path: Path) -> None:
    create_category_dataset(tmp_path / "school")

    monkeypatch.setattr(
        "school_safety_validator.single_category_inspection_runner.build_image_assessment_graph",
        lambda clients, settings: FakeImageAssessmentGraph(),
    )
    settings = ValidatorSettings(
        input_root=tmp_path / "school",
        output_root=tmp_path / "outputs",
        max_concurrent_requests=1,
    )

    category_state = asyncio.run(run_category_inspection("classroom", settings, clients=object()))

    assert len(category_state["image_results"]) == 2
    failed_result = next(result for result in category_state["image_results"] if result["image_id"] == "broken.jpg")
    completed_result = next(result for result in category_state["image_results"] if result["image_id"] == "working.jpg")

    assert failed_result["status"] == "failed"
    assert failed_result["error"]["error_type"] == "ValueError"
    assert "Unable to read image" in failed_result["error"]["error_message"]
    assert failed_result["human_review"]["required"] is True
    assert completed_result["status"] == "completed"
    assert category_state["category_status"] == "insufficient_evidence"
    assert len(category_state["human_review_queue"]) == 1
    assert (tmp_path / "outputs" / "model_outputs" / "classroom" / "broken.json").exists()
    assert (tmp_path / "outputs" / "model_outputs" / "classroom" / "working.json").exists()
