"""Minimal FastAPI routes for testing the School Safety Validator pipeline."""

from __future__ import annotations

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
from school_safety_validator.pipeline import run_school_safety_pipeline

from .inspection_api_models import (
    ApiRunStatus,
    CategorySummaryResponse,
    HealthResponse,
    HumanReviewApiItem,
    HumanReviewDecisionRequest,
    HumanReviewDecisionResponse,
    InspectionRunCreateRequest,
    InspectionRunCreateResponse,
    InspectionRunStatusResponse,
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


def sanitize_human_review_item(
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
        resolved_path = Path(artifact_path).resolve()
        if resolved_path.is_relative_to(resolved_run_root) and resolved_path.is_file():
            artifact_names.append(artifact_name)
    return sorted(artifact_names)


def build_status_response(record: InspectionRunRecord) -> InspectionRunStatusResponse:
    """Build the public status response for a run."""

    result = record.result
    if result is None:
        return InspectionRunStatusResponse(
            run_id=record.run_id,
            status=record.status,
            errors=sanitized_errors(record),
        )

    return InspectionRunStatusResponse(
        run_id=record.run_id,
        status=record.status,
        pipeline_status=result.pipeline_status,
        overall_status=result.overall_status,
        provisional=result.provisional,
        processed_sections=result.processed_sections,
        failed_sections=result.failed_sections,
        not_inspected_sections=result.not_inspected_sections,
        total_images=result.total_images,
        human_review_required=result.human_review_required,
        human_review_items=[
            sanitize_human_review_item(item, record.human_review_decisions) for item in result.human_review_items
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
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Uploaded image is larger than 10 MB.")

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


def execute_pipeline_job(run_id: str, start_options: StartInspectionRunRequest) -> None:
    """Run the blocking pipeline in a FastAPI background task."""

    record = RUNS[run_id]
    try:
        with PIPELINE_LOCK:
            result = run_school_safety_pipeline(
                build_pipeline_request(record),
                PipelineExecutionOptions(
                    output_root=API_OUTPUT_ROOT,
                    run_id=run_id,
                    generate_report=start_options.generate_report,
                ),
            )
        record.result = result
        record.status = result.pipeline_status
    except Exception:
        logger.exception("API inspection run %s failed unexpectedly.", run_id)
        record.status = "failed"
        record.errors = ["Pipeline failed. Check server logs for details."]


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
    """Start background processing for a staged inspection run."""

    record = get_run_record(run_id)
    if record.status != "created":
        raise HTTPException(status.HTTP_409_CONFLICT, "Inspection run has already been started.")

    record.status = "running"
    background_tasks.add_task(execute_pipeline_job, run_id, payload)
    return StartInspectionRunResponse(run_id=run_id, status=record.status)


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
    return [sanitize_human_review_item(item, record.human_review_decisions) for item in record.result.human_review_items]


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
    review_items = record.result.human_review_items if record.result else []
    known_review_ids = {str(item.get("review_id", "")) for item in review_items}
    if review_id not in known_review_ids:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Human-review item was not found for this run.")

    record.human_review_decisions[review_id] = payload
    return HumanReviewDecisionResponse(run_id=run_id, review_id=review_id, status=payload.status)


@router.get("/inspection-runs/{run_id}/artifacts/{artifact_name}")
def download_artifact(run_id: str, artifact_name: str) -> FileResponse:
    """Download a generated artifact by allowlisted artifact name."""

    record = get_run_record(run_id)
    if record.result is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Artifacts are not available until the run finishes.")
    artifact_path = record.result.artifact_paths.get(artifact_name)
    if artifact_path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact was not found for this run.")

    resolved_path = Path(artifact_path).resolve()
    resolved_run_root = run_root(run_id).resolve()
    if not resolved_path.is_relative_to(resolved_run_root) or not resolved_path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact was not found for this run.")

    return FileResponse(resolved_path, filename=resolved_path.name)
