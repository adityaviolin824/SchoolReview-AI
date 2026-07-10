"""End-to-end School Safety Validator pipeline entry point."""

from __future__ import annotations

import asyncio
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.tracers.langchain import wait_for_all_tracers
from langsmith import tracing_context

from .all_categories_inspection_runner import run_all_category_inspections
from .final_report_content_generation import run_final_report_generation
from .inspection_data_models import (
    PipelineExecutionOptions,
    SchoolInspectionRequest,
    SchoolInspectionResult,
)
from .inspection_file_paths import SUPPORTED_IMAGE_EXTENSIONS
from .logging_config import logging
from .inspection_runtime_settings import CATEGORY_NAMES, get_settings
from .vision_model_provider_clients import ModelClients


logger = logging.getLogger(__name__)


def resolve_path_from_base(path: Path, base_dir: Path) -> Path:
    """Resolve relative request paths against a known base directory."""

    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def load_school_inspection_request_json(
    request_json_path: Path,
    base_dir: Path | None = None,
) -> SchoolInspectionRequest:
    """Load a request JSON file and resolve image paths relative to it."""

    request_json_path = request_json_path.resolve()
    data = json.loads(request_json_path.read_text(encoding="utf-8"))
    request = SchoolInspectionRequest.model_validate(data)
    return resolve_request_image_paths(request, base_dir or request_json_path.parent)


def resolve_request_image_paths(
    request: SchoolInspectionRequest,
    base_dir: Path,
) -> SchoolInspectionRequest:
    """Return a copy of the request with absolute image paths."""

    resolved_sections = []
    for section in request.sections:
        resolved_images = [
            image.model_copy(update={"image_path": resolve_path_from_base(image.image_path, base_dir)})
            for image in section.images
        ]
        resolved_sections.append(section.model_copy(update={"images": resolved_images}))
    return request.model_copy(update={"sections": resolved_sections})


def normalize_execution_options(options: PipelineExecutionOptions) -> PipelineExecutionOptions:
    """Resolve generated-output paths without relying on process cwd later."""

    base_output_root = options.output_root.resolve()
    run_id = options.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_root = base_output_root / run_id
    materialized_input_root = (
        options.materialized_input_root.resolve()
        if options.materialized_input_root
        else output_root / "pipeline_inputs"
    )
    return options.model_copy(
        update={
            "output_root": output_root,
            "materialized_input_root": materialized_input_root,
            "run_id": run_id,
        }
    )


def validate_request_sections(request: SchoolInspectionRequest) -> list[str]:
    """Validate section names against configured backend categories."""

    section_names = [section.section_name.strip() for section in request.sections]
    duplicate_sections = sorted({name for name in section_names if section_names.count(name) > 1})
    unknown_sections = sorted(set(section_names) - set(CATEGORY_NAMES))

    if duplicate_sections:
        raise ValueError(f"Duplicate section_name values are not allowed: {duplicate_sections}")
    if unknown_sections:
        raise ValueError(f"Unknown section_name values: {unknown_sections}. Expected one of: {CATEGORY_NAMES}")
    return section_names


def unique_destination_name(source_path: Path, used_names: set[str]) -> str:
    """Choose a stable non-colliding filename for materialized images."""

    candidate = source_path.name
    if candidate not in used_names:
        used_names.add(candidate)
        return candidate

    index = 2
    while True:
        candidate = f"{source_path.stem}_{index}{source_path.suffix}"
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate
        index += 1


def materialize_request_dataset(
    request: SchoolInspectionRequest,
    input_root: Path,
) -> list[str]:
    """Copy request images/comments into the folder shape expected by runners."""

    validate_request_sections(request)
    warnings = []
    input_root.mkdir(parents=True, exist_ok=True)

    for section in request.sections:
        section_name = section.section_name.strip()
        images_root = input_root / section_name / "images"
        comments_root = input_root / section_name / "comments"
        images_root.mkdir(parents=True, exist_ok=True)
        comments_root.mkdir(parents=True, exist_ok=True)
        (comments_root / "overall_comments.txt").write_text(section.section_comment.strip(), encoding="utf-8")

        if not section.images:
            warnings.append(f"Section '{section_name}' has no images and will be marked as insufficient evidence.")
            continue

        used_names: set[str] = set()
        for image in section.images:
            source_path = image.image_path
            if not source_path.exists():
                raise FileNotFoundError(f"Image file does not exist: {source_path}")
            if not source_path.is_file():
                raise ValueError(f"Image path is not a file: {source_path}")
            if source_path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
                raise ValueError(
                    f"Unsupported image extension for {source_path}. "
                    f"Supported extensions: {sorted(SUPPORTED_IMAGE_EXTENSIONS)}"
                )

            destination_name = unique_destination_name(source_path, used_names)
            destination_path = images_root / destination_name
            shutil.copy2(source_path, destination_path)
            (comments_root / f"{destination_path.stem}.txt").write_text(image.comment.strip(), encoding="utf-8")

    return warnings


