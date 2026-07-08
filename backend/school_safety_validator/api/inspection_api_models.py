"""Public FastAPI models that avoid exposing local filesystem paths."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from school_safety_validator.inspection_data_models import (
    CategoryStatus,
    OverallInspectionStatus,
    PipelineStatus,
    SchoolMetadata,
)


ApiRunStatus = Literal["created", "running", "completed", "completed_with_human_review_required", "failed"]
HumanReviewDecisionStatus = Literal["reviewed", "deferred"]


class InspectionRunSectionCreate(BaseModel):
    """One inspection category to include in an API-created run."""

    section_name: str = Field(min_length=1, max_length=80)
    section_comment: str = Field(default="", max_length=2000)


class InspectionRunCreateRequest(BaseModel):
    """API request for creating an inspection run before image uploads."""

    school: SchoolMetadata
    sections: list[InspectionRunSectionCreate] = Field(min_length=1)


class InspectionRunCreateResponse(BaseModel):
    """Response returned after a run record is created."""

    run_id: str
    status: ApiRunStatus
    sections: list[str]


class UploadedImageResponse(BaseModel):
    """Response returned after one image is staged for a run."""

    run_id: str
    section_name: str
    image_id: str
    original_filename: str


class StartInspectionRunRequest(BaseModel):
    """Runtime option for starting a staged inspection run."""

    generate_report: bool = True


class StartInspectionRunResponse(BaseModel):
    """Response returned when processing has been scheduled."""

    run_id: str
    status: ApiRunStatus


class HumanReviewApiItem(BaseModel):
    """Sanitized human-review item safe for API responses."""

    review_id: str
    category_name: str
    image_id: str
    reason: str
    status: str


class HumanReviewDecisionRequest(BaseModel):
    """Record a manual review decision for a flagged image."""

    status: HumanReviewDecisionStatus
    notes: str = Field(default="", max_length=2000)


class HumanReviewDecisionResponse(BaseModel):
    """Response returned after a human-review decision is recorded."""

    run_id: str
    review_id: str
    status: HumanReviewDecisionStatus


class CategorySummaryResponse(BaseModel):
    """Small category summary without internal file paths."""

    category_status: CategoryStatus | None = None
    image_count: int = 0
    human_review_required: bool = False
    human_review_item_count: int = 0


class InspectionRunStatusResponse(BaseModel):
    """Sanitized run status returned to API clients."""

    run_id: str
    status: ApiRunStatus
    pipeline_status: PipelineStatus | None = None
    overall_status: OverallInspectionStatus | None = None
    provisional: bool | None = None
    processed_sections: list[str] = Field(default_factory=list)
    failed_sections: list[str] = Field(default_factory=list)
    not_inspected_sections: list[str] = Field(default_factory=list)
    total_images: int = 0
    human_review_required: bool = False
    human_review_items: list[HumanReviewApiItem] = Field(default_factory=list)
    category_summaries: dict[str, CategorySummaryResponse] = Field(default_factory=dict)
    artifacts: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """Basic service health response."""

    status: Literal["ok"]
