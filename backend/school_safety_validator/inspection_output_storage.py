"""Filesystem persistence for one-category inspection outputs."""

from __future__ import annotations

import json
from pathlib import Path

from .inspection_data_models import CategoryRunState, ImageAssessmentState
from .inspection_runtime_settings import ValidatorSettings


def image_state_to_result(
    state: ImageAssessmentState,
    primary_model: str,
    backup_model: str,
    review_model: str,
) -> dict:
    """Convert final image state into the saved image-level JSON shape."""

    raw_image_path = state["raw_image_path"]

    if state.get("status") == "failed":
        review_reason = "Image job failed and should be checked after category processing."
        from .deterministic_assessment_rules import build_human_review_item

        return {
            "image_id": raw_image_path.name,
            "category": state["category_name"],
            "status": "failed",
            "raw_image_path": str(raw_image_path),
            "model_trace": {
                "primary_model": primary_model,
                "backup_model": backup_model,
                "review_model": review_model,
                "final_assessment_source": None,
                "backup_used": state.get("backup_used"),
                "review_used": state.get("review_used"),
                "primary_error": state.get("primary_error"),
                "review_error": state.get("review_error"),
            },
            "primary_assessment": state["primary_assessment"].model_dump() if state.get("primary_assessment") else None,
            "backup_assessment": state["backup_assessment"].model_dump() if state.get("backup_assessment") else None,
            "review_assessment": state["review_assessment"].model_dump() if state.get("review_assessment") else None,
            "final_assessment": state["final_assessment"].model_dump() if state.get("final_assessment") else None,
            "human_review": {
                "required": True,
                "status": "pending",
                "item": build_human_review_item(state, review_reason),
                "notes": review_reason,
            },
            "error": state.get("error"),
        }

    return {
        "image_id": raw_image_path.name,
        "category": state["category_name"],
        "status": state["status"],
        "raw_image_path": str(raw_image_path),
        "model_trace": {
            "primary_model": primary_model,
            "backup_model": backup_model if state.get("backup_used") else None,
            "review_model": review_model if state.get("review_used") else None,
            "final_assessment_source": state.get("final_assessment_source"),
            "backup_used": state.get("backup_used"),
            "review_used": state.get("review_used"),
            "primary_error": state.get("primary_error"),
            "review_error": state.get("review_error"),
        },
        "primary_assessment": state["primary_assessment"].model_dump() if state.get("primary_assessment") else None,
        "backup_assessment": state["backup_assessment"].model_dump() if state.get("backup_assessment") else None,
        "review_assessment": state["review_assessment"].model_dump() if state.get("review_assessment") else None,
        "final_assessment": state["final_assessment"].model_dump() if state.get("final_assessment") else None,
        "human_review": {
            "required": state.get("human_review_required", False),
            "status": state.get("human_review_status", "not_required"),
            "item": state.get("human_review_item"),
            "notes": state.get("human_review_notes", ""),
        },
        "error": state.get("error"),
    }


def save_category_outputs(category_state: CategoryRunState, settings: ValidatorSettings) -> CategoryRunState:
    """Save image JSON files and one compact category summary JSON."""

    category_name = category_state["category_name"]
    category_paths = category_state["category_paths"]

    for result in category_state["image_results"]:
        output_file = category_paths["model_output_path"] / f"{Path(result['image_id']).stem}.json"
        output_file.write_text(json.dumps(result, indent=2), encoding="utf-8")

    category_output_root = settings.output_root / "category_outputs"
    category_output_root.mkdir(parents=True, exist_ok=True)
    category_output_file = category_output_root / f"{category_name}_image_assessments.json"
    category_output_file.write_text(json.dumps(category_state["category_summary"], indent=2), encoding="utf-8")

    category_state["saved_category_output_file"] = category_output_file
    return category_state


def save_all_category_run_summary(run_summary: dict, settings: ValidatorSettings) -> Path:
    """Save a compact local summary for an all-category run.

    Each category still owns its detailed image audit JSON and compact category
    JSON. This file is only a navigation index so a human can quickly see which
    categories ran, where their category JSON files are, and what needs review.
    """

    run_output_root = settings.output_root / "run_outputs"
    run_output_root.mkdir(parents=True, exist_ok=True)
    run_summary_file = run_output_root / "all_category_run_summary.json"
    run_summary_file.write_text(json.dumps(run_summary, indent=2), encoding="utf-8")
    return run_summary_file
