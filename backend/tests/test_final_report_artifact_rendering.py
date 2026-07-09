"""Smoke tests for deterministic report artifact rendering."""

import sys
from pathlib import Path
from types import SimpleNamespace

from school_safety_validator import final_report_artifact_rendering
from school_safety_validator.final_report_artifact_rendering import (
    REPORTLAB_PRIORITY_TABLE_WIDTHS_MM,
    REPORTLAB_USABLE_WIDTH_MM,
    reportlab_col_widths,
    reportlab_table_rows,
    render_report_pdf,
    render_report_html,
    render_report_markdown,
    save_final_report_outputs,
)
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
        "key_risks": ["Visible classroom maintenance concern."],
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
        {"validated_final_verdict": {"key_risks": ["Visible classroom maintenance concern."]}},
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


def test_enterprise_report_renderers_include_risks_scope_and_actions(tmp_path: Path) -> None:
    html_text = render_report_html(report_content(), metadata(tmp_path), category_packets())
    markdown_text = render_report_markdown(report_content(), metadata(tmp_path), category_packets())

    assert "Status Dashboard" in markdown_text
    assert "Category Coverage" in markdown_text
    assert "Key Risks" in markdown_text
    assert "Priority Actions" in markdown_text
    assert "Section-wise Findings" in markdown_text
    assert "Overall status" not in markdown_text
    assert "Categories processed" not in markdown_text
    assert "Human review items" not in markdown_text
    assert "Generated at" not in markdown_text
    assert "Human review required" in html_text
    assert "Key Risks" in html_text
    assert "Overall status" not in html_text
    assert "Categories processed" not in html_text
    assert "Review items" not in html_text
    assert "Generated at" not in html_text
    assert "Priority Actions" in html_text
    assert "Section-wise Findings" in html_text


def test_pdf_renderer_uses_reportlab_by_default(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("SCHOOL_VALIDATOR_PDF_RENDERER", raising=False)
    pdf_path = tmp_path / "report.pdf"

    renderer = render_report_pdf(
        "<html><body>Report</body></html>",
        pdf_path,
        report_content(),
        metadata(tmp_path),
        category_packets(),
    )

    assert renderer == "reportlab"
    assert pdf_path.exists()


def test_pdf_renderer_can_opt_into_weasyprint(monkeypatch, tmp_path: Path) -> None:
    class FakeHTML:
        def __init__(self, string, base_url):
            self.string = string
            self.base_url = base_url

        def write_pdf(self, pdf_path):
            Path(pdf_path).write_bytes(b"%PDF-1.4\n")

    monkeypatch.setenv("SCHOOL_VALIDATOR_PDF_RENDERER", "weasyprint")
    monkeypatch.setitem(sys.modules, "weasyprint", SimpleNamespace(HTML=FakeHTML))

    pdf_path = tmp_path / "report.pdf"
    renderer = render_report_pdf(
        "<html><body>Report</body></html>",
        pdf_path,
        report_content(),
        metadata(tmp_path),
        category_packets(),
    )

    assert renderer == "weasyprint"
    assert pdf_path.exists()


def test_reportlab_priority_table_widths_stay_inside_a4_frame() -> None:
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Table

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TableHeader", parent=styles["BodyText"], wordWrap="CJK"))
    styles.add(ParagraphStyle(name="TableCell", parent=styles["BodyText"], wordWrap="CJK"))
    rows = [
        ["Priority", "Category", "Recommended Action", "Evidence", "Review Required"],
        [
            "Medium",
            "classroom",
            "Repair holes and perform minor refurbishment of walls and floor tiles.",
            "classroom_37e6ac9122e642c09b7182816555b133.jpg",
            "No",
        ],
    ]

    table = Table(
        reportlab_table_rows(rows, styles),
        colWidths=reportlab_col_widths(REPORTLAB_PRIORITY_TABLE_WIDTHS_MM),
        repeatRows=1,
    )
    width, _height = table.wrap(REPORTLAB_USABLE_WIDTH_MM * mm, 200 * mm)

    assert sum(REPORTLAB_PRIORITY_TABLE_WIDTHS_MM) == REPORTLAB_USABLE_WIDTH_MM
    assert width <= REPORTLAB_USABLE_WIDTH_MM * mm
