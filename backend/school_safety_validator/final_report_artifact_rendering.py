"""Deterministic Markdown, HTML, and PDF rendering for final reports."""

from __future__ import annotations

import base64
import contextlib
import html
import io
import json
import os
from pathlib import Path

from jinja2 import BaseLoader, Environment, select_autoescape

from .final_report_artifact_validation import validate_rendered_report
from .final_verdict_aggregation import final_report_output_root
from .inspection_data_models import FinalReportContent
from .logging_config import logging
from .inspection_runtime_settings import BACKEND_ROOT, ValidatorSettings


logger = logging.getLogger(__name__)


REPORTLAB_USABLE_WIDTH_MM = 170
REPORTLAB_CATEGORY_TABLE_WIDTHS_MM = [32, 38, 16, 13, 16, 13, 42]
REPORTLAB_PRIORITY_TABLE_WIDTHS_MM = [18, 32, 55, 38, 27]
STATUS_LABEL_OVERRIDES = {
    "insufficient_evidence": "Review Required",
}
REPORT_STATUS_LABEL = "AI-Assisted Draft - Requires Qualified Review"
STANDARD_LIMITATIONS = [
    "This report is based only on the provided images, comments, and automated validation outputs.",
    "It does not certify safety, code compliance, structural soundness, electrical safety, hygiene, or serviceability.",
    "Hidden defects, non-visible areas, image-quality limitations, and missing evidence may affect the findings.",
    "Qualified personnel must review the evidence before decisions, repairs, closures, or compliance actions are made.",
]


def find_report_cover_image() -> Path | None:
    """Return the bundled report cover image when it is available."""

    cover_image_path = BACKEND_ROOT / "utility_files" / "report_img" / "sample_report_image.png"
    return cover_image_path if cover_image_path.is_file() else None


def image_path_to_data_url(image_path: str) -> str:
    """Return a local image as an HTML data URL for PDF-safe rendering."""

    path = Path(image_path)
    mime_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    mime_type = mime_types.get(path.suffix.lower())
    if not mime_type or not path.is_file():
        return ""
    encoded_image = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded_image}"


def status_label(value: str) -> str:
    """Convert schema labels into report-friendly labels."""

    return STATUS_LABEL_OVERRIDES.get(value, value.replace("_", " ").title())


def markdown_list(items: list[str]) -> str:
    """Render a compact Markdown bullet list."""

    cleaned_items = clean_text_items(items)
    if not cleaned_items:
        return "- None recorded."
    return "\n".join(f"- {item}" for item in cleaned_items)


def markdown_table_value(value: object) -> str:
    """Escape values used in Markdown tables."""

    return str(value).replace("|", "\\|").replace("\n", " ")


def build_report_appendix(metadata: dict) -> dict:
    """Return the machine-readable report appendix."""

    return {
        "final_aggregation_json": Path(metadata["final_aggregation_json_path"]).name,
        "report_content_json": Path(metadata["report_content_json_path"]).name,
        "models": metadata["models"],
        "not_inspected_categories": metadata["not_inspected_categories"],
        "total_images": metadata["total_images"],
        "deterministic_status_floor": status_label(metadata["deterministic_status_floor"]),
        "human_review_completed": metadata.get("human_review_completed", False),
        "human_review_decisions": metadata.get("human_review_decisions", []),
        "evidence_id_mapping": metadata.get("evidence_id_mapping", []),
    }


def clean_text_items(items: list[str]) -> list[str]:
    """Return non-empty stripped text items."""

    return [item.strip() for item in items if item and item.strip()]


def build_limitations(items: list[str]) -> list[str]:
    """Return limitations with the standard visual-inspection caveats always present."""

    limitations = clean_text_items(items)
    existing = {item.lower() for item in limitations}
    for limitation in STANDARD_LIMITATIONS:
        if limitation.lower() not in existing:
            limitations.append(limitation)
    return limitations


def display_filename(value: str, evidence_filename_map: dict[str, str] | None = None) -> str:
    """Return a report-safe evidence filename without exposing internal folders."""

    cleaned_value = str(value or "").strip()
    if not cleaned_value:
        return ""
    evidence_filename_map = evidence_filename_map or {}
    mapped_value = evidence_filename_map.get(cleaned_value, cleaned_value)
    return Path(str(mapped_value)).name


def display_filenames(values: list[str], evidence_filename_map: dict[str, str] | None = None) -> list[str]:
    """Return report-safe evidence filenames for a list of references."""

    return clean_text_items([display_filename(value, evidence_filename_map) for value in values])


def build_evidence_id_mapping(
    content: FinalReportContent,
    category_packets: list[dict],
    metadata: dict,
) -> dict[str, str]:
    """Assign compact display IDs to evidence filenames used in the report."""

    evidence_filename_map = metadata.get("evidence_filename_map", {})
    ordered_filenames = []
    seen = set()

    def add_evidence(value: str) -> None:
        filename = display_filename(value, evidence_filename_map)
        if filename and filename not in seen:
            seen.add(filename)
            ordered_filenames.append(filename)

    for section in content.category_sections:
        for evidence_ref in clean_text_items(list(section.evidence_refs)):
            add_evidence(evidence_ref)

    for packet in category_packets:
        for finding in packet.get("key_findings", []):
            add_evidence(str(finding.get("image_id", "")))
        for gap in packet.get("documentation_gaps", []):
            add_evidence(str(gap.get("image_id", "")))

    for decision in metadata.get("human_review_decisions", []):
        add_evidence(str(decision.get("image_id", "")))

    return {filename: f"E{index}" for index, filename in enumerate(ordered_filenames, start=1)}


def evidence_id_for(
    value: str,
    evidence_id_mapping: dict[str, str],
    evidence_filename_map: dict[str, str] | None = None,
) -> str:
    """Return the compact evidence ID for a reference, falling back to the display filename."""

    filename = display_filename(value, evidence_filename_map)
    return evidence_id_mapping.get(filename, filename)


def evidence_ids_for(
    values: list[str],
    evidence_id_mapping: dict[str, str],
    evidence_filename_map: dict[str, str] | None = None,
) -> list[str]:
    """Return compact evidence IDs for a list of references."""

    return clean_text_items([evidence_id_for(value, evidence_id_mapping, evidence_filename_map) for value in values])


