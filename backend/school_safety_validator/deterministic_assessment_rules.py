"""Deterministic rules and state helpers for one-category assessment."""

from __future__ import annotations

from pathlib import Path

from .inspection_data_models import (
    CategoryPaths,
    CategoryRunState,
    FullInspectionRunState,
    HumanReviewItem,
    ImageAssessment,
    ImageAssessmentState,
    Severity,
)


SEVERITY_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3, "unclear": 4}
RANK_TO_SEVERITY = {0: "none", 1: "low", 2: "medium", 3: "high", 4: "unclear"}


def read_text_if_exists(path: Path) -> str:
    """Read a text file when present, otherwise return an empty string."""

    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def init_image_state(
    category_name: str,
    raw_image_path: Path,
    privacy_image_path: Path,
    officer_comment: str,
    system_prompt: str,
) -> ImageAssessmentState:
    """Create the starting state for one image assessment graph run."""

    return {
        "category_name": category_name,
        "raw_image_path": raw_image_path,
        "privacy_image_path": privacy_image_path,
        "officer_comment": officer_comment,
        "system_prompt": system_prompt,
        "primary_assessment": None,
        "backup_assessment": None,
        "review_assessment": None,
        "final_assessment": None,
        "primary_error": None,
        "review_error": None,
        "backup_used": False,
        "review_used": False,
        "final_assessment_source": None,
        "status": "pending",
        "error": None,
        "human_review_required": False,
        "human_review_status": "not_required",
        "human_review_item": None,
        "human_review_notes": "",
    }


def init_category_state(
    category_name: str,
    category_paths: CategoryPaths,
    overall_comment: str,
    system_prompt: str,
) -> CategoryRunState:
    """Create the starting state for one category run."""

    return {
        "category_name": category_name,
        "category_paths": category_paths,
        "overall_comment": overall_comment,
        "system_prompt": system_prompt,
        "image_jobs": [],
        "image_results": [],
        "human_review_queue": [],
        "category_summary": None,
        "category_status": None,
        "human_review_required": False,
        "saved_category_output_file": None,
    }


def init_full_run_state(run_category_names: list[str]) -> FullInspectionRunState:
    """Create the starting state for a selected multi-category run."""

    return {
        "run_category_names": run_category_names,
        "category_states": {},
        "all_human_review_queue": [],
        "saved_category_output_files": {},
    }


def clean_uncertainties(uncertainties: list[str]) -> list[str]:
    """Remove empty placeholder uncertainty strings from model output."""

    cleaned = []
    for item in uncertainties:
        text = str(item).strip()
        if text and text.lower() not in {"none", "n/a", "na", "no uncertainty", "no uncertainties"}:
            cleaned.append(text)
    return cleaned


def normalize_assessment(
    assessment: ImageAssessment,
    image_name: str,
    category_name: str,
    officer_comment: str,
) -> ImageAssessment:
    """Apply structural cleanup after a model response is parsed."""

    assessment.image_name = image_name
    assessment.category = category_name
    assessment.officer_comment_assessment.text = officer_comment
    assessment.uncertainties = clean_uncertainties(assessment.uncertainties)
    return assessment


def max_visible_severity(assessment: ImageAssessment) -> Severity:
    """Find the highest severity among visible or unclear findings."""

    max_rank = SEVERITY_RANK["none"]
    for finding in assessment.visual_findings:
        if finding.visibility == "visible":
            max_rank = max(max_rank, SEVERITY_RANK[finding.severity])
        if finding.visibility == "unclear":
            max_rank = max(max_rank, SEVERITY_RANK["unclear"])
    return RANK_TO_SEVERITY[max_rank]


def apply_rule_based_risk_updates(assessment: ImageAssessment) -> ImageAssessment:
    """Keep image-level risk/action consistent with the strongest visible finding."""

    visible_severity = max_visible_severity(assessment)
    if SEVERITY_RANK[visible_severity] > SEVERITY_RANK[assessment.risk_assessment.severity]:
        assessment.risk_assessment.severity = visible_severity

    if visible_severity == "high" and assessment.recommended_action.action_type in ["none", "monitor"]:
        assessment.recommended_action.action_type = "urgent_attention"
        assessment.recommended_action.action_text = "Address the high-severity visible finding in the category summary."
    elif visible_severity == "medium" and assessment.recommended_action.action_type == "none":
        assessment.recommended_action.action_type = "maintenance_review"
        assessment.recommended_action.action_text = "Review the visible maintenance concern."
    elif visible_severity == "low" and assessment.recommended_action.action_type == "none":
        assessment.recommended_action.action_type = "monitor"
        assessment.recommended_action.action_text = "Monitor the minor visible concern."

    if assessment.uncertainties or assessment.risk_assessment.severity == "unclear":
        assessment.risk_assessment.requires_human_review = True

    return assessment


def finalize_model_assessment(
    assessment: ImageAssessment,
    image_name: str,
    category_name: str,
    officer_comment: str,
) -> ImageAssessment:
    """Normalize and apply deterministic risk rules to one model assessment."""

    assessment = normalize_assessment(assessment, image_name, category_name, officer_comment)
    return apply_rule_based_risk_updates(assessment)


def should_use_review_model(assessment: ImageAssessment, confidence_threshold: float = 0.60) -> bool:
    """Decide whether the independent review model should review this image."""

    if assessment.risk_assessment.requires_human_review:
        return True
    if assessment.risk_assessment.severity in ["high", "unclear"]:
        return True
    if assessment.officer_comment_assessment.agreement in ["contradicts_visual_evidence", "unclear"]:
        return True
    return any(
        finding.visibility == "unclear" or finding.confidence < confidence_threshold
        for finding in assessment.visual_findings
    )


def build_human_review_item(state: ImageAssessmentState, reason: str | None = None) -> HumanReviewItem:
    """Create one queued human-review item from a completed or failed image state."""

    final_assessment = state.get("final_assessment")
    image_id = state["raw_image_path"].name

    return {
        "review_id": f"{state['category_name']}::{image_id}",
        "category_name": state["category_name"],
        "image_id": image_id,
        "raw_image_path": str(state["raw_image_path"]),
        "reason": reason
        or (final_assessment.risk_assessment.reason if final_assessment else "Image assessment failed or is missing."),
        "model_assessment": final_assessment.model_dump() if final_assessment else {},
        "status": "pending",
    }


def finalize_human_review_fields(state: ImageAssessmentState) -> dict:
    """Return human-review fields for a completed image state."""

    if state.get("human_review_required"):
        return {
            "human_review_required": True,
            "human_review_status": state.get("human_review_status", "pending"),
            "human_review_item": state.get("human_review_item") or build_human_review_item(state),
            "human_review_notes": state.get(
                "human_review_notes",
                "Queued for human review after all category processing is complete.",
            ),
        }

    final_assessment = state.get("final_assessment")
    human_review_required = bool(final_assessment and final_assessment.risk_assessment.requires_human_review)

    if not human_review_required:
        return {
            "human_review_required": False,
            "human_review_status": "not_required",
            "human_review_item": None,
            "human_review_notes": "",
        }

    return {
        "human_review_required": True,
        "human_review_status": "pending",
        "human_review_item": build_human_review_item(state),
        "human_review_notes": "Queued for human review after all category processing is complete.",
    }
