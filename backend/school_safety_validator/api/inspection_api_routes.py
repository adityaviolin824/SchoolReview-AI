"""Minimal FastAPI routes for testing the School Safety Validator pipeline."""

from __future__ import annotations

import copy
import io
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError

from school_safety_validator.inspection_data_models import (
    InspectionImageInput,
    InspectionSectionInput,
    PipelineExecutionOptions,
    SchoolInspectionRequest,
    SchoolInspectionResult,
)
from school_safety_validator.inspection_file_paths import SUPPORTED_IMAGE_EXTENSIONS
from school_safety_validator.inspection_runtime_settings import BACKEND_ROOT, CATEGORY_NAMES
from school_safety_validator.logging_config import logging
from school_safety_validator.pipeline import build_artifact_paths, run_school_safety_pipeline
from school_safety_validator.final_report_content_generation import run_final_report_generation
from school_safety_validator.inspection_runtime_settings import get_settings

from .inspection_api_models import (
    ApiRunStatus,
    CategorySummaryResponse,
    FinalizeInspectionReportResponse,
    HealthResponse,
    HumanReviewApiItem,
    HumanReviewDecisionRequest,
    HumanReviewDecisionResponse,
    HumanReviewFindingSummary,
    HumanReviewModelSummary,
    InputStatusResponse,
    InspectionRunCreateRequest,
    InspectionRunCreateResponse,
    InspectionRunStatusResponse,
    RunProgressResponse,
    SectionInputStatusResponse,
    StartInspectionRunRequest,
    StartInspectionRunResponse,
    UploadedImageResponse,
)


router = APIRouter()
logger = logging.getLogger(__name__)

API_OUTPUT_ROOT = BACKEND_ROOT.parent / "runs" / "api_runs"
RUN_RETENTION_SECONDS = 24 * 60 * 60
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
IMAGE_CONTENT_TYPES = {
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
}


@dataclass
class StagedImage:
    """One image staged through the API upload boundary."""

    image_id: str
    original_filename: str
    staged_path: Path
    comment: str


@dataclass
class InspectionRunRecord:
    """In-memory run state for the simple test API."""

    run_id: str
    request: InspectionRunCreateRequest
    status: ApiRunStatus = "created"
    staged_images: dict[str, list[StagedImage]] = field(default_factory=dict)
    result: SchoolInspectionResult | None = None
    human_review_decisions: dict[str, HumanReviewDecisionRequest] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


RUNS: dict[str, InspectionRunRecord] = {}
PIPELINE_LOCK = threading.Lock()


def cleanup_old_api_runs(max_age_seconds: int = RUN_RETENTION_SECONDS, now: float | None = None) -> list[Path]:
    """Delete stale immediate run folders from the controlled API output root."""

    deleted_paths: list[Path] = []
    current_time = time.time() if now is None else now
    API_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    resolved_root = API_OUTPUT_ROOT.resolve()

    for child in API_OUTPUT_ROOT.iterdir():
        if child.is_symlink() or not child.is_dir():
            continue
        if child.parent.resolve() != resolved_root:
            continue
        if current_time - child.stat().st_mtime <= max_age_seconds:
            continue

        shutil.rmtree(child)
        deleted_paths.append(child)
        logger.info("Deleted stale API run folder: %s", child.name)

    return deleted_paths


def validate_section_names(section_names: list[str]) -> None:
    """Reject duplicate or unknown inspection section names."""

    duplicate_sections = sorted({name for name in section_names if section_names.count(name) > 1})
    unknown_sections = sorted(set(section_names) - set(CATEGORY_NAMES))
    if duplicate_sections:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Duplicate section_name values: {duplicate_sections}")
    if unknown_sections:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unknown section_name values: {unknown_sections}. Expected one of: {CATEGORY_NAMES}",
        )