def source_file_label(item: dict) -> str:
    """Return a source label without exposing an internal absolute path."""

    source_name = Path(str(item.get("path", ""))).name
    category = str(item.get("category", "")).strip()
    source_type = str(item.get("source_type", "")).strip()
    if source_type:
        return f"{category}: {source_name} ({source_type})"
    return f"{category}: {source_name}"


def build_category_table_rows(content: FinalReportContent, category_packets: list[dict]) -> list[dict]:
    """Build category table rows shared by Markdown, HTML, and PDF renderers."""

    packet_by_category = {packet["category"]: packet for packet in category_packets}
    rows = []
    for section in content.category_sections:
        packet = packet_by_category[section.category]
        counts = packet["issue_counts"]
        rows.append(
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
    return rows


def status_class(value: str) -> str:
    """Map a report status to a printable CSS class."""

    return {
        "urgent_review_required": "status-urgent",
        "maintenance_attention_required": "status-attention",
        "insufficient_evidence": "status-insufficient",
        "acceptable_with_minor_issues": "status-acceptable",
        "urgent_review": "status-urgent",
        "attention_required": "status-attention",
        "minor_maintenance": "status-minor",
        "acceptable_visible_condition": "status-acceptable",
    }.get(value, "status-neutral")


def priority_class(value: str) -> str:
    """Map a priority label to a printable CSS class."""

    return {
        "urgent": "priority-urgent",
        "high": "priority-high",
        "medium": "priority-medium",
        "low": "priority-low",
    }.get(value, "priority-low")


def evidence_summary(
    section: object,
    packet: dict,
    evidence_id_mapping: dict[str, str],
    evidence_filename_map: dict[str, str] | None = None,
) -> str:
    """Return compact evidence text from already-validated category data."""

    evidence_refs = clean_text_items(list(getattr(section, "evidence_refs", [])))
    key_findings = packet.get("key_findings", [])
    if evidence_refs:
        return ", ".join(evidence_ids_for(evidence_refs[:3], evidence_id_mapping, evidence_filename_map))
    if key_findings:
        return ", ".join(
            evidence_ids_for(
                clean_text_items([item.get("image_id", "") for item in key_findings])[:3],
                evidence_id_mapping,
                evidence_filename_map,
            )
        )
    return "Category-level evidence packet"


def build_priority_action_rows(
    content: FinalReportContent,
    category_packets: list[dict],
    evidence_id_mapping: dict[str, str],
    evidence_filename_map: dict[str, str] | None = None,
) -> list[dict]:
    """Build deterministic action rows from validated category sections."""

    packet_by_category = {packet["category"]: packet for packet in category_packets}
    rows = []
    for section in content.category_sections:
        packet = packet_by_category.get(section.category, {})
        review_required = "Yes" if packet.get("human_review_required") else "No"
        for action in clean_text_items(section.recommended_actions):
            rows.append(
                {
                    "priority": status_label(section.priority),
                    "priority_class": priority_class(section.priority),
                    "category": section.category,
                    "issue": section.summary,
                    "action": action,
                    "evidence": evidence_summary(section, packet, evidence_id_mapping, evidence_filename_map),
                    "review_required": review_required,
                }
            )
    return rows


def build_category_view_sections(
    content: FinalReportContent,
    category_packets: list[dict],
    evidence_id_mapping: dict[str, str],
    evidence_filename_map: dict[str, str] | None = None,
) -> list[dict]:
    """Prepare deterministic category display fields without changing semantics."""

    packet_by_category = {packet["category"]: packet for packet in category_packets}
    sections = []
    for section in content.category_sections:
        packet = packet_by_category[section.category]
        key_findings = []
        for finding in packet.get("key_findings", []):
            key_findings.append(
                {
                    **finding,
                    "image_id": evidence_id_for(finding.get("image_id", ""), evidence_id_mapping, evidence_filename_map),
                }
            )
        documentation_gaps = []
        for gap in packet.get("documentation_gaps", []):
            documentation_gaps.append(
                {
                    **gap,
                    "image_id": evidence_id_for(gap.get("image_id", ""), evidence_id_mapping, evidence_filename_map),
                }
            )
        sections.append(
            {
                "category": section.category,
                "status": section.status,
                "status_label": status_label(section.status),
                "status_class": status_class(section.status),
                "priority": section.priority,
                "priority_label": status_label(section.priority),
                "priority_class": priority_class(section.priority),
                "summary": section.summary,
                "image_count": packet["image_count"],
                "human_review_required": packet["human_review_required"],
                "issue_counts": packet["issue_counts"],
                "key_findings": key_findings,
                "documentation_gaps": documentation_gaps,
                "evidence_refs": evidence_ids_for(section.evidence_refs, evidence_id_mapping, evidence_filename_map),
                "recommended_actions": clean_text_items(section.recommended_actions),
            }
        )
    return sections


def build_global_action_groups(content: FinalReportContent) -> list[dict]:
    """Prepare validated global action lists for display."""

    return [
        {"label": "Immediate Actions", "action_items": clean_text_items(content.immediate_actions)},
        {"label": "Maintenance Actions", "action_items": clean_text_items(content.maintenance_actions)},
        {
            "label": "Documentation Follow-ups",
            "action_items": clean_text_items(content.documentation_followups),
        },
    ]


def build_human_review_decision_rows(metadata: dict, evidence_id_mapping: dict[str, str]) -> list[dict]:
    """Return exact human-review decisions for deterministic report display."""

    evidence_filename_map = metadata.get("evidence_filename_map", {})
    return [
        {
            "category": str(decision.get("category_name", "")),
            "image_id": evidence_id_for(str(decision.get("image_id", "")), evidence_id_mapping, evidence_filename_map),
            "status": str(decision.get("status", "")),
            "notes": str(decision.get("notes", "")),
        }
        for decision in metadata.get("human_review_decisions", [])
    ]


def build_report_view_model(content: FinalReportContent, metadata: dict, category_packets: list[dict]) -> dict:
    """Build deterministic display data for Markdown, HTML, and PDF renderers."""

    not_inspected_categories = clean_text_items(metadata.get("not_inspected_categories", []))
    evidence_filename_map = metadata.get("evidence_filename_map", {})
    evidence_id_mapping = build_evidence_id_mapping(content, category_packets, metadata)
    metadata["evidence_id_mapping"] = [
        {"evidence_id": evidence_id, "filename": filename}
        for filename, evidence_id in evidence_id_mapping.items()
    ]
    human_review_items = sum(1 for packet in category_packets if packet.get("human_review_required"))
    issue_counts = {"high": 0, "medium": 0, "low": 0}
    for packet in category_packets:
        for severity in issue_counts:
            issue_counts[severity] += packet.get("issue_counts", {}).get(severity, 0)

    return {
        "title": content.title,
        "report_status_label": REPORT_STATUS_LABEL,
        "cover_image_url": image_path_to_data_url(str(metadata.get("cover_image_path", ""))),
        "provisional": content.provisional,
        "not_inspected_categories": not_inspected_categories,
        "total_images": metadata["total_images"],
        "human_review_items": human_review_items,
        "human_review_completed": metadata.get("human_review_completed", False),
        "human_review_decision_rows": build_human_review_decision_rows(metadata, evidence_id_mapping),
        "issue_counts": issue_counts,
        "deterministic_status_floor": metadata["deterministic_status_floor"],
        "deterministic_status_floor_label": status_label(metadata["deterministic_status_floor"]),
        "category_table": build_category_table_rows(content, category_packets),
        "category_sections": build_category_view_sections(content, category_packets, evidence_id_mapping, evidence_filename_map),
        "priority_action_rows": build_priority_action_rows(content, category_packets, evidence_id_mapping, evidence_filename_map),
        "global_action_groups": build_global_action_groups(content),
        "executive_summary": clean_text_items(content.executive_summary),
        "key_risks": clean_text_items(metadata.get("key_risks", [])),
        "scope_and_inputs": clean_text_items(content.scope_and_inputs),
        "human_review_notes": clean_text_items(content.human_review_notes),
        "limitations": build_limitations(content.limitations),
        "disclaimer": content.disclaimer,
        "source_files": [source_file_label(item) for item in metadata["category_output_sources"]],
        "appendix": build_report_appendix(metadata),
    }


def render_report_markdown(content: FinalReportContent, metadata: dict, category_packets: list[dict]) -> str:
    """Render the final report as deterministic Markdown."""

    view = build_report_view_model(content, metadata, category_packets)
    category_rows = [
        "| Category | Status | Images | High | Medium | Low | Review Flag |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in view["category_table"]:
        category_rows.append(
            "| "
            + " | ".join(
                [
                    markdown_table_value(row["category"]),
                    markdown_table_value(row["status"]),
                    markdown_table_value(row["image_count"]),
                    markdown_table_value(row["high"]),
                    markdown_table_value(row["medium"]),
                    markdown_table_value(row["low"]),
                    markdown_table_value(row["human_review"]),
                ]
            )
            + " |"
        )

    action_rows = [
        "| Priority | Category | Recommended Action | Evidence IDs | Review Flag |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in view["priority_action_rows"]:
        action_rows.append(
            "| "
            + " | ".join(
                [
                    markdown_table_value(row["priority"]),
                    markdown_table_value(row["category"]),
                    markdown_table_value(row["action"]),
                    markdown_table_value(row["evidence"]),
                    markdown_table_value(row["review_required"]),
                ]
            )
            + " |"
        )

    category_sections = []
    for section in view["category_sections"]:
        finding_lines = [
            f"- {finding.get('severity', 'unclear')}: {finding.get('issue_type', '')} - {finding.get('evidence', '')}"
            for finding in section["key_findings"]
        ]
        gap_lines = [
            f"- {gap.get('image_id', '')}: {gap.get('gap', '')}"
            for gap in section["documentation_gaps"]
        ]
        category_sections.append(
            f"### {section['category']}\n\n"
            f"- Status: {section['status_label']}\n"
            f"- Priority: {section['priority_label']}\n"
            f"- Images reviewed: {section['image_count']}\n"
            f"- Human review required: {'Yes' if section['human_review_required'] else 'No'}\n\n"
            f"{section['summary']}\n\n"
            f"Key findings:\n{markdown_list(finding_lines)}\n\n"
            f"Evidence references:\n{markdown_list(section['evidence_refs'])}\n\n"
            f"Documentation gaps:\n{markdown_list(gap_lines)}\n\n"
            f"Recommended actions:\n{markdown_list(section['recommended_actions'])}"
        )

    source_lines = [f"- {item}" for item in view["source_files"]]
    decision_lines = [
        f"- {row['category']} / {row['image_id']}: {row['status']} - {row['notes'] or 'No reviewer notes.'}"
        for row in view["human_review_decision_rows"]
    ]
    return "\n\n".join(
        [
            f"# {content.title}",
            "## Status Dashboard\n\n"
            f"- Report status: {view['report_status_label']}\n"
            f"- Categories not inspected: {len(view['not_inspected_categories'])}\n"
            f"- Total images: {view['total_images']}\n"
            f"- Deterministic status floor: {view['deterministic_status_floor_label']}",
            "## Human Review Notice\n\n"
            + (
                "Human review was completed before this final report was generated."
                if view["human_review_items"] and view["human_review_completed"]
                else (
                    "This report is provisional and requires human review before decisions are made."
                    if content.provisional or view["human_review_items"]
                    else "No automated human-review escalation was triggered."
                )
            ),
            "## Executive Summary\n\n" + markdown_list(view["executive_summary"]),
            "## Key Risks\n\n" + markdown_list(view["key_risks"]),
            "## Category Coverage\n\n"
            f"Not inspected categories:\n{markdown_list(view['not_inspected_categories'])}\n\n"
            f"Scope notes:\n{markdown_list(view['scope_and_inputs'])}",
            "## Source References\n\n" + "\n".join(source_lines),
            "## Category Summary Table\n\n" + "\n".join(category_rows),
            "## Priority Actions\n\n" + ("\n".join(action_rows) if view["priority_action_rows"] else "- None recorded."),
            "## Global Action Lists\n\n"
            + "\n\n".join(
                f"### {group['label']}\n\n{markdown_list(group['action_items'])}"
                for group in view["global_action_groups"]
            ),
            "## Human Review Notes\n\n" + markdown_list(view["human_review_notes"]),
            "## Human Review Decisions\n\n" + markdown_list(decision_lines),
            "## Section-wise Findings\n\n" + "\n\n".join(category_sections),
            "## Limitations and Disclaimer\n\n" + markdown_list(view["limitations"]) + f"\n\n{content.disclaimer}",
            "## Machine-Readable Appendix\n\n```json\n"
            + json.dumps(view["appendix"], indent=2, ensure_ascii=False)
            + "\n```",
        ]
    ) + "\n"


REPORT_HTML_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{{ view.title }}</title>
<style>
@page {
  background: #fbfcee;
  size: A4;
  margin: 17mm 15mm 18mm 15mm;
  @top-left {
    content: "SchoolReview AI";
    color: #7a684f;
    font-size: 8.5pt;
  }
  @bottom-right {
    content: "Page " counter(page) " of " counter(pages);
    color: #7a684f;
    font-size: 8.5pt;
  }
  @bottom-left {
    content: "AI-assisted visual inspection summary - not a certification";
    color: #7a684f;
    font-size: 8.5pt;
  }
}
@page cover {
  margin: 0;
  @top-left { content: ""; }
  @bottom-left { content: ""; }
  @bottom-right { content: ""; }
}
* { box-sizing: border-box; }
html { background: #fbfcee; color: #33291f; font-family: "Aptos", "Avenir Next", "Segoe UI", "Noto Sans", Arial, sans-serif; font-size: 10.2pt; line-height: 1.5; }
body { background: #fbfcee; margin: 0; }
h1, h2, h3 { color: #3f331f; line-height: 1.18; margin: 0; }
h1 { font-family: Georgia, "Iowan Old Style", "Times New Roman", serif; }
h2 { border-bottom: 1px solid #c9b27c; color: #4f4f2a; font-size: 16pt; margin: 10mm 0 4mm; padding-bottom: 2mm; page-break-after: avoid; }
h3 { color: #5b4a2e; font-size: 12.5pt; margin: 3mm 0 3mm; page-break-after: avoid; }
p { margin: 0 0 3mm; }
ul { margin: 2mm 0 4mm 5mm; padding: 0; }
li { margin: 0 0 1.5mm; }
table { border-collapse: collapse; margin: 3mm 0 7mm; page-break-inside: auto; table-layout: fixed; width: 100%; }
thead { display: table-header-group; }
tr { page-break-inside: avoid; }
th, td { border: 1px solid #d8c8a7; hyphens: none; overflow-wrap: break-word; padding: 7px 8px; text-align: left; vertical-align: top; word-break: normal; }
th { background: #efe4c8; color: #4d4028; font-size: 8.5pt; letter-spacing: .03em; text-transform: uppercase; }
td { font-size: 9.2pt; }
tbody tr:nth-child(even) { background: #f5f7df; }
code, pre { font-family: Consolas, "Courier New", monospace; font-size: 8.4pt; }
pre { background: #f5f7df; border: 1px solid #d8c8a7; border-radius: 6px; padding: 8px; white-space: pre-wrap; }
.cover { background: linear-gradient(135deg, #3c2c1f 0%, #596239 58%, #9a6b20 100%); color: #fffaf0; min-height: 297mm; padding: 21mm; page: cover; page-break-after: always; position: relative; }
.cover-kicker { color: #f0c76a; font-size: 9pt; font-weight: 700; letter-spacing: .11em; margin-bottom: 7mm; text-transform: uppercase; }
.cover h1 { color: #fff8e8; font-size: 30pt; max-width: 160mm; }
.cover-subtitle { color: #f5e8c8; font-size: 12.5pt; margin-top: 6mm; max-width: 150mm; }
.cover-grid { display: grid; gap: 5mm; grid-template-columns: minmax(0, 1.35fr) minmax(0, .75fr); margin-top: 12mm; }
.cover-panel { background: rgba(58, 43, 29, .28); border: 1px solid rgba(255,244,214,.36); border-radius: 8px; min-height: 24mm; padding: 5mm; }
.cover-label { color: #f4d58d; font-size: 8pt; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; }
.cover-value { color: #fffaf0; font-size: 11.5pt; font-weight: 700; line-height: 1.25; margin-top: 2mm; overflow-wrap: break-word; }
.cover-image { background: rgba(58, 43, 29, .22); border: 1px solid rgba(255,244,214,.36); border-radius: 8px; margin-top: 8mm; overflow: hidden; }
.cover-image img { display: block; height: 78mm; object-fit: cover; width: 100%; }
.cover-footer { bottom: 17mm; color: #f5e8c8; font-size: 8.8pt; left: 21mm; position: absolute; right: 21mm; }
.report-header { border-bottom: 3px solid #7b6f38; margin-bottom: 6mm; padding-bottom: 4mm; }
.report-header h1 { font-size: 21pt; margin-bottom: 2mm; }
.meta-line { color: #6d5c41; font-size: 9pt; }
.badge { border-radius: 999px; display: inline-block; font-size: 8.5pt; font-weight: 700; letter-spacing: .02em; padding: 4px 9px; text-transform: uppercase; }
.status-urgent { background: #8f2f1c; color: #fff; }
.status-attention { background: #9a6b20; color: #fff; }
.status-insufficient { background: #6b5f49; color: #fff; }
.status-minor { background: #626b35; color: #fff; }
.status-acceptable { background: #46633a; color: #fff; }
.status-neutral { background: #7a684f; color: #fff; }
.priority-urgent, .priority-high { background: #f4dfcf; color: #7b2f1d; }
.priority-medium { background: #f7ebc8; color: #725016; }
.priority-low { background: #e8edd8; color: #4f5e2f; }
.status-strip { align-items: stretch; display: grid; gap: 4mm; grid-template-columns: repeat(4, 1fr); margin: 5mm 0 6mm; }
.metric-card { background: #f5f7df; border: 1px solid #d8c8a7; border-radius: 8px; padding: 4mm; }
.metric-label { color: #7a684f; font-size: 8pt; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; }
.metric-value { color: #3f331f; font-size: 16pt; font-weight: 700; margin-top: 2mm; }
.metric-note { color: #7a684f; font-size: 8.5pt; margin-top: 1.5mm; }
.notice { border-left: 5px solid #9a6b20; background: #f7ebc8; border-radius: 7px; margin: 5mm 0 7mm; padding: 4mm 5mm; }
.notice strong { color: #684515; }
.coverage-grid { display: grid; gap: 5mm; grid-template-columns: 1fr 1fr; }
.coverage-box, .section-card, .appendix-card { background: #fffff5; border: 1px solid #d8c8a7; border-radius: 8px; padding: 4mm; }
.section-card { margin: 0 0 5mm; page-break-inside: avoid; }
.section-header { align-items: center; border-bottom: 1px solid #ded1b1; display: flex; justify-content: space-between; margin-bottom: 3mm; padding-bottom: 2mm; }
.section-meta { color: #7a684f; font-size: 8.8pt; margin-top: 1mm; }
.issue-pills { display: flex; gap: 2mm; margin: 3mm 0; }
.pill { background: #f5f7df; border: 1px solid #d8c8a7; border-radius: 999px; color: #4d4028; font-size: 8.3pt; padding: 2px 7px; }
.two-column { display: grid; gap: 5mm; grid-template-columns: 1fr 1fr; }
.finding-list { margin-top: 2mm; }
.finding-item { border-left: 3px solid #b7a267; margin: 0 0 3mm; padding-left: 3mm; }
.muted { color: #7a684f; }
.disclaimer { background: #f7ebc8; border: 1px solid #d8c8a7; border-left: 5px solid #9a6b20; border-radius: 8px; font-weight: 700; margin-top: 4mm; padding: 4mm; }
.page-break { page-break-before: always; }
</style>
</head>
<body>
<section class="cover">
  <div class="cover-kicker">School condition review</div>
  <h1>{{ view.title }}</h1>
  <p class="cover-subtitle">A simple summary of what was visible in the submitted inspection images. This is not a safety or compliance certificate.</p>
  <div class="cover-grid">
    <div class="cover-panel"><div class="cover-label">Report status</div><div class="cover-value">{{ view.report_status_label }}</div></div>
    <div class="cover-panel"><div class="cover-label">Evidence images</div><div class="cover-value">{{ view.total_images }}</div></div>
  </div>
  {% if view.cover_image_url %}<div class="cover-image"><img src="{{ view.cover_image_url }}" alt="School inspection report illustration"></div>{% endif %}
  <div class="cover-footer">{{ view.disclaimer }}</div>
</section>
<main>
<div class="report-header">
  <h1>{{ view.title }}</h1>
  <p class="meta-line">AI-assisted visual inspection summary | Deterministic status floor: {{ view.deterministic_status_floor_label }}</p>
</div>
<div class="status-strip">
  <div class="metric-card"><div class="metric-label">Report status</div><div class="metric-value">{{ view.report_status_label }}</div><div class="metric-note">Human review before decisions</div></div>
  <div class="metric-card"><div class="metric-label">Evidence</div><div class="metric-value">{{ view.total_images }}</div><div class="metric-note">Images represented in category packets</div></div>
  <div class="metric-card"><div class="metric-label">Not inspected</div><div class="metric-value">{{ view.not_inspected_categories|length }}</div><div class="metric-note">Configured categories without evidence</div></div>
</div>
{% if view.human_review_items and view.human_review_completed %}
<div class="notice"><strong>Human review completed.</strong> Human-review decisions were recorded before this final report was generated.</div>
{% elif view.provisional or view.human_review_items %}
<div class="notice"><strong>Human review required.</strong> This report is provisional and requires human review before decisions are made. Review-required category count: {{ view.human_review_items }}.</div>
{% else %}
<div class="notice"><strong>Review status.</strong> No automated human-review escalation was triggered. Qualified personnel must still review this report before decisions are made.</div>
{% endif %}
<h2>Executive Summary</h2>
<ul>{% for item in view.executive_summary %}<li>{{ item }}</li>{% else %}<li>None recorded.</li>{% endfor %}</ul>
<h2>Key Risks</h2>
<ul>{% for item in view.key_risks %}<li>{{ item }}</li>{% else %}<li>None recorded.</li>{% endfor %}</ul>
<h2>Category Coverage</h2>
<div class="coverage-box"><h3>Not inspected categories</h3><ul>{% for item in view.not_inspected_categories %}<li>{{ item }}</li>{% else %}<li>None recorded.</li>{% endfor %}</ul></div>
<h2>Scope and Inputs</h2>
<ul>{% for item in view.scope_and_inputs %}<li>{{ item }}</li>{% else %}<li>None recorded.</li>{% endfor %}</ul>
<h2>Source References</h2>
<ul>{% for item in view.source_files %}<li>{{ item }}</li>{% endfor %}</ul>
<h2>Category Summary Table</h2>
<table><thead><tr><th>Category</th><th>Status</th><th>Images</th><th>High</th><th>Medium</th><th>Low</th><th>Review Flag</th></tr></thead><tbody>
{% for row in view.category_table %}<tr><td><code>{{ row.category }}</code></td><td>{{ row.status }}</td><td>{{ row.image_count }}</td><td>{{ row.high }}</td><td>{{ row.medium }}</td><td>{{ row.low }}</td><td>{{ row.human_review }}</td></tr>{% endfor %}
</tbody></table>
<h2>Priority Actions</h2>
{% if view.priority_action_rows %}
<table><thead><tr><th>Priority</th><th>Category</th><th>Recommended action</th><th>Evidence IDs</th><th>Review Flag</th></tr></thead><tbody>
{% for row in view.priority_action_rows %}<tr><td><span class="badge {{ row.priority_class }}">{{ row.priority }}</span></td><td>{{ row.category }}</td><td>{{ row.action }}</td><td>{{ row.evidence }}</td><td>{{ row.review_required }}</td></tr>{% endfor %}
</tbody></table>
{% else %}<p class="muted">No priority action rows were recorded in the validated report content.</p>{% endif %}
<div class="two-column">
{% for group in view.global_action_groups %}
<div class="coverage-box"><h3>{{ group.label }}</h3><ul>{% for item in group.action_items %}<li>{{ item }}</li>{% else %}<li>None recorded.</li>{% endfor %}</ul></div>
{% endfor %}
</div>
<h2>Human Review Notes</h2><ul>{% for item in view.human_review_notes %}<li>{{ item }}</li>{% else %}<li>None recorded.</li>{% endfor %}</ul>
<h2>Human Review Decisions</h2>
<table><thead><tr><th>Category</th><th>Image</th><th>Status</th><th>Reviewer notes</th></tr></thead><tbody>
{% for row in view.human_review_decision_rows %}<tr><td>{{ row.category }}</td><td>{{ row.image_id }}</td><td>{{ row.status }}</td><td>{{ row.notes or "No reviewer notes." }}</td></tr>{% else %}<tr><td colspan="4">None recorded.</td></tr>{% endfor %}
</tbody></table>
<h2 class="page-break">Section-wise Findings</h2>
{% for section in view.category_sections %}
<section class="section-card">
  <div class="section-header">
    <div><h3>{{ section.category }}</h3><div class="section-meta">Images reviewed: {{ section.image_count }} | Human review required: {{ "Yes" if section.human_review_required else "No" }}</div></div>
    <div><span class="badge {{ section.status_class }}">{{ section.status_label }}</span> <span class="badge {{ section.priority_class }}">{{ section.priority_label }}</span></div>
  </div>
  <p>{{ section.summary }}</p>
  <div class="issue-pills"><span class="pill">High: {{ section.issue_counts.high }}</span><span class="pill">Medium: {{ section.issue_counts.medium }}</span><span class="pill">Low: {{ section.issue_counts.low }}</span></div>
  <div class="two-column">
    <div><strong>Key findings</strong><div class="finding-list">{% for finding in section.key_findings %}<div class="finding-item"><strong>{{ finding.severity }}</strong> - {{ finding.issue_type }}<br><span class="muted">{{ finding.evidence }}</span></div>{% else %}<p class="muted">None recorded.</p>{% endfor %}</div></div>
    <div><strong>Recommended actions</strong><ul>{% for item in section.recommended_actions %}<li>{{ item }}</li>{% else %}<li>None recorded.</li>{% endfor %}</ul><strong>Evidence references</strong><ul>{% for item in section.evidence_refs %}<li>{{ item }}</li>{% else %}<li>None recorded.</li>{% endfor %}</ul></div>
  </div>
  <strong>Documentation gaps</strong><ul>{% for gap in section.documentation_gaps %}<li>{{ gap.image_id }}: {{ gap.gap }}</li>{% else %}<li>None recorded.</li>{% endfor %}</ul>
</section>
{% endfor %}
<h2>Limitations and Disclaimer</h2>
<ul>{% for item in view.limitations %}<li>{{ item }}</li>{% else %}<li>None recorded.</li>{% endfor %}</ul>
<p class="disclaimer">{{ view.disclaimer }}</p>
<h2>Machine-Readable Appendix</h2>
<pre>{{ appendix_json }}</pre>
</main>
</body>
</html>
""".strip()


def render_report_html(content: FinalReportContent, metadata: dict, category_packets: list[dict]) -> str:
    """Render the final report as deterministic HTML for PDF conversion."""

    view = build_report_view_model(content, metadata, category_packets)

    environment = Environment(loader=BaseLoader(), autoescape=select_autoescape(default=True))
    template = environment.from_string(REPORT_HTML_TEMPLATE)
    return template.render(
        view=view,
        appendix_json=json.dumps(view["appendix"], indent=2, ensure_ascii=False),
    )


def reportlab_text(value: str) -> str:
    """Escape text for ReportLab Paragraph markup."""

    return html.escape(value or "")


def reportlab_bullet_list(items: list[str], styles: dict) -> list:
    """Convert text items into ReportLab bullet paragraphs."""

    from reportlab.platypus import Paragraph

    cleaned_items = clean_text_items(items)
    if not cleaned_items:
        cleaned_items = ["None recorded."]
    return [Paragraph("- " + reportlab_text(item), styles["BodyText"]) for item in cleaned_items]


def reportlab_col_widths(widths_mm: list[float]) -> list[float]:
    """Convert millimeter column widths into ReportLab points."""

    from reportlab.lib.units import mm

    return [width * mm for width in widths_mm]


def reportlab_table_rows(
    rows: list[list[object]],
    styles: dict,
    split_long_columns: set[int] | None = None,
) -> list[list[object]]:
    """Wrap table values in Paragraphs so long text cannot force page overflow."""

    from reportlab.platypus import Paragraph

    split_long_columns = split_long_columns or set()
    table_rows = []
    for row_index, row in enumerate(rows):
        paragraph_row = []
        for column_index, value in enumerate(row):
            if row_index == 0:
                style = styles["TableHeader"]
            elif column_index in split_long_columns:
                style = styles["TableCellLong"]
            else:
                style = styles["TableCell"]
            paragraph_row.append(Paragraph(reportlab_text(str(value)), style))
        table_rows.append(paragraph_row)
    return table_rows


def render_report_pdf_with_reportlab(
    content: FinalReportContent,
    metadata: dict,
    category_packets: list[dict],
    pdf_path: Path,
) -> None:
    """Render a deterministic PDF with ReportLab when WeasyPrint is unavailable."""

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    styles["Title"].fontName = "Times-Bold"
    styles["Title"].textColor = colors.HexColor("#3f331f")
    styles["BodyText"].fontName = "Helvetica"
    styles["BodyText"].fontSize = 9.8
    styles["BodyText"].textColor = colors.HexColor("#33291f")
    styles["BodyText"].leading = 13.2
    styles["BodyText"].spaceAfter = 3
    styles["BodyText"].wordWrap = "LTR"
    styles["BodyText"].splitLongWords = 0
    styles["Normal"].textColor = colors.HexColor("#33291f")
    styles["Normal"].wordWrap = "LTR"
    styles["Normal"].splitLongWords = 0
    styles["Heading2"].fontName = "Times-Bold"
    styles["Heading2"].textColor = colors.HexColor("#4f4f2a")
    styles["Heading2"].fontSize = 16
    styles["Heading2"].leading = 19
    styles["Heading2"].spaceBefore = 13
    styles["Heading2"].spaceAfter = 6
    styles["Heading2"].keepWithNext = 1
    styles["Heading3"].fontName = "Times-Bold"
    styles["Heading3"].textColor = colors.HexColor("#5b4a2e")
    styles["Heading3"].fontSize = 12
    styles["Heading3"].leading = 15
    styles["Heading3"].spaceBefore = 8
    styles["Heading3"].spaceAfter = 4
    styles["Heading3"].keepWithNext = 1
    styles["Heading4"].fontName = "Helvetica-BoldOblique"
    styles["Heading4"].textColor = colors.HexColor("#5b4a2e")
    styles["Heading4"].fontSize = 10
    styles["Heading4"].leading = 12.5
    styles["Heading4"].spaceBefore = 7
    styles["Heading4"].spaceAfter = 2
    styles["Heading4"].keepWithNext = 1
    styles.add(
        ParagraphStyle(
            name="CoverText",
            parent=styles["BodyText"],
            textColor=colors.HexColor("#f5e8c8"),
            fontSize=11,
            leading=15,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CoverKicker",
            parent=styles["BodyText"],
            fontName="Helvetica-Bold",
            textColor=colors.HexColor("#f0c76a"),
            fontSize=11,
            leading=13,
            spaceAfter=10,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CoverTitle",
            parent=styles["Title"],
            fontName="Times-Bold",
            textColor=colors.HexColor("#fff8e8"),
            fontSize=32,
            leading=36,
            spaceAfter=10,
            alignment=TA_LEFT,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CoverMetricLabel",
            parent=styles["BodyText"],
            fontName="Helvetica-Bold",
            textColor=colors.HexColor("#f4d58d"),
            fontSize=8.5,
            leading=10,
            spaceAfter=4,
            splitLongWords=0,
            wordWrap="LTR",
        )
    )
    styles.add(
        ParagraphStyle(
            name="CoverMetricValue",
            parent=styles["BodyText"],
            fontName="Helvetica-Bold",
            textColor=colors.HexColor("#fffaf0"),
            fontSize=12.5,
            leading=15.2,
            splitLongWords=0,
            wordWrap="LTR",
        )
    )
    styles.add(
        ParagraphStyle(
            name="TableHeader",
            parent=styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7.8,
            leading=9.4,
            textColor=colors.HexColor("#4d4028"),
            splitLongWords=0,
            wordWrap="LTR",
        )
    )
    styles.add(
        ParagraphStyle(
            name="TableCell",
            parent=styles["BodyText"],
            fontSize=8,
            leading=10.2,
            textColor=colors.HexColor("#33291f"),
            splitLongWords=0,
            wordWrap="LTR",
        )
    )
    styles.add(
        ParagraphStyle(
            name="TableCellLong",
            parent=styles["TableCell"],
            splitLongWords=1,
            wordWrap="LTR",
        )
    )
    view = build_report_view_model(content, metadata, category_packets)

    story = [
        Spacer(1, 7 * mm),
        Paragraph("SCHOOL CONDITION REVIEW", styles["CoverKicker"]),
        Paragraph(reportlab_text(content.title), styles["CoverTitle"]),
        Paragraph(
            "A simple summary of what was visible in the submitted inspection images. "
            "This is not a safety or compliance certificate.",
            styles["CoverText"],
        ),
        Spacer(1, 7 * mm),
        Table(
            [
                [
                    [
                        Paragraph("REPORT STATUS", styles["CoverMetricLabel"]),
                        Paragraph(reportlab_text(view["report_status_label"]), styles["CoverMetricValue"]),
                    ],
                    [
                        Paragraph("EVIDENCE IMAGES", styles["CoverMetricLabel"]),
                        Paragraph(str(view["total_images"]), styles["CoverMetricValue"]),
                    ],
                ],
            ],
            colWidths=[118 * mm, 50 * mm],
            hAlign="LEFT",
            style=[
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#4a4729")),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#938a68")),
                ("INNERGRID", (0, 0), (-1, -1), 0.8, colors.HexColor("#938a68")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ],
        ),
        Spacer(1, 7 * mm),
    ]

    cover_image_path = Path(str(metadata.get("cover_image_path", "")))
    if cover_image_path.is_file():
        cover_image = Image(str(cover_image_path))
        cover_image_padding = 4
        cover_image._restrictSize(140 * mm, 99 * mm)
        cover_image_table = Table(
            [[cover_image]],
            colWidths=[cover_image.drawWidth + 2 * cover_image_padding],
            hAlign="CENTER",
            style=[
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#3c2c1f")),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#938a68")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), cover_image_padding),
                ("RIGHTPADDING", (0, 0), (-1, -1), cover_image_padding),
                ("TOPPADDING", (0, 0), (-1, -1), cover_image_padding),
                ("BOTTOMPADDING", (0, 0), (-1, -1), cover_image_padding),
            ],
        )
        story.extend([cover_image_table, Spacer(1, 8 * mm)])

    story.extend(
        [
            Paragraph(reportlab_text(content.disclaimer), styles["CoverText"]),
            PageBreak(),
            Paragraph("Overall Verdict", styles["Heading2"]),
            Paragraph(f"Provisional: {'Yes' if content.provisional else 'No'}", styles["BodyText"]),
            Paragraph(
                f"Deterministic status floor: {reportlab_text(view['deterministic_status_floor_label'])}",
                styles["BodyText"],
            ),
        ]
    )

    if view["human_review_items"] and view["human_review_completed"]:
        story.append(
            Paragraph(
                "Human review was completed before this final report was generated.",
                styles["BodyText"],
            )
        )
    elif content.provisional or view["human_review_items"]:
        story.append(
            Paragraph(
                "Human review required. This report is provisional and requires human review before decisions are made.",
                styles["BodyText"],
            )
        )
    else:
        story.append(
            Paragraph(
                "No automated human-review escalation was triggered. Qualified personnel must still review this report before decisions are made.",
                styles["BodyText"],
            )
        )

    story.extend(
        [
            Paragraph("Executive Summary", styles["Heading2"]),
            *reportlab_bullet_list(content.executive_summary, styles),
            Paragraph("Key Risks", styles["Heading2"]),
            *reportlab_bullet_list(view["key_risks"], styles),
            Paragraph("Category Coverage", styles["Heading2"]),
            Paragraph("Not inspected categories", styles["Heading3"]),
            *reportlab_bullet_list(view["not_inspected_categories"], styles),
            Paragraph("Scope and Inputs", styles["Heading2"]),
            *reportlab_bullet_list(content.scope_and_inputs, styles),
            Paragraph("Source References", styles["Heading2"]),
            *reportlab_bullet_list(view["source_files"], styles),
        ]
    )

    table_rows = [["Category", "Status", "Images", "High", "Medium", "Low", "Review Flag"]]
    for row in build_category_table_rows(content, category_packets):
        table_rows.append(
            [
                row["category"],
                row["status"],
                str(row["image_count"]),
                str(row["high"]),
                str(row["medium"]),
                str(row["low"]),
                row["human_review"],
            ]
        )

    story.append(Paragraph("Category Summary Table", styles["Heading2"]))
    table = Table(
        reportlab_table_rows(table_rows, styles),
        colWidths=reportlab_col_widths(REPORTLAB_CATEGORY_TABLE_WIDTHS_MM),
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#efe4c8")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d8c8a7")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.extend([table, Spacer(1, 4 * mm)])

    if view["priority_action_rows"]:
        priority_rows = [["Priority", "Category", "Recommended Action", "Evidence IDs", "Review Flag"]]
        for row in view["priority_action_rows"]:
            priority_rows.append(
                [
                    row["priority"],
                    row["category"],
                    row["action"],
                    row["evidence"],
                    row["review_required"],
                ]
            )
        story.append(Paragraph("Priority Actions", styles["Heading2"]))
        priority_table = Table(
            reportlab_table_rows(priority_rows, styles, split_long_columns={3}),
            colWidths=reportlab_col_widths(REPORTLAB_PRIORITY_TABLE_WIDTHS_MM),
            repeatRows=1,
        )
        priority_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#efe4c8")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d8c8a7")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.extend([priority_table, Spacer(1, 4 * mm)])

    for heading, items in [
        ("Immediate Actions", content.immediate_actions),
        ("Maintenance Actions", content.maintenance_actions),
        ("Documentation Follow-ups", content.documentation_followups),
        ("Human Review Notes", content.human_review_notes),
    ]:
        story.append(Paragraph(heading, styles["Heading2"]))
        story.extend(reportlab_bullet_list(items, styles))

    story.append(Paragraph("Human Review Decisions", styles["Heading2"]))
    story.extend(
        reportlab_bullet_list(
            [
                f"{row['category']} / {row['image_id']}: {row['status']} - {row['notes'] or 'No reviewer notes.'}"
                for row in view["human_review_decision_rows"]
            ],
            styles,
        )
    )

    story.append(Paragraph("Category-by-Category Findings", styles["Heading2"]))
    for section in content.category_sections:
        view_section = next(item for item in view["category_sections"] if item["category"] == section.category)
        story.extend(
            [
                Paragraph(reportlab_text(section.category), styles["Heading3"]),
                Paragraph(f"Status: {reportlab_text(section.status)}", styles["BodyText"]),
                Paragraph(f"Priority: {reportlab_text(section.priority)}", styles["BodyText"]),
                Paragraph(reportlab_text(section.summary), styles["BodyText"]),
                Paragraph("Evidence references", styles["Heading4"]),
                *reportlab_bullet_list(view_section["evidence_refs"], styles),
                Paragraph("Recommended actions", styles["Heading4"]),
                *reportlab_bullet_list(section.recommended_actions, styles),
            ]
        )

    story.append(Paragraph("Limitations and Disclaimer", styles["Heading2"]))
    story.extend(reportlab_bullet_list(view["limitations"], styles))
    story.append(Paragraph(reportlab_text(content.disclaimer), styles["BodyText"]))
    story.append(Paragraph("Machine-Readable Appendix", styles["Heading2"]))
    story.append(
        Paragraph(
            reportlab_text(json.dumps(view["appendix"], indent=2, ensure_ascii=False)).replace(
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

    def draw_cover_background(canvas, _document) -> None:
        canvas.saveState()
        page_width, page_height = A4
        canvas.setFillColor(colors.HexColor("#4f5330"))
        canvas.rect(0, 0, page_width, page_height, stroke=0, fill=1)
        canvas.setFillColor(colors.HexColor("#3c2c1f"))
        canvas.rect(0, 0, 86 * mm, page_height, stroke=0, fill=1)
        canvas.setFillColor(colors.HexColor("#70621f"))
        canvas.rect(86 * mm, 0, page_width - 86 * mm, page_height, stroke=0, fill=1)
        canvas.setFillColor(colors.Color(1, 1, 1, alpha=0.06))
        canvas.rect(0, 0, page_width, 42 * mm, stroke=0, fill=1)
        canvas.restoreState()

    def draw_page_background(canvas, _document) -> None:
        canvas.saveState()
        page_width, page_height = A4
        canvas.setFillColor(colors.HexColor("#fbfcee"))
        canvas.rect(0, 0, page_width, page_height, stroke=0, fill=1)
        canvas.setFillColor(colors.HexColor("#7a684f"))
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(page_width - 20 * mm, 11 * mm, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()

    document.build(story, onFirstPage=draw_cover_background, onLaterPages=draw_page_background)


def render_report_pdf(
    html_text: str,
    pdf_path: Path,
    content: FinalReportContent,
    metadata: dict,
    category_packets: list[dict],
) -> str:
    """Render the final PDF with ReportLab by default.

    WeasyPrint needs native GTK/Pango/GObject libraries on macOS. Keeping
    ReportLab as the default avoids local system installs while preserving PDF
    output. Set SCHOOL_VALIDATOR_PDF_RENDERER=weasyprint to opt into WeasyPrint.
    """

    if os.getenv("SCHOOL_VALIDATOR_PDF_RENDERER", "reportlab").strip().lower() != "weasyprint":
        render_report_pdf_with_reportlab(content, metadata, category_packets, pdf_path)
        return "reportlab"

    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            from weasyprint import HTML

        HTML(string=html_text, base_url=str(Path.cwd())).write_pdf(pdf_path)
        return "weasyprint"
    except Exception as error:
        logger.warning("WeasyPrint PDF rendering failed; using ReportLab fallback: %s", str(error)[:500])
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

    metadata["key_risks"] = payload.get("validated_final_verdict", {}).get("key_risks", [])
    markdown_text = render_report_markdown(content, metadata, category_packets)
    html_text = render_report_html(content, metadata, category_packets)
    paths["markdown_report"].write_text(markdown_text, encoding="utf-8")
    paths["html_report"].write_text(html_text, encoding="utf-8")
    paths["report_content_json"].write_text(content.model_dump_json(indent=2), encoding="utf-8")
    paths["report_generation_payload"].write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    metadata["pdf_renderer"] = render_report_pdf(html_text, paths["pdf_report"], content, metadata, category_packets)

    validate_rendered_report(content, paths, category_packets, global_rollup)
    return paths
