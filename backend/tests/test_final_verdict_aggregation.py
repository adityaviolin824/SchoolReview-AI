"""Tests for final aggregation payloads, validation, and saved outputs."""

import json
from pathlib import Path
from types import SimpleNamespace

from school_safety_validator.final_verdict_aggregation import (
    build_category_packets,
    build_global_rollup,
    run_final_aggregation,
    validate_final_report,
)
from school_safety_validator.inspection_data_models import CategoryFinalFeedback, FinalInspectionLLMReport
from school_safety_validator.inspection_runtime_settings import ValidatorSettings


def category_output(category: str = "classroom", status: str = "attention_required") -> dict:
    """Build one compact category output like the category runner saves."""

    return {
        "category": category,
        "image_count": 1,
        "category_status": status,
        "overall_officer_comment": "Overall comment.",
        "issue_counts": {"high": 0, "medium": 1, "low": 0},
        "human_review_required": True,
        "key_findings": [
            {
                "image_id": f"{category}_001.jpg",
                "issue_type": "damaged surface",
                "severity": "medium",
                "evidence": "A visible damaged surface is present.",
            }
        ],
        "documentation_gaps": [],
        "recommended_actions": ["Review the visible maintenance concern."],
    }


def final_report(overall_status: str = "acceptable_with_minor_issues") -> FinalInspectionLLMReport:
    """Build a valid final aggregation object for validation tests."""

    return FinalInspectionLLMReport(
        overall_status=overall_status,
        provisional=False,
        executive_summary="A visible maintenance concern was observed.",
        key_risks=["Damaged classroom surface."],
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
        human_review_notes=["Human review is required for the classroom."],
        limitations=[],
    )


class FakeResponses:
    def __init__(self, parsed):
        self.parsed = parsed

    def parse(self, **kwargs):
        return SimpleNamespace(output_parsed=self.parsed)


class FakeOpenAIClient:
    def __init__(self, parsed):
        self.responses = FakeResponses(parsed)


def test_global_rollup_uses_deterministic_status_floor_for_missing_categories() -> None:
    packets = build_category_packets({"classroom": category_output()})

    rollup = build_global_rollup(packets)

    assert rollup["processed_categories"] == ["classroom"]
    assert "ceiling" in rollup["not_inspected_categories"]
    assert rollup["deterministic_status_floor"] == "insufficient_evidence"
    assert rollup["human_review_required"] is True


def test_validate_final_report_upgrades_status_and_adds_not_inspected_limitation() -> None:
    packets = build_category_packets({"classroom": category_output()})
    rollup = build_global_rollup(packets)

    validated = validate_final_report(final_report(), rollup, packets)

    assert validated.overall_status == "insufficient_evidence"
    assert validated.provisional is True
    assert any("Not inspected categories:" in item for item in validated.limitations)


def test_run_final_aggregation_saves_raw_validated_and_payload_json(tmp_path: Path) -> None:
    category_output_root = tmp_path / "category_outputs"
    category_output_root.mkdir()
    (category_output_root / "classroom_image_assessments.json").write_text(
        """
        {
          "category": "classroom",
          "image_count": 1,
          "category_status": "attention_required",
          "overall_officer_comment": "Overall comment.",
          "issue_counts": {"high": 0, "medium": 1, "low": 0},
          "human_review_required": true,
          "key_findings": [],
          "documentation_gaps": [],
          "recommended_actions": ["Review the visible maintenance concern."]
        }
        """,
        encoding="utf-8",
    )
    settings = ValidatorSettings(output_root=tmp_path)

    result = run_final_aggregation(settings, openai_client=FakeOpenAIClient(final_report()))

    assert result["final_report"].overall_status == "insufficient_evidence"
    assert result["paths"]["final_aggregation_raw_output"].exists()
    assert result["paths"]["final_aggregation_output"].exists()
    assert result["paths"]["final_aggregation_payload"].exists()

    raw_output = json.loads(result["paths"]["final_aggregation_raw_output"].read_text(encoding="utf-8"))
    validated_output = json.loads(result["paths"]["final_aggregation_output"].read_text(encoding="utf-8"))

    assert raw_output["overall_status"] == "acceptable_with_minor_issues"
    assert raw_output["provisional"] is False
    assert validated_output["overall_status"] == "insufficient_evidence"
    assert validated_output["provisional"] is True