def get_run_record(run_id: str) -> InspectionRunRecord:
    """Return a run record or raise a controlled 404."""

    record = RUNS.get(run_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Inspection run was not found.")
    return record


def run_root(run_id: str) -> Path:
    """Return the controlled root folder for one API run."""

    return API_OUTPUT_ROOT / run_id


def upload_root(run_id: str, section_name: str) -> Path:
    """Return the controlled upload folder for one run section."""

    return run_root(run_id) / "uploads" / section_name


def selected_section_names(record: InspectionRunRecord) -> list[str]:
    """Return section names selected for this API run."""

    return [section.section_name for section in record.request.sections]


def build_input_status(record: InspectionRunRecord) -> InputStatusResponse:
    """Return upload readiness for the selected run sections."""

    sections = {}
    missing_sections = []
    for section_name in selected_section_names(record):
        image_count = len(record.staged_images.get(section_name, []))
        ready = image_count > 0
        if not ready:
            missing_sections.append(section_name)
        sections[section_name] = SectionInputStatusResponse(
            selected=True,
            image_count=image_count,
            ready=ready,
        )

    return InputStatusResponse(
        can_start=record.status == "created" and not missing_sections,
        missing_image_sections=missing_sections,
        sections=sections,
    )


def build_progress_response(record: InspectionRunRecord, input_status: InputStatusResponse) -> RunProgressResponse:
    """Return a concise dashboard message for the current run phase."""

    if record.status == "created":
        if input_status.missing_image_sections:
            missing = ", ".join(input_status.missing_image_sections)
            return RunProgressResponse(
                phase=record.status,
                message=f"Upload at least one image for: {missing}.",
            )
        return RunProgressResponse(phase=record.status, message="Inputs are ready. Start assessment when ready.")
    if record.status == "running":
        return RunProgressResponse(phase=record.status, message="Assessment is running.")
    if record.status == "awaiting_human_review":
        return RunProgressResponse(phase=record.status, message="Assessment complete. Human review required.")
    if record.status == "ready_for_report":
        if review_items_for_record(record):
            message = "Human review complete. Ready to generate final report."
        else:
            message = "Assessment complete. Ready to generate final report."
        return RunProgressResponse(phase=record.status, message=message)
    if record.status == "finalizing_report":
        return RunProgressResponse(phase=record.status, message="Final report is being generated.")
    if record.status == "completed":
        return RunProgressResponse(phase=record.status, message="Final report ready.")
    if record.status == "failed":
        return RunProgressResponse(phase=record.status, message="Run failed. Check errors.")
    return RunProgressResponse(phase=record.status, message=record.status)


def find_human_review_item(record: InspectionRunRecord, review_id: str) -> dict | None:
    """Return one raw human-review item for a run."""

    review_items = record.result.human_review_items if record.result else []
    for item in review_items:
        if str(item.get("review_id", "")) == review_id:
            return item
    return None


def safe_human_review_image_path(record: InspectionRunRecord, item: dict) -> Path | None:
    """Return a review image path only when it stays inside this run root."""

    raw_image_path = str(item.get("raw_image_path", "")).strip()
    if not raw_image_path:
        return None

    image_path = Path(raw_image_path).resolve()
    resolved_run_root = run_root(record.run_id).resolve()
    if not image_path.is_relative_to(resolved_run_root):
        return None
    if image_path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
        return None
    if not image_path.is_file():
        return None
    return image_path


def review_items_for_record(record: InspectionRunRecord) -> list[dict]:
    """Return raw review items for a completed assessment."""

    if record.result is None:
        return []
    return record.result.human_review_items


def human_review_status_counts(record: InspectionRunRecord) -> dict[str, int]:
    """Count current review states using saved decisions as the source of truth."""

    counts = {"pending": 0, "reviewed": 0, "deferred": 0}
    for item in review_items_for_record(record):
        review_id = str(item.get("review_id", ""))
        decision = record.human_review_decisions.get(review_id)
        item_status = decision.status if decision else str(item.get("status", "pending"))
        if item_status not in counts:
            item_status = "pending"
        counts[item_status] += 1
    return counts


def all_human_review_items_reviewed(record: InspectionRunRecord) -> bool:
    """Return true when every flagged item has a reviewed decision."""

    review_items = review_items_for_record(record)
    if not review_items:
        return True
    return all(
        record.human_review_decisions.get(str(item.get("review_id", "")))
        and record.human_review_decisions[str(item.get("review_id", ""))].status == "reviewed"
        for item in review_items
    )


def status_after_assessment(record: InspectionRunRecord) -> ApiRunStatus:
    """Map an assessment result to the API workflow status."""

    if record.result is None:
        return record.status
    if record.result.pipeline_status == "failed" or record.result.errors:
        return "failed"
    if not review_items_for_record(record):
        return "ready_for_report"
    return "ready_for_report" if all_human_review_items_reviewed(record) else "awaiting_human_review"


def human_review_decision_records(record: InspectionRunRecord) -> list[dict]:
    """Return exact review decisions with category/image context for final payloads."""

    decisions = []
    for item in review_items_for_record(record):
        review_id = str(item.get("review_id", ""))
        decision = record.human_review_decisions.get(review_id)
        if decision is None:
            continue
        decisions.append(
            {
                "review_id": review_id,
                "category_name": str(item.get("category_name", "")),
                "image_id": str(item.get("image_id", "")),
                "status": decision.status,
                "notes": decision.notes,
            }
        )
    return decisions


def run_summary_with_human_review(record: InspectionRunRecord) -> dict:
    """Copy the assessment run summary and attach human-review decisions."""

    if record.result is None:
        return {}
    run_summary = copy.deepcopy(record.result.run_summary)
    run_summary["human_review_decisions"] = human_review_decision_records(record)
    return run_summary


def build_human_review_model_summary(item: dict) -> HumanReviewModelSummary:
    """Extract concise display text from the model assessment."""

    assessment = item.get("model_assessment") if isinstance(item.get("model_assessment"), dict) else {}
    risk_assessment = assessment.get("risk_assessment") if isinstance(assessment.get("risk_assessment"), dict) else {}
    recommended_action = (
        assessment.get("recommended_action") if isinstance(assessment.get("recommended_action"), dict) else {}
    )
    officer_comment_assessment = (
        assessment.get("officer_comment_assessment")
        if isinstance(assessment.get("officer_comment_assessment"), dict)
        else {}
    )
    raw_uncertainties = assessment.get("uncertainties") if isinstance(assessment.get("uncertainties"), list) else []
    raw_findings = assessment.get("visual_findings") if isinstance(assessment.get("visual_findings"), list) else []

    visible_findings = []
    for finding in raw_findings:
        if not isinstance(finding, dict) or finding.get("visibility") != "visible":
            continue
        visible_findings.append(
            HumanReviewFindingSummary(
                issue_type=str(finding.get("issue_type", "")),
                visibility=str(finding.get("visibility", "")),
                severity=str(finding.get("severity", "")),
                evidence=str(finding.get("evidence", "")),
                confidence=finding.get("confidence") if isinstance(finding.get("confidence"), (int, float)) else None,
            )
        )

    return HumanReviewModelSummary(
        risk_severity=str(risk_assessment.get("severity", "")),
        risk_reason=str(risk_assessment.get("reason", "")),
        recommended_action=str(recommended_action.get("action_text", "")),
        officer_comment_status=str(officer_comment_assessment.get("status", "")),
        officer_comment_reason=str(officer_comment_assessment.get("reason", "")),
        uncertainties=[str(item) for item in raw_uncertainties],
        visible_findings=visible_findings,
    )


def sanitize_human_review_item(
    record: InspectionRunRecord,
    item: dict,
    decisions: dict[str, HumanReviewDecisionRequest] | None = None,
) -> HumanReviewApiItem:
    """Remove filesystem paths and model internals from a human-review item."""

    review_id = str(item.get("review_id", ""))
    decision = (decisions or {}).get(review_id)
    return HumanReviewApiItem(
        review_id=review_id,
        category_name=str(item.get("category_name", "")),
        image_id=str(item.get("image_id", "")),
        reason=str(item.get("reason", "")),
        status=decision.status if decision else str(item.get("status", "pending")),
        image_available=safe_human_review_image_path(record, item) is not None,
        model_summary=build_human_review_model_summary(item),
        reviewer_notes=decision.notes if decision else "",
    )


def sanitize_category_summaries(result: SchoolInspectionResult | None) -> dict[str, CategorySummaryResponse]:
    """Return category summaries without saved file paths or internal errors."""

    if result is None:
        return {}
    summaries = {}
    for category_name, summary in result.category_summaries.items():
        summaries[category_name] = CategorySummaryResponse(
            category_status=summary.get("category_status"),
            image_count=summary.get("image_count", 0),
            human_review_required=summary.get("human_review_required", False),
            human_review_item_count=summary.get("human_review_item_count", 0),
        )
    return summaries


def sanitized_errors(record: InspectionRunRecord) -> list[str]:
    """Return safe external errors without internal paths or stack traces."""

    if record.errors:
        return record.errors
    if record.status == "failed":
        return ["Pipeline failed. Check server logs for details."]
    return []


def downloadable_artifact_names(result: SchoolInspectionResult, run_id: str) -> list[str]:
    """Return artifact keys that resolve to files inside this API run root."""

    resolved_run_root = run_root(run_id).resolve()
    artifact_names = []
    for artifact_name, artifact_path in result.artifact_paths.items():
        if not artifact_name.startswith("final_report:"):
            continue
        resolved_path = Path(artifact_path).resolve()
        if resolved_path.is_relative_to(resolved_run_root) and resolved_path.is_file():
            artifact_names.append(artifact_name)
    return sorted(artifact_names)


def build_status_response(record: InspectionRunRecord) -> InspectionRunStatusResponse:
    """Build the public status response for a run."""

    input_status = build_input_status(record)
    progress = build_progress_response(record, input_status)
    result = record.result
    if result is None:
        return InspectionRunStatusResponse(
            run_id=record.run_id,
            status=record.status,
            input_status=input_status,
            progress=progress,
            errors=sanitized_errors(record),
        )

    return InspectionRunStatusResponse(
        run_id=record.run_id,
        status=record.status,
        input_status=input_status,
        progress=progress,
        pipeline_status=result.pipeline_status,
        overall_status=result.overall_status,
        provisional=result.provisional,
        processed_sections=result.processed_sections,
        failed_sections=result.failed_sections,
        not_inspected_sections=result.not_inspected_sections,
        total_images=result.total_images,
        human_review_required=result.human_review_required,
        human_review_items=[
            sanitize_human_review_item(record, item, record.human_review_decisions) for item in result.human_review_items
        ],
        category_summaries=sanitize_category_summaries(result),
        artifacts=downloadable_artifact_names(result, record.run_id),
        warnings=result.warnings,
        errors=sanitized_errors(record),
    )


def validate_uploaded_image(filename: str | None, content_type: str | None, data: bytes) -> str:
    """Validate uploaded image metadata and readable image bytes."""

    if not filename:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Uploaded image must include a filename.")
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_IMAGE_EXTENSIONS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unsupported image extension. Supported extensions: {sorted(SUPPORTED_IMAGE_EXTENSIONS)}",
        )
    if content_type not in IMAGE_CONTENT_TYPES.get(suffix, set()):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Uploaded image content type does not match its extension.")
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Uploaded image is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Uploaded image is larger than 10 MB.")

    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
    except (UnidentifiedImageError, OSError) as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Uploaded file is not a readable image.") from error

    return suffix