def build_artifact_paths(
    options: PipelineExecutionOptions,
    run_summary: dict,
    report_result: dict | None,
) -> dict[str, str]:
    """Collect important generated paths for the structured pipeline result."""

    artifact_paths = {
        "run_id": options.run_id or "",
        "output_root": str(options.output_root),
        "materialized_input_root": str(options.materialized_input_root),
    }
    if run_summary.get("saved_run_summary_file"):
        artifact_paths["run_summary"] = run_summary["saved_run_summary_file"]

    for category_name, output_file in run_summary.get("saved_category_output_files", {}).items():
        artifact_paths[f"category_output:{category_name}"] = str(output_file)

    if report_result:
        for label, path in report_result["aggregation"]["paths"].items():
            artifact_paths[f"final_aggregation:{label}"] = str(path)
        for label, path in report_result["report_paths"].items():
            artifact_paths[f"final_report:{label}"] = str(path)

    return artifact_paths


def build_pipeline_result(
    request: SchoolInspectionRequest,
    options: PipelineExecutionOptions,
    run_summary: dict,
    report_result: dict | None,
    warnings: list[str],
    errors: list[str] | None = None,
) -> SchoolInspectionResult:
    """Create the structured result returned by the pipeline entry point."""

    errors = errors or []
    aggregation = report_result["aggregation"] if report_result else None
    global_rollup = aggregation["global_rollup"] if aggregation else {}
    final_report = aggregation["final_report"] if aggregation else None
    failed_sections = run_summary.get("failed_categories", [])
    human_review_items = run_summary.get("all_human_review_queue", [])
    human_review_required = bool(human_review_items or failed_sections or global_rollup.get("human_review_required"))
    total_images = global_rollup.get("total_images")
    if total_images is None:
        total_images = sum(
            summary.get("image_count", 0) for summary in run_summary.get("category_summaries", {}).values()
        )

    pipeline_status = "failed" if errors else "completed"
    if pipeline_status == "completed" and human_review_required:
        pipeline_status = "completed_with_human_review_required"

    return SchoolInspectionResult(
        school=request.school,
        pipeline_status=pipeline_status,
        overall_status=final_report.overall_status if final_report else None,
        provisional=final_report.provisional if final_report else None,
        processed_sections=global_rollup.get("processed_categories", run_summary.get("processed_categories", [])),
        failed_sections=failed_sections,
        not_inspected_sections=global_rollup.get(
            "not_inspected_categories",
            run_summary.get("not_inspected_categories", []),
        ),
        total_images=total_images,
        human_review_required=human_review_required,
        human_review_items=human_review_items,
        category_summaries=run_summary.get("category_summaries", {}),
        run_summary=run_summary,
        artifact_paths=build_artifact_paths(options, run_summary, report_result),
        warnings=warnings,
        errors=errors,
    )


def build_failed_pipeline_result(
    request: SchoolInspectionRequest,
    options: PipelineExecutionOptions,
    run_summary: dict,
    warnings: list[str],
    error: Exception,
) -> SchoolInspectionResult:
    """Return a structured failure without hiding the root error."""

    return build_pipeline_result(
        request=request,
        options=options,
        run_summary=run_summary,
        report_result=None,
        warnings=warnings,
        errors=[f"{type(error).__name__}: {error}"],
    )


async def run_school_safety_pipeline_async(
    request: SchoolInspectionRequest,
    options: PipelineExecutionOptions,
    clients: ModelClients | None = None,
    openai_client: object | None = None,
) -> SchoolInspectionResult:
    """Run image assessment, category summaries, final aggregation, and reports."""

    options = normalize_execution_options(options)
    run_summary: dict = {}
    warnings: list[str] = []

    try:
        logger.info("Starting school safety pipeline for %s.", request.school.name)
        warnings.extend(materialize_request_dataset(request, options.materialized_input_root))
        settings = get_settings(
            input_root=options.materialized_input_root,
            output_root=options.output_root,
        )
        section_names = validate_request_sections(request)
        model_clients = clients or ModelClients.from_env(settings)

        with tracing_context(enabled=settings.langsmith_tracing, project_name=settings.langsmith_project):
            run_summary = await run_all_category_inspections(section_names, settings, model_clients)
            report_result = None
            if options.generate_report:
                report_result = run_final_report_generation(
                    settings=settings,
                    openai_client=openai_client or model_clients.openai_client,
                    full_run_state=run_summary,
                )
        return build_pipeline_result(request, options, run_summary, report_result, warnings)
    except Exception as error:
        logger.exception("School safety pipeline failed: %s", error)
        return build_failed_pipeline_result(request, options, run_summary, warnings, error)
    finally:
        wait_for_all_tracers()


def run_school_safety_pipeline(
    request: SchoolInspectionRequest,
    options: PipelineExecutionOptions,
    clients: ModelClients | None = None,
    openai_client: object | None = None,
) -> SchoolInspectionResult:
    """Synchronous wrapper for local scripts and sync FastAPI routes."""

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(run_school_safety_pipeline_async(request, options, clients, openai_client))
    raise RuntimeError("Use run_school_safety_pipeline_async from an active event loop.")
