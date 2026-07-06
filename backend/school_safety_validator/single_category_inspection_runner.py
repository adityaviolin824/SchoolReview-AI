"""Run one inspection category through the modular image workflow."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from langchain_core.tracers.langchain import wait_for_all_tracers
from langsmith import tracing_context

from .deterministic_assessment_rules import init_category_state, init_image_state, read_text_if_exists
from .image_assessment_workflow_graph import build_image_assessment_graph
from .inspection_data_models import CategoryRunState, CategoryStatus, ImageAssessmentState
from .inspection_file_paths import build_category_paths, discover_image_paths, ensure_output_dirs
from .logging_config import configure_logging, logging
from .inspection_output_storage import image_state_to_result, save_category_outputs
from .inspection_prompt_templates import build_category_system_prompt
from .inspection_runtime_settings import ValidatorSettings, get_settings
from .vision_model_provider_clients import ModelClients


logger = logging.getLogger(__name__)


def build_category_image_states(
    category_name: str,
    category_paths: dict,
    system_prompt: str,
) -> list[ImageAssessmentState]:
    """Create one starting image state for each image in one category."""

    image_states = []
    image_paths = discover_image_paths(category_paths["images_path"])

    for raw_image_path in image_paths:
        privacy_image_path = category_paths["privacy_images_path"] / raw_image_path.name
        officer_comment = read_text_if_exists(category_paths["comments_path"] / f"{raw_image_path.stem}.txt")
        image_states.append(
            init_image_state(
                category_name,
                raw_image_path,
                privacy_image_path,
                officer_comment,
                system_prompt,
            )
        )
    return image_states


def classify_category(image_results: list[dict]) -> CategoryStatus:
    """Convert image-level risk severities into one category-level status."""

    if not image_results:
        return "insufficient_evidence"

    severities = []
    failed_result_seen = False

    for result in image_results:
        if result["status"] != "completed":
            failed_result_seen = True
            continue
        risk = result["final_assessment"]["risk_assessment"]
        severities.append(risk["severity"])

    if not severities:
        return "insufficient_evidence"
    if "high" in severities:
        return "urgent_review"
    if failed_result_seen or "unclear" in severities:
        return "insufficient_evidence"
    if "medium" in severities:
        return "attention_required"
    if "low" in severities:
        return "minor_maintenance"
    return "acceptable_visible_condition"


def summarize_category(category_name: str, category_results: list[dict], overall_comment: str) -> dict:
    """Create one compact category summary from all image-level results."""

    issue_counts = {"high": 0, "medium": 0, "low": 0}
    key_findings = []
    documentation_gaps = []
    recommended_actions = []
    human_review_required = False

    for result in category_results:
        if result["status"] != "completed":
            human_review_required = True
            error_data = result.get("error") or {}
            error_message = error_data.get("error_message", "Image job failed.")
            documentation_gaps.append({"image_id": result["image_id"], "gap": error_message})
            continue

        assessment = result["final_assessment"]
        risk = assessment["risk_assessment"]
        human_review_required = human_review_required or risk["requires_human_review"]

        comment_assessment = assessment["officer_comment_assessment"]
        if comment_assessment["documentation_gap"]:
            documentation_gaps.append({"image_id": result["image_id"], "gap": comment_assessment["reason"]})

        action_text = assessment["recommended_action"]["action_text"].strip()
        if action_text and action_text.lower() not in {"none", "no action needed"}:
            recommended_actions.append(action_text)

        for finding in assessment["visual_findings"]:
            if finding["visibility"] != "visible":
                continue

            severity = finding["severity"]
            if severity in issue_counts:
                issue_counts[severity] += 1

            if severity in ["high", "medium"]:
                key_findings.append(
                    {
                        "image_id": result["image_id"],
                        "issue_type": finding["issue_type"],
                        "severity": severity,
                        "evidence": finding["evidence"],
                    }
                )

    return {
        "category": category_name,
        "image_count": len(category_results),
        "category_status": classify_category(category_results),
        "overall_officer_comment": overall_comment,
        "issue_counts": issue_counts,
        "human_review_required": human_review_required,
        "key_findings": key_findings,
        "documentation_gaps": documentation_gaps,
        "recommended_actions": sorted(set(recommended_actions)),
    }


async def run_category_inspection(
    category_name: str,
    settings: ValidatorSettings | None = None,
    clients: ModelClients | None = None,
) -> CategoryRunState:
    """Run one category through the image graph and save outputs."""

    settings = settings or get_settings()
    clients = clients or ModelClients.from_env(settings)
    category_paths = build_category_paths(category_name, settings)
    ensure_output_dirs(category_paths, settings.output_root)
    logger.info("Starting category inspection: %s", category_name)

    category_state = init_category_state(
        category_name,
        category_paths,
        read_text_if_exists(category_paths["overall_comment_path"]),
        build_category_system_prompt(category_name),
    )
    category_state["image_jobs"] = build_category_image_states(
        category_name,
        category_paths,
        category_state["system_prompt"],
    )

    if not category_state["image_jobs"]:
        logger.info("No images found for category: %s", category_name)
        category_state["category_summary"] = summarize_category(category_name, [], category_state["overall_comment"])
        category_state["category_status"] = category_state["category_summary"]["category_status"]
        saved_state = save_category_outputs(category_state, settings)
        logger.info("Saved empty category output for %s: %s", category_name, saved_state["saved_category_output_file"])
        return saved_state

    image_assessment_graph = build_image_assessment_graph(clients, settings)
    semaphore = asyncio.Semaphore(settings.max_concurrent_requests)

    async def run_one(image_state: ImageAssessmentState) -> ImageAssessmentState:
        async with semaphore:
            try:
                return await image_assessment_graph.ainvoke(
                    image_state,
                    config={
                        "run_name": f"{category_name}:{image_state['raw_image_path'].name}",
                        "tags": ["school-inspection", category_name],
                        "metadata": {
                            "category": category_name,
                            "image_name": image_state["raw_image_path"].name,
                        },
                    },
                )
            except Exception as error:
                logger.warning(
                    "Image assessment failed for %s/%s: %s",
                    category_name,
                    image_state["raw_image_path"].name,
                    str(error)[:1000],
                )
                return {
                    **image_state,
                    "status": "failed",
                    "error": {"error_type": type(error).__name__, "error_message": str(error)[:1000]},
                }

    final_image_states = await asyncio.gather(*(run_one(image_state) for image_state in category_state["image_jobs"]))
    image_results = []
    human_review_queue = []

    for final_image_state in final_image_states:
        image_result = image_state_to_result(
            final_image_state,
            settings.primary_vlm_model,
            settings.backup_vlm_model,
            settings.escalation_review_model,
        )
        image_results.append(image_result)

        review_item = image_result["human_review"].get("item")
        if review_item:
            human_review_queue.append(review_item)

    category_state["image_results"] = image_results
    category_state["human_review_queue"] = human_review_queue
    category_state["human_review_required"] = bool(human_review_queue)
    category_state["category_summary"] = summarize_category(
        category_name,
        image_results,
        category_state["overall_comment"],
    )
    category_state["category_status"] = category_state["category_summary"]["category_status"]
    saved_state = save_category_outputs(category_state, settings)
    logger.info("Saved category output for %s: %s", category_name, saved_state["saved_category_output_file"])
    return saved_state


async def run_category_with_tracing(category_name: str, settings: ValidatorSettings) -> CategoryRunState:
    """Run one category with LangSmith tracing enabled when configured."""

    try:
        with tracing_context(enabled=settings.tracing_enabled, project_name=settings.langsmith_project):
            return await run_category_inspection(category_name, settings)
    finally:
        wait_for_all_tracers()


def main() -> None:
    """CLI entrypoint for running a single category."""

    configure_logging()
    parser = argparse.ArgumentParser(description="Run one school inspection category.")
    parser.add_argument("category", help="Category name, e.g. classroom or electrical.")
    parser.add_argument("--input-root", type=Path, default=None, help="Dataset root. Defaults to sample_data/school.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Generated output root. Defaults to school_validation_outputs.",
    )
    parser.add_argument("--no-tracing", action="store_true", help="Disable LangSmith tracing for this run.")
    args = parser.parse_args()

    settings = get_settings(
        input_root=args.input_root,
        output_root=args.output_root,
        tracing_enabled=not args.no_tracing,
    )
    category_state = asyncio.run(run_category_with_tracing(args.category, settings))
    print("Saved category output:", category_state["saved_category_output_file"])
    print("Category status:", category_state["category_status"])
    print("Images processed:", len(category_state["image_results"]))
    print("Human review items:", len(category_state["human_review_queue"]))


if __name__ == "__main__":
    main()
