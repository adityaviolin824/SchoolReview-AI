"""Smoke tests for deterministic report artifact rendering."""

from pathlib import Path

from school_safety_validator import final_report_artifact_rendering
from school_safety_validator.final_report_artifact_rendering import save_final_report_outputs
from school_safety_validator.final_report_content_generation import REPORT_DISCLAIMER
from school_safety_validator.inspection_data_models import FinalReportCategorySection, FinalReportContent
from school_safety_validator.inspection_runtime_settings import ValidatorSettings


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


def metadata(tmp_path: Path) -> dict:
    return {
        "generated_at_utc": "2026-06-30T00:00:00+00:00",
        "final_aggregation_json_path": str(tmp_path / "final_aggregation_output.json"),
        "report_content_json_path": str(tmp_path / "school_safety_final_report_content.json"),
        "cover_image_path": "",
        "category_output_sources": [
            {
                "category": "classroom",
                "path": str(tmp_path / "classroom_image_assessments.json"),
                "last_modified_utc": "2026-06-30T00:00:00+00:00",
            }
        ],
        "models": {
            "primary_vlm_model": "gemini-3.1-flash-lite",
            "backup_vlm_model": "gpt-4.1-mini",
            "escalation_review_model": "gpt-4.1-mini",
            "final_aggregation_model": "gpt-4.1-mini",
            "final_report_model": "gpt-4.1-mini",
        },
        "processed_categories": ["classroom"],
        "not_inspected_categories": ["ceiling"],
        "total_images": 1,
        "deterministic_status_floor": "insufficient_evidence",
    }


def test_save_final_report_outputs_writes_and_validates_all_artifacts(monkeypatch, tmp_path: Path) -> None:
    def fake_render_report_pdf(html_text, pdf_path, content, report_metadata, packets):
        final_report_artifact_rendering.render_report_pdf_with_reportlab(
            content,
            report_metadata,
            packets,
            pdf_path,
        )
        return "reportlab"

    monkeypatch.setattr(final_report_artifact_rendering, "render_report_pdf", fake_render_report_pdf)
    settings = ValidatorSettings(output_root=tmp_path)

    paths = save_final_report_outputs(
        report_content(),
        {"payload": "value"},
        metadata(tmp_path),
        category_packets(),
        {
            "not_inspected_categories": ["ceiling"],
            "processed_categories": ["classroom"],
            "total_images": 1,
            "deterministic_status_floor": "insufficient_evidence",
        },
        settings,
    )

    assert paths["markdown_report"].exists()
    assert paths["html_report"].exists()
    assert paths["pdf_report"].exists()
    assert paths["report_content_json"].exists()
    assert paths["report_generation_payload"].exists()
