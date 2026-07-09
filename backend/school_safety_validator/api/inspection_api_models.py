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


ApiRunStatus = Literal[
    "created",
    "running",
    "awaiting_human_review",
    "ready_for_report",
    "finalizing_report",
    "completed",
    "completed_with_human_review_required",
    "failed",
]
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


class FinalizeInspectionReportResponse(BaseModel):
    """Response returned when final report generation has been scheduled."""

    run_id: str
    status: ApiRunStatus


class HumanReviewFindingSummary(BaseModel):
    """Short visible finding text for human-review display."""

    issue_type: str = ""
    visibility: str = ""
    severity: str = ""
    evidence: str = ""
    confidence: float | None = None


class HumanReviewModelSummary(BaseModel):
    """Small model inference summary without raw model JSON."""

    risk_severity: str = ""
    risk_reason: str = ""
    recommended_action: str = ""
    officer_comment_status: str = ""
    officer_comment_reason: str = ""
    uncertainties: list[str] = Field(default_factory=list)
    visible_findings: list[HumanReviewFindingSummary] = Field(default_factory=list)


class HumanReviewApiItem(BaseModel):
    """Sanitized human-review item safe for API responses."""

    review_id: str
    category_name: str
    image_id: str
    reason: str
    status: str
    image_available: bool = False
    model_summary: HumanReviewModelSummary = Field(default_factory=HumanReviewModelSummary)
    reviewer_notes: str = ""


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


class SectionInputStatusResponse(BaseModel):
    """Readiness for one selected input section before assessment starts."""

    selected: bool = True
    image_count: int = 0
    ready: bool = False


class InputStatusResponse(BaseModel):
    """Input readiness summary for the selected run sections."""

    can_start: bool = False
    missing_image_sections: list[str] = Field(default_factory=list)
    sections: dict[str, SectionInputStatusResponse] = Field(default_factory=dict)


class RunProgressResponse(BaseModel):
    """Small dashboard progress message for the current API phase."""

    phase: ApiRunStatus
    message: str


class InspectionRunStatusResponse(BaseModel):
    """Sanitized run status returned to API clients."""

    run_id: str
    status: ApiRunStatus
    input_status: InputStatusResponse = Field(default_factory=InputStatusResponse)
    progress: RunProgressResponse | None = None
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
