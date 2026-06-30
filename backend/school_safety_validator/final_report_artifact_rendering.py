"""Deterministic Markdown, HTML, and PDF rendering for final reports."""

from __future__ import annotations

import base64
import contextlib
import html
import io
import json
from pathlib import Path

from jinja2 import BaseLoader, Environment, select_autoescape

from .final_report_artifact_validation import validate_rendered_report
from .final_verdict_aggregation import final_report_output_root
from .inspection_data_models import FinalReportContent
from .inspection_runtime_settings import BACKEND_ROOT, ValidatorSettings


SUPPORTED_REPORT_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def find_report_cover_image() -> Path | None:
    """Return the first available report cover image, if one exists."""

    image_dir = BACKEND_ROOT / "utility_files" / "report_img"
    return next(
        iter(
            sorted(
                image_path
                for image_path in image_dir.glob("*")
                if image_path.suffix.lower() in SUPPORTED_REPORT_IMAGE_EXTENSIONS
            )
        ),
        None,
    )


def image_path_to_data_url(image_path: Path | None) -> str:
    """Return a browser/PDF friendly data URL for the report cover image."""

    if not image_path or not image_path.exists():
        return ""

    mime_type = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(image_path.suffix.lower(), "image/png")
    image_base64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    return f"data:{mime_type};base64,{image_base64}"


def status_label(value: str) -> str:
    """Convert schema labels into report-friendly labels."""

    return value.replace("_", " ").title()


def markdown_list(items: list[str]) -> str:
    """Render a compact Markdown bullet list."""

    cleaned_items = [item.strip() for item in items if item and item.strip()]
    if not cleaned_items:
        return "- None recorded."
    return "\n".join(f"- {item}" for item in cleaned_items)


def markdown_table_value(value: object) -> str:
    """Escape values used in Markdown tables."""

    return str(value).replace("|", "\\|").replace("\n", " ")


def build_report_appendix(metadata: dict) -> dict:
    """Return the machine-readable report appendix."""

    return {
        "final_aggregation_json_path": metadata["final_aggregation_json_path"],
        "report_content_json_path": metadata["report_content_json_path"],
        "models": metadata["models"],
        "processed_categories": metadata["processed_categories"],
        "not_inspected_categories": metadata["not_inspected_categories"],
        "total_images": metadata["total_images"],
        "deterministic_status_floor": metadata["deterministic_status_floor"],
    }


