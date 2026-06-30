"""Run every configured school inspection category locally.

This module intentionally stops after category-level outputs. It does not call
the final aggregation LLM, generate final report prose, render PDFs, or expose
FastAPI routes. That gives us a local checkpoint where we can inspect exactly
what image inputs were sent through the graph and what category JSON came out.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from langchain_core.tracers.langchain import wait_for_all_tracers
from langsmith import tracing_context
from utils.logger import configure_logging, logging

from .deterministic_assessment_rules import init_full_run_state
from .inspection_output_storage import save_all_category_run_summary
from .inspection_runtime_settings import CATEGORY_NAMES, ValidatorSettings, get_settings
from .single_category_inspection_runner import run_category_inspection
from .vision_model_provider_clients import ModelClients


logger = logging.getLogger(__name__)


def build_failed_category_state(category_name: str, error: Exception) -> dict:
    """Represent a category-level runner failure without stopping the full run."""

    error_data = {"error_type": type(error).__name__, "error_message": str(error)[:1000]}
    return {
        "category_name": category_name,
        "image_results": [],
        "human_review_queue": [],
        "human_review_required": True,
        "category_status": "insufficient_evidence",
        "saved_category_output_file": None,
        "category_error": error_data,
        "category_summary": {
            "category": category_name,
            "image_count": 0,
            "category_status": "insufficient_evidence",
            "human_review_required": True,
            "documentation_gaps": [
                {
                    "image_id": None,
                    "gap": f"Category runner failed before category output could be saved: {error_data['error_message']}",
                }
            ],
            "recommended_actions": ["Review this category run failure before final aggregation."],
        },
    }


def build_all_category_run_summary(full_run_state: dict, saved_run_summary_file: Path | None = None) -> dict:
    """Build a compact index of an all-category local run.

    This is not the final inspection verdict. It is a developer/operator summary
    that helps us inspect the category-level stage before we add final LLM
    aggregation and report generation.
    """

    category_summaries = {}
    failed_categories = []
    processed_categories = []
    for category_name, category_state in full_run_state["category_states"].items():
        if category_state.get("category_error"):
            failed_categories.append(category_name)
        if category_state.get("image_results"):
            processed_categories.append(category_name)
        category_summaries[category_name] = {
            "category_status": category_state.get("category_status"),
            "image_count": len(category_state.get("image_results", [])),
            "human_review_required": category_state.get("human_review_required", False),
            "human_review_item_count": len(category_state.get("human_review_queue", [])),
            "saved_category_output_file": str(category_state.get("saved_category_output_file") or ""),
        }
        if category_state.get("category_error"):
            category_summaries[category_name]["error"] = category_state["category_error"]

    not_inspected_categories = [
        category_name
        for category_name in full_run_state["run_category_names"]
        if category_name not in processed_categories and category_name not in failed_categories
    ]

    summary = {
        "run_category_names": full_run_state["run_category_names"],
        "processed_categories": processed_categories,
        "failed_categories": failed_categories,
        "not_inspected_categories": not_inspected_categories,
        "saved_category_output_files": {
            category_name: str(output_file)
            for category_name, output_file in full_run_state["saved_category_output_files"].items()
        },
        "all_human_review_queue": full_run_state["all_human_review_queue"],
        "category_summaries": category_summaries,
    }
    if saved_run_summary_file is not None:
        summary["saved_run_summary_file"] = str(saved_run_summary_file)
    return summary


async def run_all_category_inspections(
    run_category_names: list[str] | None = None,
    settings: ValidatorSettings | None = None,
    clients: ModelClients | None = None,
) -> dict:
    """Run selected categories sequentially and save category-level outputs.

    A single `ModelClients` instance is reused across all categories. That keeps
    Gemini pacing state in one place and avoids recreating provider clients for
    every category.
    """

    settings = settings or get_settings()
    category_names = run_category_names or CATEGORY_NAMES
    clients = clients or ModelClients.from_env(settings)
    full_run_state = init_full_run_state(category_names)
    logger.info("Starting all-category inspection run for %d categories.", len(category_names))

    # Run categories one at a time for now. This is slower, but easier to debug
    # while we are proving that prompts, image inputs, and JSON outputs are right.
    for category_name in category_names:
        try:
            logger.info("Starting category inside all-category run: %s", category_name)
            category_state = await run_category_inspection(category_name, settings, clients)
        except Exception as error:
            logger.warning("Category inspection failed for %s: %s", category_name, str(error)[:1000])
            category_state = build_failed_category_state(category_name, error)
        full_run_state["category_states"][category_name] = category_state
        full_run_state["all_human_review_queue"].extend(category_state["human_review_queue"])
        if category_state.get("saved_category_output_file"):
            full_run_state["saved_category_output_files"][category_name] = category_state["saved_category_output_file"]

    unsaved_summary = build_all_category_run_summary(full_run_state)
    saved_run_summary_file = save_all_category_run_summary(unsaved_summary, settings)
    logger.info("Saved all-category run summary: %s", saved_run_summary_file)
    return build_all_category_run_summary(full_run_state, saved_run_summary_file)


async def run_all_categories_with_tracing(
    run_category_names: list[str] | None,
    settings: ValidatorSettings,
) -> dict:
    """Run all requested categories with one optional LangSmith trace context."""

    try:
        with tracing_context(enabled=settings.tracing_enabled, project_name=settings.langsmith_project):
            return await run_all_category_inspections(run_category_names, settings)
    finally:
        wait_for_all_tracers()


def parse_category_list(raw_categories: str | None) -> list[str] | None:
    """Parse a comma-separated category override from the CLI."""

    if not raw_categories:
        return None
    return [category.strip() for category in raw_categories.split(",") if category.strip()]


def main() -> None:
    """CLI entrypoint for running all configured categories locally."""

    configure_logging()
    parser = argparse.ArgumentParser(description="Run school inspection image assessment for all categories.")
    parser.add_argument(
        "--categories",
        default=None,
        help="Optional comma-separated category list. Defaults to every configured school category.",
    )
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
    run_summary = asyncio.run(
        run_all_categories_with_tracing(
            parse_category_list(args.categories),
            settings,
        )
    )

    print("Saved run summary:", run_summary["saved_run_summary_file"])
    print("Processed categories:", ", ".join(run_summary["processed_categories"]))
    print("Human review items:", len(run_summary["all_human_review_queue"]))
    for category_name, category_summary in run_summary["category_summaries"].items():
        print(
            f"- {category_name}: {category_summary['category_status']} "
            f"({category_summary['image_count']} images)"
        )


if __name__ == "__main__":
    main()