def build_pipeline_request(record: InspectionRunRecord) -> SchoolInspectionRequest:
    """Convert staged API inputs into the internal filesystem-oriented request."""

    sections = []
    for section in record.request.sections:
        staged_images = record.staged_images.get(section.section_name, [])
        sections.append(
            InspectionSectionInput(
                section_name=section.section_name,
                section_comment=section.section_comment,
                images=[
                    InspectionImageInput(image_path=image.staged_path, comment=image.comment)
                    for image in staged_images
                ],
            )
        )
    return SchoolInspectionRequest(school=record.request.school, sections=sections)


def final_report_options(run_id: str) -> PipelineExecutionOptions:
    """Return normalized paths for finalizing an existing API run."""

    return PipelineExecutionOptions(
        output_root=run_root(run_id),
        materialized_input_root=run_root(run_id) / "pipeline_inputs",
        run_id=run_id,
        generate_report=True,
    )


def build_finalized_result(record: InspectionRunRecord, report_result: dict) -> SchoolInspectionResult:
    """Merge final aggregation/report artifacts into the existing assessment result."""

    if record.result is None:
        raise RuntimeError("Cannot finalize a run before assessment completes.")

    aggregation = report_result["aggregation"]
    final_report = aggregation["final_report"]
    global_rollup = aggregation["global_rollup"]
    run_summary = run_summary_with_human_review(record)
    options = final_report_options(record.run_id)

    return SchoolInspectionResult(
        school=record.result.school,
        pipeline_status="completed",
        overall_status=final_report.overall_status,
        provisional=final_report.provisional,
        processed_sections=global_rollup.get("processed_categories", record.result.processed_sections),
        failed_sections=global_rollup.get("failed_categories", record.result.failed_sections),
        not_inspected_sections=global_rollup.get("not_inspected_categories", record.result.not_inspected_sections),
        total_images=global_rollup.get("total_images", record.result.total_images),
        human_review_required=bool(review_items_for_record(record)),
        human_review_items=record.result.human_review_items,
        category_summaries=record.result.category_summaries,
        run_summary=run_summary,
        artifact_paths=build_artifact_paths(options, run_summary, report_result),
        warnings=record.result.warnings,
        errors=[],
    )


