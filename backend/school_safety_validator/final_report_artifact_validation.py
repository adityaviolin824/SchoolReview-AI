"""Validation checks for final rendered report artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from pypdf import PdfReader

from .inspection_data_models import FinalReportContent


def normalize_report_text(value: str) -> str:
    """Normalize extracted report text for stable containment checks."""

    return " ".join(value.lower().split())


def validate_rendered_report(
    content: FinalReportContent,
    paths: dict[str, Path],
    category_packets: list[dict],
    global_rollup: dict,
) -> None:
    """Validate saved Markdown, HTML, JSON, and PDF artifacts."""

    for label in ["markdown_report", "html_report", "report_content_json", "report_generation_payload"]:
        path = paths[label]
        if not path.exists() or path.stat().st_size == 0:
            raise ValueError(f"Rendered report artifact is missing or empty: {label} -> {path}")

    pdf_path = paths["pdf_report"]
    if not pdf_path.exists() or pdf_path.stat().st_size == 0:
        raise ValueError(f"Rendered PDF report is missing or empty: {pdf_path}")

    saved_content = json.loads(paths["report_content_json"].read_text(encoding="utf-8"))
    if saved_content != content.model_dump(mode="json"):
        raise ValueError("Saved report content JSON does not match validated FinalReportContent.")

    reader = PdfReader(str(pdf_path))
    if len(reader.pages) < 1:
        raise ValueError("Rendered PDF has no pages.")

    pdf_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    pdf_text_normalized = normalize_report_text(pdf_text)
    required_terms = [content.overall_status, content.disclaimer]
    required_terms.extend(packet["category"] for packet in category_packets)
    required_terms.extend(global_rollup.get("not_inspected_categories", []))

    for term in required_terms:
        if term and normalize_report_text(term) not in pdf_text_normalized:
            raise ValueError(f"Rendered PDF is missing required text: {term}")

    if content.provisional and not (
        "provisional" in pdf_text_normalized or "human review" in pdf_text_normalized
    ):
        raise ValueError("Rendered PDF does not mention provisional or human review status.")