def render_report_markdown(content: FinalReportContent, metadata: dict, category_packets: list[dict]) -> str:
    """Render the final report as deterministic Markdown."""

    packet_by_category = {packet["category"]: packet for packet in category_packets}
    category_rows = [
        "| Category | Status | Images | High | Medium | Low | Human Review |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for section in content.category_sections:
        packet = packet_by_category[section.category]
        counts = packet["issue_counts"]
        category_rows.append(
            "| "
            + " | ".join(
                [
                    markdown_table_value(section.category),
                    markdown_table_value(status_label(section.status)),
                    markdown_table_value(packet["image_count"]),
                    markdown_table_value(counts.get("high", 0)),
                    markdown_table_value(counts.get("medium", 0)),
                    markdown_table_value(counts.get("low", 0)),
                    markdown_table_value("Yes" if packet["human_review_required"] else "No"),
                ]
            )
            + " |"
        )

    category_sections = []
    for section in content.category_sections:
        category_sections.append(
            f"### {section.category}\n\n"
            f"- Status: {status_label(section.status)}\n"
            f"- Priority: {status_label(section.priority)}\n\n"
            f"{section.summary}\n\n"
            f"Evidence references:\n{markdown_list(section.evidence_refs)}\n\n"
            f"Recommended actions:\n{markdown_list(section.recommended_actions)}"
        )

    source_lines = [
        f"- {item['category']}: {item['path']} ({item['last_modified_utc']})"
        for item in metadata["category_output_sources"]
    ]
    cover_lines = []
    if metadata.get("cover_image_path"):
        cover_lines = [f"![Report cover]({metadata['cover_image_path']})", ""]

    return "\n\n".join(
        [
            *cover_lines,
            f"# {content.title}",
            f"Generated at: {metadata['generated_at_utc']}",
            "## Overall Verdict\n\n"
            f"- Overall status: {content.overall_status}\n"
            f"- Provisional: {'Yes' if content.provisional else 'No'}\n"
            f"- Deterministic status floor: {metadata['deterministic_status_floor']}",
            "## Executive Summary\n\n" + markdown_list(content.executive_summary),
            "## Scope and Inspected Categories\n\n" + markdown_list(content.scope_and_inputs),
            "## Input Provenance\n\n" + "\n".join(source_lines),
            "## Category Summary Table\n\n" + "\n".join(category_rows),
            "## Immediate Actions\n\n" + markdown_list(content.immediate_actions),
            "## Maintenance Actions\n\n" + markdown_list(content.maintenance_actions),
            "## Documentation Follow-ups\n\n" + markdown_list(content.documentation_followups),
            "## Human Review Notes\n\n" + markdown_list(content.human_review_notes),
            "## Category-by-Category Findings\n\n" + "\n\n".join(category_sections),
            "## Limitations and Disclaimer\n\n" + markdown_list(content.limitations) + f"\n\n{content.disclaimer}",
            "## Machine-Readable Appendix\n\n```json\n"
            + json.dumps(build_report_appendix(metadata), indent=2, ensure_ascii=False)
            + "\n```",
        ]
    ) + "\n"


REPORT_HTML_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{{ content.title }}</title>
<style>
@page { size: A4; margin: 22mm 20mm; @bottom-center { content: "AI-assisted visual inspection summary, not a safety certification - Page " counter(page) " of " counter(pages); color: #667085; font-size: 8pt; } }
@page cover { margin: 0; @bottom-center { content: ""; } }
* { box-sizing: border-box; }
body { color: #172033; font-family: Arial, Helvetica, sans-serif; font-size: 10.5pt; line-height: 1.48; margin: 0; }
.cover { background: #071f3d; color: white; min-height: 297mm; padding: 22mm; page: cover; page-break-after: always; position: relative; }
.cover h1 { color: white; font-size: 33pt; line-height: 1.08; margin: 0 0 7mm; max-width: 170mm; }
.cover-kicker { color: #9ed0ff; font-size: 10pt; font-weight: 700; letter-spacing: 0.08em; margin-bottom: 6mm; text-transform: uppercase; }
.cover-subtitle { color: #d8e7f7; font-size: 13pt; max-width: 150mm; }
.cover-meta { border-left: 4px solid #46b3ff; color: #e8f2ff; font-size: 10.5pt; margin-top: 11mm; padding-left: 6mm; }
.cover-image { background: rgba(255, 255, 255, 0.08); border: 1px solid rgba(255, 255, 255, 0.18); border-radius: 8px; margin-top: 12mm; padding: 5mm; }
.cover-image img { border-radius: 6px; display: block; width: 100%; }
.cover-footer { bottom: 18mm; color: #a9bfd7; font-size: 9pt; left: 22mm; position: absolute; right: 22mm; }
h1 { color: #102a43; font-size: 25pt; margin: 0 0 9mm; }
h2 { border-bottom: 2px solid #d7e3ef; color: #12385b; font-size: 15.5pt; margin-top: 10mm; padding-bottom: 2mm; }
h3 { color: #23435f; font-size: 12.5pt; margin-top: 7mm; }
table { border-collapse: collapse; margin: 4mm 0 7mm; width: 100%; }
th, td { border: 1px solid #c9d6e2; padding: 6px 8px; text-align: left; vertical-align: top; }
th { background: #eaf2f8; color: #153754; font-weight: 700; }
tbody tr:nth-child(even) { background: #f8fbfd; }
.badge { border-radius: 999px; color: white; display: inline-block; font-size: 9pt; font-weight: 700; padding: 4px 10px; text-transform: uppercase; }
.urgent { background: #b42318; }
.medium { background: #b54708; }
.status-ok { background: #027a48; }
.status-insufficient { background: #667085; }
.summary-card { background: #f5f9fc; border: 1px solid #d7e3ef; border-left: 5px solid #2474a6; border-radius: 8px; margin: 5mm 0 7mm; padding: 5mm; }
.category-block { border-top: 1px solid #d7e3ef; padding-top: 5mm; page-break-inside: avoid; }
.meta { color: #52677a; font-size: 9pt; }
.disclaimer { background: #fff7ed; border: 1px solid #fed7aa; border-left: 5px solid #f97316; border-radius: 8px; padding: 8px 10px; }
code, pre { font-family: Consolas, monospace; font-size: 8.5pt; }
pre { background: #f7fafc; border: 1px solid #d7e3ef; border-radius: 6px; padding: 8px; white-space: pre-wrap; }
</style>
</head>
<body>
<section class="cover">
  <div class="cover-kicker">AI-assisted school condition validator</div>
  <h1>{{ content.title }}</h1>
  <p class="cover-subtitle">A cautious visual inspection summary generated from category-level evidence packets and deterministic validation checks.</p>
  <div class="cover-meta">
    <p>Overall status: <strong>{{ content.overall_status }}</strong></p>
    <p>Provisional: <strong>{{ "Yes" if content.provisional else "No" }}</strong></p>
    <p>Generated at: {{ metadata.generated_at_utc }}</p>
  </div>
  {% if cover_image_url %}<div class="cover-image"><img src="{{ cover_image_url }}" alt="School inspection report visual"></div>{% endif %}
  <div class="cover-footer">{{ content.disclaimer }}</div>
</section>
<main>
<h1>{{ content.title }}</h1>
<p class="meta">Generated at: {{ metadata.generated_at_utc }}</p>
<h2>Overall Verdict</h2>
<div class="summary-card">
  <p><span class="badge {{ status_class }}">{{ content.overall_status }}</span></p>
  <ul><li>Provisional: {{ "Yes" if content.provisional else "No" }}</li><li>Deterministic status floor: {{ metadata.deterministic_status_floor }}</li></ul>
</div>
<h2>Executive Summary</h2>
<ul>{% for item in content.executive_summary %}<li>{{ item }}</li>{% else %}<li>None recorded.</li>{% endfor %}</ul>
<h2>Scope and Inspected Categories</h2>
<ul>{% for item in content.scope_and_inputs %}<li>{{ item }}</li>{% else %}<li>None recorded.</li>{% endfor %}</ul>
<h2>Input Provenance</h2>
<ul>{% for item in metadata.category_output_sources %}<li><code>{{ item.category }}</code>: <code>{{ item.path }}</code> ({{ item.last_modified_utc }})</li>{% endfor %}</ul>
<h2>Category Summary Table</h2>
<table><thead><tr><th>Category</th><th>Status</th><th>Images</th><th>High</th><th>Medium</th><th>Low</th><th>Human Review</th></tr></thead><tbody>
{% for row in category_table %}<tr><td><code>{{ row.category }}</code></td><td>{{ row.status }}</td><td>{{ row.image_count }}</td><td>{{ row.high }}</td><td>{{ row.medium }}</td><td>{{ row.low }}</td><td>{{ row.human_review }}</td></tr>{% endfor %}
</tbody></table>
<h2>Immediate Actions</h2><ul>{% for item in content.immediate_actions %}<li>{{ item }}</li>{% else %}<li>None recorded.</li>{% endfor %}</ul>
<h2>Maintenance Actions</h2><ul>{% for item in content.maintenance_actions %}<li>{{ item }}</li>{% else %}<li>None recorded.</li>{% endfor %}</ul>
<h2>Documentation Follow-ups</h2><ul>{% for item in content.documentation_followups %}<li>{{ item }}</li>{% else %}<li>None recorded.</li>{% endfor %}</ul>
<h2>Human Review Notes</h2><ul>{% for item in content.human_review_notes %}<li>{{ item }}</li>{% else %}<li>None recorded.</li>{% endfor %}</ul>
<h2>Category-by-Category Findings</h2>
{% for section in content.category_sections %}
<section class="category-block">
<h3>{{ section.category }}</h3>
<ul><li>Status: {{ section.status }}</li><li>Priority: {{ section.priority }}</li></ul>
<p>{{ section.summary }}</p>
<p><strong>Evidence references</strong></p><ul>{% for item in section.evidence_refs %}<li>{{ item }}</li>{% else %}<li>None recorded.</li>{% endfor %}</ul>
<p><strong>Recommended actions</strong></p><ul>{% for item in section.recommended_actions %}<li>{{ item }}</li>{% else %}<li>None recorded.</li>{% endfor %}</ul>
</section>
{% endfor %}
<h2>Limitations and Disclaimer</h2>
<ul>{% for item in content.limitations %}<li>{{ item }}</li>{% endfor %}</ul>
<p class="disclaimer">{{ content.disclaimer }}</p>
<h2>Machine-Readable Appendix</h2>
<pre>{{ appendix_json }}</pre>
</main>
</body>
</html>
""".strip()


def render_report_html(content: FinalReportContent, metadata: dict, category_packets: list[dict]) -> str:
    """Render the final report as deterministic HTML for PDF conversion."""

    packet_by_category = {packet["category"]: packet for packet in category_packets}
    category_table = []
    for section in content.category_sections:
        packet = packet_by_category[section.category]
        counts = packet["issue_counts"]
        category_table.append(
            {
                "category": section.category,
                "status": status_label(section.status),
                "image_count": packet["image_count"],
                "high": counts.get("high", 0),
                "medium": counts.get("medium", 0),
                "low": counts.get("low", 0),
                "human_review": "Yes" if packet["human_review_required"] else "No",
            }
        )

    status_class = {
        "urgent_review_required": "urgent",
        "maintenance_attention_required": "medium",
        "insufficient_evidence": "status-insufficient",
        "acceptable_with_minor_issues": "status-ok",
    }[content.overall_status]
    cover_image_path = Path(metadata["cover_image_path"]) if metadata.get("cover_image_path") else None

    environment = Environment(loader=BaseLoader(), autoescape=select_autoescape(default=True))
    template = environment.from_string(REPORT_HTML_TEMPLATE)
    return template.render(
        content=content.model_dump(mode="json"),
        metadata=metadata,
        category_table=category_table,
        status_class=status_class,
        cover_image_url=image_path_to_data_url(cover_image_path),
        appendix_json=json.dumps(build_report_appendix(metadata), indent=2, ensure_ascii=False),
    )


def reportlab_text(value: str) -> str:
    """Escape text for ReportLab Paragraph markup."""

    return html.escape(value or "")


def reportlab_bullet_list(items: list[str], styles: dict) -> list:
    """Convert text items into ReportLab bullet paragraphs."""

    from reportlab.platypus import Paragraph

    cleaned_items = [item.strip() for item in items if item and item.strip()]
    if not cleaned_items:
        cleaned_items = ["None recorded."]
    return [Paragraph("- " + reportlab_text(item), styles["BodyText"]) for item in cleaned_items]


def render_report_pdf_with_reportlab(
    content: FinalReportContent,
    metadata: dict,
    category_packets: list[dict],
    pdf_path: Path,
) -> None:
    """Render a deterministic PDF with ReportLab when WeasyPrint is unavailable."""

    from PIL import Image as PILImage
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image as RLImage
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="CoverText",
            parent=styles["BodyText"],
            textColor=colors.HexColor("#d8e7f7"),
            fontSize=11,
            leading=15,
        )
    )
    styles["Heading2"].textColor = colors.HexColor("#12385b")
    styles["Heading3"].textColor = colors.HexColor("#23435f")

    story = [
        Table(
            [[Paragraph("AI-assisted school condition validator", styles["CoverText"])]],
            colWidths=[170 * mm],
            style=[
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#071f3d")),
                ("BOX", (0, 0), (-1, -1), 0, colors.HexColor("#071f3d")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ],
        ),
        Spacer(1, 10 * mm),
        Paragraph(reportlab_text(content.title), styles["Title"]),
        Paragraph(
            "A cautious visual inspection summary generated from category-level evidence packets and deterministic validation checks.",
            styles["BodyText"],
        ),
        Spacer(1, 6 * mm),
    ]

    cover_image_path = Path(metadata["cover_image_path"]) if metadata.get("cover_image_path") else None
    if cover_image_path and cover_image_path.exists():
        image_width_px, image_height_px = PILImage.open(cover_image_path).size
        cover_width = 170 * mm
        cover_height = cover_width * image_height_px / image_width_px
        cover_image = RLImage(str(cover_image_path), width=cover_width, height=cover_height)
        cover_image.hAlign = "CENTER"
        story.extend([cover_image, Spacer(1, 7 * mm)])

    story.extend(
        [
            Paragraph(f"Generated at: {reportlab_text(metadata['generated_at_utc'])}", styles["BodyText"]),
            Paragraph(f"Overall status: {reportlab_text(content.overall_status)}", styles["BodyText"]),
            Paragraph(f"Provisional: {'Yes' if content.provisional else 'No'}", styles["BodyText"]),
            Paragraph(reportlab_text(content.disclaimer), styles["BodyText"]),
            PageBreak(),
            Paragraph(f"Generated at: {reportlab_text(metadata['generated_at_utc'])}", styles["Normal"]),
            Paragraph("Overall Verdict", styles["Heading2"]),
            Paragraph(f"Overall status: {reportlab_text(content.overall_status)}", styles["BodyText"]),
            Paragraph(f"Provisional: {'Yes' if content.provisional else 'No'}", styles["BodyText"]),
            Paragraph(
                f"Deterministic status floor: {reportlab_text(metadata['deterministic_status_floor'])}",
                styles["BodyText"],
            ),
            Paragraph("Executive Summary", styles["Heading2"]),
            *reportlab_bullet_list(content.executive_summary, styles),
            Paragraph("Scope and Inspected Categories", styles["Heading2"]),
            *reportlab_bullet_list(content.scope_and_inputs, styles),
            Paragraph("Input Provenance", styles["Heading2"]),
            *reportlab_bullet_list(
                [
                    f"{item['category']}: {item['path']} ({item['last_modified_utc']})"
                    for item in metadata["category_output_sources"]
                ],
                styles,
            ),
        ]
    )

    packet_by_category = {packet["category"]: packet for packet in category_packets}
    table_rows = [["Category", "Status", "Images", "High", "Medium", "Low", "Human Review"]]
    for section in content.category_sections:
        packet = packet_by_category[section.category]
        counts = packet["issue_counts"]
        table_rows.append(
            [
                section.category,
                status_label(section.status),
                str(packet["image_count"]),
                str(counts.get("high", 0)),
                str(counts.get("medium", 0)),
                str(counts.get("low", 0)),
                "Yes" if packet["human_review_required"] else "No",
            ]
        )

    story.append(Paragraph("Category Summary Table", styles["Heading2"]))
    table = Table(table_rows, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f4f7")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d5dd")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.extend([table, Spacer(1, 4 * mm)])

    for heading, items in [
        ("Immediate Actions", content.immediate_actions),
        ("Maintenance Actions", content.maintenance_actions),
        ("Documentation Follow-ups", content.documentation_followups),
        ("Human Review Notes", content.human_review_notes),
    ]:
        story.append(Paragraph(heading, styles["Heading2"]))
        story.extend(reportlab_bullet_list(items, styles))

    story.append(Paragraph("Category-by-Category Findings", styles["Heading2"]))
    for section in content.category_sections:
        story.extend(
            [
                Paragraph(reportlab_text(section.category), styles["Heading3"]),
                Paragraph(f"Status: {reportlab_text(section.status)}", styles["BodyText"]),
                Paragraph(f"Priority: {reportlab_text(section.priority)}", styles["BodyText"]),
                Paragraph(reportlab_text(section.summary), styles["BodyText"]),
                Paragraph("Evidence references", styles["Heading4"]),
                *reportlab_bullet_list(section.evidence_refs, styles),
                Paragraph("Recommended actions", styles["Heading4"]),
                *reportlab_bullet_list(section.recommended_actions, styles),
            ]
        )

    story.append(Paragraph("Limitations and Disclaimer", styles["Heading2"]))
    story.extend(reportlab_bullet_list(content.limitations, styles))
    story.append(Paragraph(reportlab_text(content.disclaimer), styles["BodyText"]))
    story.append(Paragraph("Machine-Readable Appendix", styles["Heading2"]))
    story.append(
        Paragraph(
            reportlab_text(json.dumps(build_report_appendix(metadata), indent=2, ensure_ascii=False)).replace(
                "\n", "<br />"
            ),
            styles["Code"],
        )
    )

    document = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=22 * mm,
        bottomMargin=22 * mm,
    )
    document.build(story)


def render_report_pdf(
    html_text: str,
    pdf_path: Path,
    content: FinalReportContent,
    metadata: dict,
    category_packets: list[dict],
) -> str:
    """Render HTML into PDF with WeasyPrint, falling back to ReportLab if needed."""

    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            from weasyprint import HTML

        HTML(string=html_text, base_url=str(Path.cwd())).write_pdf(pdf_path)
        return "weasyprint"
    except Exception:
        render_report_pdf_with_reportlab(content, metadata, category_packets, pdf_path)
        return "reportlab"


def save_final_report_outputs(
    content: FinalReportContent,
    payload: dict,
    metadata: dict,
    category_packets: list[dict],
    global_rollup: dict,
    settings: ValidatorSettings,
) -> dict[str, Path]:
    """Save final Markdown, HTML, PDF, JSON, and payload artifacts."""

    output_root = final_report_output_root(settings)
    paths = {
        "markdown_report": output_root / "school_safety_final_report.md",
        "html_report": output_root / "school_safety_final_report.html",
        "pdf_report": output_root / "school_safety_final_report.pdf",
        "report_content_json": output_root / "school_safety_final_report_content.json",
        "report_generation_payload": output_root / "report_generation_payload.json",
    }

    markdown_text = render_report_markdown(content, metadata, category_packets)
    html_text = render_report_html(content, metadata, category_packets)
    paths["markdown_report"].write_text(markdown_text, encoding="utf-8")
    paths["html_report"].write_text(html_text, encoding="utf-8")
    paths["report_content_json"].write_text(content.model_dump_json(indent=2), encoding="utf-8")
    paths["report_generation_payload"].write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    metadata["pdf_renderer"] = render_report_pdf(html_text, paths["pdf_report"], content, metadata, category_packets)

    validate_rendered_report(content, paths, category_packets, global_rollup)
    return paths