def execute_pipeline_job(run_id: str) -> None:
    """Run the blocking pipeline in a FastAPI background task."""

    record = RUNS[run_id]
    try:
        with PIPELINE_LOCK:
            result = run_school_safety_pipeline(
                build_pipeline_request(record),
                PipelineExecutionOptions(
                    output_root=API_OUTPUT_ROOT,
                    run_id=run_id,
                    generate_report=False,
                ),
            )
        record.result = result
        record.status = status_after_assessment(record)
    except Exception:
        logger.exception("API inspection run %s failed unexpectedly.", run_id)
        record.status = "failed"
        record.errors = ["Pipeline failed. Check server logs for details."]


def execute_final_report_job(run_id: str) -> None:
    """Run final aggregation and report generation after human review."""

    record = RUNS[run_id]
    try:
        with PIPELINE_LOCK:
            options = final_report_options(run_id)
            settings = get_settings(input_root=options.materialized_input_root, output_root=options.output_root)
            report_result = run_final_report_generation(
                settings=settings,
                full_run_state=run_summary_with_human_review(record),
            )
        record.result = build_finalized_result(record, report_result)
        record.status = "completed"
    except Exception:
        logger.exception("API report finalization for run %s failed unexpectedly.", run_id)
        record.status = "failed"
        record.errors = ["Final report generation failed. Check server logs for details."]


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Return basic service health."""

    return HealthResponse(status="ok")


@router.post("/inspection-runs", response_model=InspectionRunCreateResponse, status_code=status.HTTP_201_CREATED)
def create_inspection_run(payload: InspectionRunCreateRequest) -> InspectionRunCreateResponse:
    """Create a run record before uploading images and starting processing."""

    section_names = [section.section_name.strip() for section in payload.sections]
    validate_section_names(section_names)
    normalized_sections = [
        section.model_copy(update={"section_name": section.section_name.strip()}) for section in payload.sections
    ]

    run_id = uuid.uuid4().hex
    record = InspectionRunRecord(
        run_id=run_id,
        request=payload.model_copy(update={"sections": normalized_sections}),
        staged_images={section_name: [] for section_name in section_names},
    )
    RUNS[run_id] = record
    run_root(run_id).mkdir(parents=True, exist_ok=True)
    return InspectionRunCreateResponse(run_id=run_id, status=record.status, sections=section_names)


@router.post(
    "/inspection-runs/{run_id}/sections/{section_name}/images",
    response_model=UploadedImageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_inspection_image(
    run_id: str,
    section_name: str,
    file: Annotated[UploadFile, File()],
    comment: Annotated[str, Form(max_length=1000)] = "",
) -> UploadedImageResponse:
    """Stage one uploaded image inside a controlled run directory."""

    record = get_run_record(run_id)
    if record.status != "created":
        raise HTTPException(status.HTTP_409_CONFLICT, "Images can only be uploaded before the run starts.")
    if section_name not in record.staged_images:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Section was not found for this run.")

    data = await file.read(MAX_UPLOAD_BYTES + 1)
    suffix = validate_uploaded_image(file.filename, file.content_type, data)

    image_id = f"{section_name}_{uuid.uuid4().hex}{suffix}"
    destination_root = upload_root(run_id, section_name)
    destination_root.mkdir(parents=True, exist_ok=True)
    destination_path = destination_root / image_id
    destination_path.write_bytes(data)

    record.staged_images[section_name].append(
        StagedImage(
            image_id=image_id,
            original_filename=file.filename or image_id,
            staged_path=destination_path,
            comment=comment.strip(),
        )
    )
    return UploadedImageResponse(
        run_id=run_id,
        section_name=section_name,
        image_id=image_id,
        original_filename=file.filename or image_id,
    )


@router.post(
    "/inspection-runs/{run_id}/start",
    response_model=StartInspectionRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_inspection_run(
    run_id: str,
    payload: StartInspectionRunRequest,
    background_tasks: BackgroundTasks,
) -> StartInspectionRunResponse:
    """Start background image/category assessment for a staged inspection run."""

    record = get_run_record(run_id)
    if record.status != "created":
        raise HTTPException(status.HTTP_409_CONFLICT, "Inspection run has already been started.")
    input_status = build_input_status(record)
    if input_status.missing_image_sections:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "code": "missing_section_images",
                "message": "Each selected section needs at least one image before assessment starts.",
                "sections": input_status.missing_image_sections,
            },
        )

    record.status = "running"
    background_tasks.add_task(execute_pipeline_job, run_id)
    return StartInspectionRunResponse(run_id=run_id, status=record.status)


@router.post(
    "/inspection-runs/{run_id}/finalize-report",
    response_model=FinalizeInspectionReportResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def finalize_inspection_report(run_id: str, background_tasks: BackgroundTasks) -> FinalizeInspectionReportResponse:
    """Generate final aggregation and report artifacts after review is complete."""

    record = get_run_record(run_id)
    if record.result is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Assessment must finish before final report generation.")
    if record.status == "finalizing_report":
        raise HTTPException(status.HTTP_409_CONFLICT, "Final report generation is already running.")
    if record.status in {"created", "running"}:
        raise HTTPException(status.HTTP_409_CONFLICT, "Assessment must finish before final report generation.")
    if record.status == "failed":
        raise HTTPException(status.HTTP_409_CONFLICT, "Failed runs cannot generate a final report.")
    if record.status == "completed":
        raise HTTPException(status.HTTP_409_CONFLICT, "Final report has already been generated.")
    if not all_human_review_items_reviewed(record):
        counts = human_review_status_counts(record)
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"All human-review items must be reviewed before final report generation. Current counts: {counts}",
        )

    record.status = "finalizing_report"
    background_tasks.add_task(execute_final_report_job, run_id)
    return FinalizeInspectionReportResponse(run_id=run_id, status=record.status)


@router.get("/inspection-runs/{run_id}", response_model=InspectionRunStatusResponse)
def get_inspection_run(run_id: str) -> InspectionRunStatusResponse:
    """Return sanitized status for one inspection run."""

    return build_status_response(get_run_record(run_id))


@router.get("/inspection-runs/{run_id}/human-review", response_model=list[HumanReviewApiItem])
def list_human_review_items(run_id: str) -> list[HumanReviewApiItem]:
    """List sanitized human-review items flagged by the pipeline."""

    record = get_run_record(run_id)
    if record.result is None:
        return []
    return [
        sanitize_human_review_item(record, item, record.human_review_decisions)
        for item in record.result.human_review_items
    ]


@router.get("/inspection-runs/{run_id}/human-review/{review_id}/image")
def download_human_review_image(run_id: str, review_id: str) -> FileResponse:
    """Return the flagged review image when it is inside this run root."""

    record = get_run_record(run_id)
    item = find_human_review_item(record, review_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Human-review item was not found for this run.")

    image_path = safe_human_review_image_path(record, item)
    if image_path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Human-review image was not found for this run.")
    return FileResponse(image_path, filename=image_path.name)


@router.post(
    "/inspection-runs/{run_id}/human-review/{review_id}",
    response_model=HumanReviewDecisionResponse,
)
def record_human_review_decision(
    run_id: str,
    review_id: str,
    payload: HumanReviewDecisionRequest,
) -> HumanReviewDecisionResponse:
    """Record a manual human-review decision for a flagged image."""

    record = get_run_record(run_id)
    if find_human_review_item(record, review_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Human-review item was not found for this run.")

    record.human_review_decisions[review_id] = payload
    if record.status in {"awaiting_human_review", "ready_for_report"}:
        record.status = status_after_assessment(record)
    return HumanReviewDecisionResponse(run_id=run_id, review_id=review_id, status=payload.status)


@router.get("/inspection-runs/{run_id}/artifacts/{artifact_name}")
def download_artifact(run_id: str, artifact_name: str) -> FileResponse:
    """Download a generated artifact by allowlisted artifact name."""

    record = get_run_record(run_id)
    if record.result is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Artifacts are not available until the run finishes.")
    if not artifact_name.startswith("final_report:"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact was not found for this run.")
    artifact_path = record.result.artifact_paths.get(artifact_name)
    if artifact_path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact was not found for this run.")

    resolved_path = Path(artifact_path).resolve()
    resolved_run_root = run_root(run_id).resolve()
    if not resolved_path.is_relative_to(resolved_run_root) or not resolved_path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact was not found for this run.")

    return FileResponse(resolved_path, filename=resolved_path.name)
