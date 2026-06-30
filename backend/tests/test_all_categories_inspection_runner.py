"""Tests for local all-category orchestration without live model calls."""

import asyncio
from pathlib import Path

from school_safety_validator import all_categories_inspection_runner
from school_safety_validator.all_categories_inspection_runner import (
    build_all_category_run_summary,
    parse_category_list,
    run_all_category_inspections,
)
from school_safety_validator.inspection_runtime_settings import ValidatorSettings


def fake_category_state(category_name: str, output_file: Path) -> dict:
    """Build the minimal state shape produced by one completed category run."""

    return {
        "category_name": category_name,
        "image_results": [{"image_id": f"{category_name}_001.jpg", "status": "completed"}],
        "human_review_queue": [],
        "human_review_required": False,
        "category_status": "minor_maintenance",
        "saved_category_output_file": output_file,
    }


def test_parse_category_list_returns_clean_category_names() -> None:
    assert parse_category_list("classroom, electrical, washroom") == [
        "classroom",
        "electrical",
        "washroom",
    ]
    assert parse_category_list(None) is None


def test_build_all_category_run_summary_indexes_saved_outputs(tmp_path: Path) -> None:
    output_file = tmp_path / "classroom_image_assessments.json"
    full_run_state = {
        "run_category_names": ["classroom"],
        "category_states": {
            "classroom": fake_category_state("classroom", output_file),
        },
        "all_human_review_queue": [],
        "saved_category_output_files": {"classroom": output_file},
    }

    summary = build_all_category_run_summary(full_run_state)

    assert summary["processed_categories"] == ["classroom"]
    assert summary["category_summaries"]["classroom"]["image_count"] == 1
    assert summary["saved_category_output_files"]["classroom"] == str(output_file)


def test_run_all_category_inspections_reuses_clients_and_saves_summary(monkeypatch, tmp_path: Path) -> None:
    calls = []

    async def fake_run_category_inspection(category_name, settings, clients):
        calls.append((category_name, clients))
        return fake_category_state(
            category_name,
            settings.output_root / "category_outputs" / f"{category_name}_image_assessments.json",
        )

    monkeypatch.setattr(
        all_categories_inspection_runner,
        "run_category_inspection",
        fake_run_category_inspection,
    )

    sentinel_clients = object()
    settings = ValidatorSettings(output_root=tmp_path)
    summary = asyncio.run(run_all_category_inspections(["classroom", "washroom"], settings, sentinel_clients))

    assert [call[0] for call in calls] == ["classroom", "washroom"]
    assert all(call[1] is sentinel_clients for call in calls)
    assert summary["processed_categories"] == ["classroom", "washroom"]
    assert (tmp_path / "run_outputs" / "all_category_run_summary.json").exists()
