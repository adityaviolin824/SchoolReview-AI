"""Final report-content LLM call and orchestration."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .final_report_artifact_rendering import find_report_cover_image, save_final_report_outputs
from .final_verdict_aggregation import final_report_output_root, run_final_aggregation
from .inspection_data_models import FinalInspectionLLMReport, FinalReportContent
from .inspection_runtime_settings import ValidatorSettings, get_settings
from .structured_model_response_parsing import parse_openai_structured_response
from .vision_model_provider_clients import create_openai_client_from_env


REPORT_DISCLAIMER = (
    "This AI-assisted visual inspection summary does not certify safety, compliance, "
    "structural soundness, electrical safety, or serviceability. It must be reviewed "
    "by qualified personnel before decisions are made."
)

REPORT_GENERATION_SYSTEM_PROMPT = f"""
You are a careful content writer for a school inspection workflow.
Create structured report content only. Do not create Markdown, HTML, or layout.
Keep the verdict cautious and evidence-bound. Do not add unsupported claims.
Use exactly one category section for each processed category and no other categories.
Use this exact disclaimer: {REPORT_DISCLAIMER}
Return structured JSON that matches the requested schema exactly.
""".strip()


def build_report_generation_payload(
    final_report: FinalInspectionLLMReport,
    category_packets: list[dict],
    global_rollup: dict,
    source_files: list[dict],
) -> dict:
    """Create the report-content payload from validated aggregation output."""

    return {
        "task": "Create structured report content from the validated school inspection verdict.",
        "rules": [
            "Use only the supplied JSON.",
            "Do not change the overall_status, provisional flag, counts, categories, or action priorities.",
            "Do not invent new evidence, defects, measurements, or certifications.",
            "Return content only; layout will be rendered by deterministic code.",
            "category_sections must contain exactly one entry for every processed category and no other categories.",
            f"Use this exact disclaimer: {REPORT_DISCLAIMER}",
        ],
        "validated_final_verdict": final_report.model_dump(mode="json"),
        "global_rollup": global_rollup,
        "source_files": source_files,
        "categories": category_packets,
    }


def validate_final_report_content(
    content: FinalReportContent,
    final_report: FinalInspectionLLMReport,
    category_packets: list[dict],
    global_rollup: dict,
) -> FinalReportContent:
    """Validate structured report content before rendering any files."""

    if content.overall_status != final_report.overall_status:
        raise ValueError("Report content changed the validated overall_status.")
    if content.provisional != final_report.provisional:
        raise ValueError("Report content changed the validated provisional flag.")

    expected_categories = {packet["category"] for packet in category_packets}
    reported_categories = [section.category for section in content.category_sections]
    reported_category_set = set(reported_categories)
    duplicate_categories = sorted({value for value in reported_categories if reported_categories.count(value) > 1})
    unknown_categories = sorted(reported_category_set - expected_categories)
    missing_categories = sorted(expected_categories - reported_category_set)

    if duplicate_categories:
        raise ValueError(f"Report content has duplicate category sections: {duplicate_categories}")
    if unknown_categories:
        raise ValueError(f"Report content invented category sections: {unknown_categories}")
    if missing_categories:
        raise ValueError(f"Report content omitted category sections: {missing_categories}")

    limitation_text = "\n".join(content.limitations).lower()
    missing_not_inspected = [
        category_name
        for category_name in global_rollup.get("not_inspected_categories", [])
        if category_name.lower() not in limitation_text
    ]
    if missing_not_inspected:
        raise ValueError(f"Report content omitted not-inspected categories: {missing_not_inspected}")
    if REPORT_DISCLAIMER != content.disclaimer:
        raise ValueError("Report content did not preserve the required disclaimer exactly.")

    return content


def build_report_metadata(
    settings: ValidatorSettings,
    source_files: list[dict],
    global_rollup: dict,
    aggregation_paths: dict[str, Path],
) -> dict:
    """Collect deterministic metadata used by renderers and appendices."""

    output_root = final_report_output_root(settings)
    cover_image_path = find_report_cover_image()
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "final_aggregation_json_path": str(aggregation_paths["final_aggregation_output"]),
        "report_content_json_path": str(output_root / "school_safety_final_report_content.json"),
        "cover_image_path": str(cover_image_path) if cover_image_path else "",
        "category_output_sources": source_files,
        "models": {
            "primary_vlm_model": settings.primary_vlm_model,
            "backup_vlm_model": settings.backup_vlm_model,
            "escalation_review_model": settings.escalation_review_model,
            "final_aggregation_model": settings.final_aggregation_model,
            "final_report_model": settings.final_report_model,
        },
        "processed_categories": global_rollup["processed_categories"],
        "not_inspected_categories": global_rollup["not_inspected_categories"],
        "total_images": global_rollup["total_images"],
        "deterministic_status_floor": global_rollup["deterministic_status_floor"],
    }


def run_final_report_generation(
    settings: ValidatorSettings | None = None,
    openai_client: object | None = None,
    aggregation_result: dict | None = None,
    full_run_state: dict | None = None,
) -> dict:
    """Run final aggregation, report-content generation, and artifact rendering."""

    settings = settings or get_settings()
    openai_client = openai_client or create_openai_client_from_env()
    aggregation_result = aggregation_result or run_final_aggregation(settings, openai_client, full_run_state)
    final_report = aggregation_result["final_report"]
    category_packets = aggregation_result["category_packets"]
    global_rollup = aggregation_result["global_rollup"]
    source_files = aggregation_result["source_files"]

    payload = build_report_generation_payload(final_report, category_packets, global_rollup, source_files)
    response = parse_openai_structured_response(
        openai_client,
        model=settings.final_report_model,
        input=[
            {
                "role": "system",
                "content": [{"type": "input_text", "text": REPORT_GENERATION_SYSTEM_PROMPT}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": json.dumps(payload, indent=2, ensure_ascii=False)}],
            },
        ],
        text_format=FinalReportContent,
    )
    raw_content = response.output_parsed
    content = validate_final_report_content(raw_content, final_report, category_packets, global_rollup)
    metadata = build_report_metadata(settings, source_files, global_rollup, aggregation_result["paths"])
    report_paths = save_final_report_outputs(content, payload, metadata, category_packets, global_rollup, settings)

    return {
        "aggregation": aggregation_result,
        "report_content": content,
        "report_generation_payload": payload,
        "report_metadata": metadata,
        "report_paths": report_paths,
    }


def main() -> None:
    """CLI entrypoint for final report generation from existing category outputs."""

    parser = argparse.ArgumentParser(description="Run final aggregation and generate report artifacts.")
    parser.add_argument("--output-root", type=Path, default=None, help="Generated output root.")
    args = parser.parse_args()
    settings = get_settings(output_root=args.output_root)
    result = run_final_report_generation(settings)
    print("Overall status:", result["aggregation"]["final_report"].overall_status)
    print("Saved final report files:")
    for label, path in result["report_paths"].items():
        print(f"- {label}: {path}")


if __name__ == "__main__":
    main()
