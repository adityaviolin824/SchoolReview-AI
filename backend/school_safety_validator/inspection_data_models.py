"""Shared schema contracts for the School Condition Validator backend.

This module is the first extraction from the notebook prototype. It contains the
controlled labels, Pydantic response models, report models, and workflow state
shapes used across the backend. Keeping these contracts in one place makes the
next modules easier to test because model clients, LangGraph nodes, aggregation,
and report rendering can all import the same definitions instead of redefining
JSON shapes independently.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, TypedDict

from pydantic import BaseModel, Field


Visibility = Literal["visible", "not_visible", "unclear"]
Severity = Literal["none", "low", "medium", "high", "unclear"]
OfficerCommentStatus = Literal["present", "missing", "unrelated", "contradictory", "unclear"]
OfficerAgreement = Literal[
    "supports_visual_evidence",
    "contradicts_visual_evidence",
    "unrelated",
    "no_comment",
    "unclear",
]
ActionType = Literal[
    "none",
    "monitor",
    "maintenance_review",
    "urgent_attention",
    "documentation_follow_up",
    "human_review",
]
CategoryStatus = Literal[
    "acceptable_visible_condition",
    "minor_maintenance",
    "attention_required",
    "urgent_review",
    "insufficient_evidence",
]
HumanReviewStatus = Literal["not_required", "pending"]
AssessmentSource = Literal["primary_model", "backup_model", "review_model"]
ImageJobStatus = Literal["pending", "completed", "failed"]
OverallInspectionStatus = Literal[
    "acceptable_with_minor_issues",
    "maintenance_attention_required",
    "urgent_review_required",
    "insufficient_evidence",
]


class VisualFinding(BaseModel):
    """One visible issue or uncertainty found in an image."""

    issue_type: str = Field(max_length=80)
    visibility: Visibility
    severity: Severity
    evidence: str = Field(max_length=260)
    confidence: float = Field(ge=0, le=1)


class RiskAssessment(BaseModel):
    """Overall image-level risk after reviewing visible evidence."""

    severity: Severity
    requires_human_review: bool
    reason: str = Field(max_length=260)


class OfficerCommentAssessment(BaseModel):
    """How the raw officer comment relates to the visible image evidence."""

    text: str = Field(max_length=500)
    status: OfficerCommentStatus
    agreement: OfficerAgreement
    reason: str = Field(max_length=260)
    documentation_gap: bool


class RecommendedAction(BaseModel):
    """Simple next step based on visible evidence and uncertainty."""

    action_type: ActionType
    action_text: str = Field(max_length=260)


class ImageAssessment(BaseModel):
    """Complete structured output for one inspection image."""

    image_name: str
    category: str
    visual_findings: list[VisualFinding]
    risk_assessment: RiskAssessment
    officer_comment_assessment: OfficerCommentAssessment
    recommended_action: RecommendedAction
    uncertainties: list[str]


class CategoryFinalFeedback(BaseModel):
    """Final report feedback for one inspection category."""

    category: str
    status: CategoryStatus
    priority: Literal["low", "medium", "high", "urgent"]
    short_summary: str = Field(max_length=700)
    main_concerns: list[str]
    recommended_next_steps: list[str]
    evidence_refs: list[str]


class FinalInspectionLLMReport(BaseModel):
    """Structured output expected from the final aggregation LLM."""

    overall_status: OverallInspectionStatus
    provisional: bool
    executive_summary: str = Field(max_length=1200)
    key_risks: list[str]
    category_feedback: list[CategoryFinalFeedback]
    immediate_actions: list[str]
    maintenance_actions: list[str]
    documentation_followups: list[str]
    human_review_notes: list[str]
    limitations: list[str]


class FinalReportCategorySection(BaseModel):
    """Report-ready content for one inspection category."""

    category: str
    status: CategoryStatus
    priority: Literal["low", "medium", "high", "urgent"]
    summary: str = Field(max_length=900)
    evidence_refs: list[str]
    recommended_actions: list[str]


class FinalReportContent(BaseModel):
    """Structured report content rendered by deterministic templates."""

    title: str = Field(max_length=180)
    overall_status: OverallInspectionStatus
    provisional: bool
    executive_summary: list[str]
    scope_and_inputs: list[str]
    category_sections: list[FinalReportCategorySection]
    immediate_actions: list[str]
    maintenance_actions: list[str]
    documentation_followups: list[str]
    human_review_notes: list[str]
    limitations: list[str]
    disclaimer: str


class CategoryPaths(TypedDict):
    """Folder/file paths needed for one category run."""

    images_path: Path
    comments_path: Path
    overall_comment_path: Path
    privacy_images_path: Path
    model_output_path: Path


class JobError(TypedDict, total=False):
    """Short error details saved when one image job fails."""

    error_type: str
    error_message: str


class HumanReviewItem(TypedDict, total=False):
    """One image-level item that should be checked after category processing."""

    review_id: str
    category_name: str
    image_id: str
    raw_image_path: str
    reason: str
    model_assessment: dict
    status: HumanReviewStatus


class ImageAssessmentState(TypedDict, total=False):
    """State for assessing one inspection image."""

    category_name: str
    raw_image_path: Path
    privacy_image_path: Path
    officer_comment: str
    system_prompt: str

    primary_assessment: ImageAssessment | None
    backup_assessment: ImageAssessment | None
    review_assessment: ImageAssessment | None
    final_assessment: ImageAssessment | None

    primary_error: str | None
    review_error: str | None
    backup_used: bool
    review_used: bool
    final_assessment_source: AssessmentSource | None

    status: ImageJobStatus
    error: JobError | None

    human_review_required: bool
    human_review_status: HumanReviewStatus
    human_review_item: HumanReviewItem | None
    human_review_notes: str


class CategoryRunState(TypedDict, total=False):
    """State for running all image assessments inside one category."""

    category_name: str
    category_paths: CategoryPaths
    overall_comment: str
    system_prompt: str
    image_jobs: list[ImageAssessmentState]
    image_results: list[dict]
    human_review_queue: list[HumanReviewItem]
    category_summary: dict | None
    category_status: CategoryStatus | None
    human_review_required: bool
    saved_category_output_file: Path | None


class FullInspectionRunState(TypedDict, total=False):
    """State for the full run across selected categories."""

    run_category_names: list[str]
    category_states: dict[str, CategoryRunState]
    all_human_review_queue: list[HumanReviewItem]
    saved_category_output_files: dict[str, Path]
