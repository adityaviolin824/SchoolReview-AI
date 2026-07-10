"""Tests for the minimal FastAPI inspection-run boundary."""

from __future__ import annotations

import io
import os
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from PIL import Image

from school_safety_validator.api import fastapi_application
from school_safety_validator.api import inspection_api_routes
from school_safety_validator.api.fastapi_application import create_app
from school_safety_validator.inspection_data_models import SchoolInspectionResult
from school_safety_validator.inspection_runtime_settings import CATEGORY_NAMES


def png_bytes() -> bytes:
    """Create a tiny valid PNG upload body."""

    buffer = io.BytesIO()
    Image.new("RGB", (1, 1), color="white").save(buffer, format="PNG")
    return buffer.getvalue()


def create_run(client: TestClient) -> str:
    response = client.post(
        "/inspection-runs",
        json={
            "school": {
                "name": "Example Government School",
                "inspection_date": "2026-06-30",
                "location": "Example District",
            },
            "sections": [
                {
                    "section_name": "classroom",
                    "section_comment": "Classroom section comment.",
                }
            ],
        },
    )
    assert response.status_code == 201
    return response.json()["run_id"]


def test_health_endpoint_returns_ok() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_api_output_root_is_root_level_runs_folder() -> None:
    assert inspection_api_routes.API_OUTPUT_ROOT == (
        inspection_api_routes.BACKEND_ROOT.parent / "runs" / "api_runs"
    )


def test_cleanup_old_api_runs_deletes_only_stale_run_directories(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(inspection_api_routes, "API_OUTPUT_ROOT", tmp_path)
    now = 2_000_000.0
    old_run = tmp_path / "old-run"
    fresh_run = tmp_path / "fresh-run"
    old_run.mkdir()
    fresh_run.mkdir()
    untouched_file = tmp_path / "not-a-run.txt"
    untouched_file.write_text("keep", encoding="utf-8")
    stale_timestamp = now - inspection_api_routes.RUN_RETENTION_SECONDS - 10
    os.utime(old_run, (stale_timestamp, stale_timestamp))
    os.utime(fresh_run, (now, now))

    deleted_paths = inspection_api_routes.cleanup_old_api_runs(now=now)

    assert deleted_paths == [old_run]
    assert not old_run.exists()
    assert fresh_run.exists()
    assert untouched_file.exists()


def test_fastapi_lifespan_runs_api_cleanup(monkeypatch) -> None:
    calls = []

    def fake_cleanup_old_api_runs():
        calls.append("cleanup")
        return []

    monkeypatch.setattr(fastapi_application, "cleanup_old_api_runs", fake_cleanup_old_api_runs)

    with TestClient(create_app()):
        pass

    assert calls == ["cleanup"]


def test_cors_allows_local_vite_frontend() -> None:
    client = TestClient(create_app())

    response = client.options(
        "/inspection-runs",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"


def test_start_request_schema_defaults_to_assessment_only() -> None:
    schema = create_app().openapi()["components"]["schemas"]["StartInspectionRunRequest"]
    generate_report = schema["properties"]["generate_report"]

    assert generate_report["default"] is False
    assert "Deprecated" in generate_report["description"]


def test_create_app_serves_bundled_frontend_without_hiding_api_routes(monkeypatch, tmp_path: Path) -> None:
    frontend_dist_dir = tmp_path / "frontend"
    frontend_dist_dir.mkdir()
    (frontend_dist_dir / "index.html").write_text("<!doctype html><div id=\"root\"></div>", encoding="utf-8")
    monkeypatch.setattr(fastapi_application, "FRONTEND_DIST_DIR", frontend_dist_dir)

    client = TestClient(create_app())

    frontend_response = client.get("/")
    health_response = client.get("/health")

    assert frontend_response.status_code == 200
    assert 'id="root"' in frontend_response.text
    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}


def test_start_blocks_selected_sections_without_images(monkeypatch, tmp_path: Path) -> None:
    inspection_api_routes.RUNS.clear()
    monkeypatch.setattr(inspection_api_routes, "API_OUTPUT_ROOT", tmp_path)
    client = TestClient(create_app())
    create_response = client.post(
        "/inspection-runs",
        json={
            "school": {
                "name": "Example Government School",
                "inspection_date": "2026-06-30",
                "location": "Example District",
            },
            "sections": [
                {
                    "section_name": "classroom",
                    "section_comment": "Classroom section comment.",
                },
                {
                    "section_name": "washroom",
                    "section_comment": "Washroom section comment.",
                },
            ],
        },
    )
    assert create_response.status_code == 201
    run_id = create_response.json()["run_id"]

    initial_status_response = client.get(f"/inspection-runs/{run_id}")
    assert initial_status_response.status_code == 200
    initial_status = initial_status_response.json()
    assert initial_status["input_status"]["can_start"] is False
    assert initial_status["input_status"]["missing_image_sections"] == ["classroom", "washroom"]
    assert initial_status["progress"]["message"] == "Upload at least one image for: classroom, washroom."

    classroom_upload = client.post(
        f"/inspection-runs/{run_id}/sections/classroom/images",
        files={"file": ("classroom.png", png_bytes(), "image/png")},
        data={"comment": "Classroom image comment."},
    )
    assert classroom_upload.status_code == 201

    partial_start_response = client.post(f"/inspection-runs/{run_id}/start", json={"generate_report": False})
    assert partial_start_response.status_code == 409
    assert partial_start_response.json()["detail"] == {
        "code": "missing_section_images",
        "message": "Each selected section needs at least one image before assessment starts.",
        "sections": ["washroom"],
    }

    partial_status_response = client.get(f"/inspection-runs/{run_id}")
    assert partial_status_response.status_code == 200
    partial_status = partial_status_response.json()
    assert partial_status["status"] == "created"
    assert partial_status["input_status"]["can_start"] is False
    assert partial_status["input_status"]["sections"]["classroom"] == {
        "selected": True,
        "image_count": 1,
        "ready": True,
    }
    assert partial_status["input_status"]["sections"]["washroom"] == {
        "selected": True,
        "image_count": 0,
        "ready": False,
    }


def test_api_run_upload_start_status_review_then_final_report(monkeypatch, tmp_path: Path) -> None:
    inspection_api_routes.RUNS.clear()
    monkeypatch.setattr(inspection_api_routes, "API_OUTPUT_ROOT", tmp_path)

    def fake_run_school_safety_pipeline(request, options):
        assert options.output_root == tmp_path
        assert options.run_id
        assert options.generate_report is False
        assert request.sections[0].images[0].image_path.is_relative_to(
            tmp_path / options.run_id / "uploads" / "classroom"
        )

        review_image = tmp_path / options.run_id / "pipeline_inputs" / "classroom" / "images" / "classroom_001.png"
        review_image.parent.mkdir(parents=True, exist_ok=True)
        review_image.write_bytes(png_bytes())

        return SchoolInspectionResult(
            school=request.school,
            pipeline_status="completed_with_human_review_required",
            overall_status="insufficient_evidence",
            provisional=True,
            processed_sections=["classroom"],
            failed_sections=[],
            not_inspected_sections=[],
            total_images=1,
            human_review_required=True,
            human_review_items=[
                {
                    "review_id": "review-1",
                    "category_name": "classroom",
                    "image_id": "classroom_001.png",
                    "raw_image_path": str(review_image),
                    "reason": "Evidence needs manual review.",
                    "model_assessment": {
                        "visual_findings": [
                            {
                                "issue_type": "wall_damage",
                                "visibility": "visible",
                                "severity": "medium",
                                "evidence": "Visible wall damage.",
                                "confidence": 0.9,
                            },
                            {
                                "issue_type": "hidden_issue",
                                "visibility": "not_visible",
                                "severity": "unclear",
                                "evidence": "Not visible.",
                                "confidence": 0.2,
                            },
                        ],
                        "risk_assessment": {
                            "severity": "medium",
                            "reason": "Manual review is needed for visible wall damage.",
                        },
                        "officer_comment_assessment": {
                            "status": "partial",
                            "reason": "Officer comment is vague.",
                        },
                        "recommended_action": {
                            "action_text": "Inspect the wall damage manually.",
                        },
                        "uncertainties": ["Depth of damage cannot be verified visually."],
                    },
                    "status": "pending",
                }
            ],
            category_summaries={
                "classroom": {
                    "category_status": "insufficient_evidence",
                    "image_count": 1,
                    "human_review_required": True,
                    "human_review_item_count": 1,
                    "saved_category_output_file": str(tmp_path / "hidden.json"),
                }
            },
            artifact_paths={
                "run_id": options.run_id,
                "output_root": str(tmp_path / options.run_id),
                "materialized_input_root": str(tmp_path / options.run_id / "pipeline_inputs"),
            },
            warnings=["Section warning."],
            errors=[],
        )

    def fake_run_final_report_generation(settings, full_run_state):
        assert settings.output_root == tmp_path / run_id
        assert full_run_state["human_review_decisions"] == [
            {
                "review_id": "review-1",
                "category_name": "classroom",
                "image_id": "classroom_001.png",
                "status": "reviewed",
                "notes": "Reviewed manually.",
            }
        ]
        artifact = tmp_path / run_id / "final_reports" / "school_safety_final_report.md"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text("# Report", encoding="utf-8")
        return {
            "aggregation": {
                "final_report": SimpleNamespace(
                    overall_status="insufficient_evidence",
                    provisional=False,
                ),
                "global_rollup": {
                    "processed_categories": ["classroom"],
                    "failed_categories": [],
                    "not_inspected_categories": [],
                    "total_images": 1,
                },
                "paths": {},
            },
            "report_paths": {
                "markdown_report": artifact,
            },
        }

    monkeypatch.setattr(
        inspection_api_routes,
        "run_school_safety_pipeline",
        fake_run_school_safety_pipeline,
    )
    monkeypatch.setattr(
        inspection_api_routes,
        "run_final_report_generation",
        fake_run_final_report_generation,
    )

    client = TestClient(create_app())
    run_id = create_run(client)

    upload_response = client.post(
        f"/inspection-runs/{run_id}/sections/classroom/images",
        files={"file": ("classroom.png", png_bytes(), "image/png")},
        data={"comment": "Classroom image comment."},
    )
    assert upload_response.status_code == 201

    start_response = client.post(f"/inspection-runs/{run_id}/start", json={"generate_report": True})
    assert start_response.status_code == 202

    status_response = client.get(f"/inspection-runs/{run_id}")
    assert status_response.status_code == 200
    status_payload = status_response.json()

    assert status_payload["status"] == "awaiting_human_review"
    assert status_payload["human_review_required"] is True
    review_item = status_payload["human_review_items"][0]
    assert review_item["review_id"] == "review-1"
    assert review_item["category_name"] == "classroom"
    assert review_item["image_id"] == "classroom_001.png"
    assert review_item["reason"] == "Evidence needs manual review."
    assert review_item["status"] == "pending"
    assert review_item["image_available"] is True
    assert review_item["reviewer_notes"] == ""
    assert review_item["model_summary"] == {
        "risk_severity": "medium",
        "risk_reason": "Manual review is needed for visible wall damage.",
        "recommended_action": "Inspect the wall damage manually.",
        "officer_comment_status": "partial",
        "officer_comment_reason": "Officer comment is vague.",
        "uncertainties": ["Depth of damage cannot be verified visually."],
        "visible_findings": [
            {
                "issue_type": "wall_damage",
                "visibility": "visible",
                "severity": "medium",
                "evidence": "Visible wall damage.",
                "confidence": 0.9,
            }
        ],
    }
    assert "raw_image_path" not in str(status_payload)
    assert "model_assessment" not in str(status_payload)
    assert "saved_category_output_file" not in str(status_payload)
    assert status_payload["artifacts"] == []

    image_response = client.get(f"/inspection-runs/{run_id}/human-review/review-1/image")
    assert image_response.status_code == 200
    assert image_response.content == png_bytes()

    unknown_image_response = client.get(f"/inspection-runs/{run_id}/human-review/unknown-review/image")
    assert unknown_image_response.status_code == 404

    blocked_finalize_response = client.post(f"/inspection-runs/{run_id}/finalize-report")
    assert blocked_finalize_response.status_code == 409

    review_response = client.post(
        f"/inspection-runs/{run_id}/human-review/review-1",
        json={"status": "reviewed", "notes": "Reviewed manually."},
    )
    assert review_response.status_code == 200
    assert review_response.json()["status"] == "reviewed"

    review_items_response = client.get(f"/inspection-runs/{run_id}/human-review")
    assert review_items_response.status_code == 200
    assert review_items_response.json()[0]["status"] == "reviewed"
    assert review_items_response.json()[0]["reviewer_notes"] == "Reviewed manually."

    reviewed_status_response = client.get(f"/inspection-runs/{run_id}")
    assert reviewed_status_response.status_code == 200
    assert reviewed_status_response.json()["status"] == "ready_for_report"
    assert reviewed_status_response.json()["artifacts"] == []

    finalize_response = client.post(f"/inspection-runs/{run_id}/finalize-report")
    assert finalize_response.status_code == 202
    assert finalize_response.json()["status"] == "finalizing_report"

    finalized_status_response = client.get(f"/inspection-runs/{run_id}")
    assert finalized_status_response.status_code == 200
    finalized_payload = finalized_status_response.json()
    assert finalized_payload["status"] == "completed"
    assert finalized_payload["overall_status"] == "insufficient_evidence"
    assert finalized_payload["provisional"] is False
    assert finalized_payload["artifacts"] == ["final_report:markdown_report"]

    artifact_response = client.get(f"/inspection-runs/{run_id}/artifacts/final_report:markdown_report")
    assert artifact_response.status_code == 200
    assert artifact_response.text == "# Report"

    duplicate_finalize_response = client.post(f"/inspection-runs/{run_id}/finalize-report")
    assert duplicate_finalize_response.status_code == 409


def test_api_run_supports_multiple_sections_and_human_review_decisions(monkeypatch, tmp_path: Path) -> None:
    inspection_api_routes.RUNS.clear()
    monkeypatch.setattr(inspection_api_routes, "API_OUTPUT_ROOT", tmp_path)

    def fake_run_school_safety_pipeline(request, options):
        assert [section.section_name for section in request.sections] == ["classroom", "washroom"]
        assert [section.section_comment for section in request.sections] == [
            "Classroom section comment.",
            "Washroom section comment.",
        ]
        assert request.sections[0].images[0].comment == "Classroom image comment."
        assert request.sections[1].images[0].comment == "Washroom image comment."
        assert request.sections[0].images[0].image_path.is_relative_to(
            tmp_path / options.run_id / "uploads" / "classroom"
        )
        assert request.sections[1].images[0].image_path.is_relative_to(
            tmp_path / options.run_id / "uploads" / "washroom"
        )
        assert options.generate_report is False

        return SchoolInspectionResult(
            school=request.school,
            pipeline_status="completed_with_human_review_required",
            overall_status=None,
            provisional=None,
            processed_sections=["classroom", "washroom"],
            failed_sections=[],
            not_inspected_sections=[],
            total_images=2,
            human_review_required=True,
            human_review_items=[
                {
                    "review_id": "classroom-review",
                    "category_name": "classroom",
                    "image_id": "classroom_001.png",
                    "raw_image_path": str(tmp_path / "hidden" / "classroom_001.png"),
                    "reason": "Classroom needs review.",
                    "status": "pending",
                },
                {
                    "review_id": "washroom-review",
                    "category_name": "washroom",
                    "image_id": "washroom_001.png",
                    "raw_image_path": str(tmp_path / "hidden" / "washroom_001.png"),
                    "reason": "Washroom needs review.",
                    "status": "pending",
                },
            ],
            category_summaries={
                "classroom": {
                    "category_status": "insufficient_evidence",
                    "image_count": 1,
                    "human_review_required": True,
                    "human_review_item_count": 1,
                    "saved_category_output_file": str(tmp_path / "hidden-classroom.json"),
                },
                "washroom": {
                    "category_status": "insufficient_evidence",
                    "image_count": 1,
                    "human_review_required": True,
                    "human_review_item_count": 1,
                    "saved_category_output_file": str(tmp_path / "hidden-washroom.json"),
                },
            },
            artifact_paths={
                "run_id": options.run_id,
                "output_root": str(tmp_path / options.run_id),
            },
            warnings=[],
            errors=[],
        )

    monkeypatch.setattr(
        inspection_api_routes,
        "run_school_safety_pipeline",
        fake_run_school_safety_pipeline,
    )

    client = TestClient(create_app())
    create_response = client.post(
        "/inspection-runs",
        json={
            "school": {
                "name": "Example Government School",
                "inspection_date": "2026-06-30",
                "location": "Example District",
            },
            "sections": [
                {
                    "section_name": "classroom",
                    "section_comment": "Classroom section comment.",
                },
                {
                    "section_name": "washroom",
                    "section_comment": "Washroom section comment.",
                },
            ],
        },
    )
    assert create_response.status_code == 201
    assert create_response.json()["sections"] == ["classroom", "washroom"]
    run_id = create_response.json()["run_id"]

    classroom_upload = client.post(
        f"/inspection-runs/{run_id}/sections/classroom/images",
        files={"file": ("classroom.png", png_bytes(), "image/png")},
        data={"comment": "Classroom image comment."},
    )
    washroom_upload = client.post(
        f"/inspection-runs/{run_id}/sections/washroom/images",
        files={"file": ("washroom.png", png_bytes(), "image/png")},
        data={"comment": "Washroom image comment."},
    )
    assert classroom_upload.status_code == 201
    assert washroom_upload.status_code == 201

    start_response = client.post(f"/inspection-runs/{run_id}/start", json={"generate_report": False})
    assert start_response.status_code == 202

    status_response = client.get(f"/inspection-runs/{run_id}")
    assert status_response.status_code == 200
    status_payload = status_response.json()

    assert status_payload["status"] == "awaiting_human_review"
    assert status_payload["processed_sections"] == ["classroom", "washroom"]
    assert status_payload["not_inspected_sections"] == [
        category_name for category_name in CATEGORY_NAMES if category_name not in {"classroom", "washroom"}
    ]
    assert status_payload["total_images"] == 2
    assert status_payload["human_review_required"] is True
    assert [item["review_id"] for item in status_payload["human_review_items"]] == [
        "classroom-review",
        "washroom-review",
    ]
    assert [item["image_available"] for item in status_payload["human_review_items"]] == [False, False]
    assert "raw_image_path" not in str(status_payload)
    assert "saved_category_output_file" not in str(status_payload)
    assert status_payload["artifacts"] == []

    unsafe_image_response = client.get(f"/inspection-runs/{run_id}/human-review/classroom-review/image")
    assert unsafe_image_response.status_code == 404

    blocked_finalize_response = client.post(f"/inspection-runs/{run_id}/finalize-report")
    assert blocked_finalize_response.status_code == 409

    review_response = client.post(
        f"/inspection-runs/{run_id}/human-review/washroom-review",
        json={"status": "deferred", "notes": "Deferred for later manual review."},
    )
    assert review_response.status_code == 200

    review_items_response = client.get(f"/inspection-runs/{run_id}/human-review")
    assert review_items_response.status_code == 200
    review_items = review_items_response.json()

    assert review_items[0]["status"] == "pending"
    assert review_items[1]["status"] == "deferred"
    assert review_items[1]["reviewer_notes"] == "Deferred for later manual review."

    deferred_finalize_response = client.post(f"/inspection-runs/{run_id}/finalize-report")
    assert deferred_finalize_response.status_code == 409


def test_category_failure_without_image_review_items_requires_review(monkeypatch, tmp_path: Path) -> None:
    inspection_api_routes.RUNS.clear()
    monkeypatch.setattr(inspection_api_routes, "API_OUTPUT_ROOT", tmp_path)

    def fake_run_school_safety_pipeline(request, options):
        return SchoolInspectionResult(
            school=request.school,
            pipeline_status="completed_with_human_review_required",
            overall_status=None,
            provisional=None,
            processed_sections=[],
            failed_sections=["classroom"],
            not_inspected_sections=[],
            total_images=0,
            human_review_required=True,
            human_review_items=[],
            category_summaries={
                "classroom": {
                    "category_status": "insufficient_evidence",
                    "image_count": 0,
                    "human_review_required": True,
                    "human_review_item_count": 0,
                }
            },
            run_summary={
                "run_category_names": ["classroom"],
                "processed_categories": [],
                "failed_categories": ["classroom"],
                "not_inspected_categories": [],
                "all_human_review_queue": [],
                "category_summaries": {},
            },
            artifact_paths={
                "run_id": options.run_id,
                "output_root": str(tmp_path / options.run_id),
            },
            warnings=[],
            errors=[],
        )

    monkeypatch.setattr(
        inspection_api_routes,
        "run_school_safety_pipeline",
        fake_run_school_safety_pipeline,
    )

    client = TestClient(create_app())
    run_id = create_run(client)
    upload_response = client.post(
        f"/inspection-runs/{run_id}/sections/classroom/images",
        files={"file": ("classroom.png", png_bytes(), "image/png")},
    )
    assert upload_response.status_code == 201

    start_response = client.post(f"/inspection-runs/{run_id}/start", json={"generate_report": False})
    assert start_response.status_code == 202

    status_response = client.get(f"/inspection-runs/{run_id}")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    expected_reason = (
        "The classroom category failed before an image-level review item was created. "
        "Review the category run before final report generation."
    )

    assert status_payload["status"] == "awaiting_human_review"
    assert status_payload["human_review_required"] is True
    assert status_payload["human_review_items"] == [
        {
            "review_id": "classroom_category_failed",
            "category_name": "classroom",
            "image_id": "__category__",
            "reason": expected_reason,
            "status": "pending",
            "image_available": False,
            "model_summary": {
                "risk_severity": "",
                "risk_reason": "",
                "recommended_action": "",
                "officer_comment_status": "",
                "officer_comment_reason": "",
                "uncertainties": [],
                "visible_findings": [],
            },
            "reviewer_notes": "",
        }
    ]

    blocked_finalize_response = client.post(f"/inspection-runs/{run_id}/finalize-report")
    assert blocked_finalize_response.status_code == 409

    review_response = client.post(
        f"/inspection-runs/{run_id}/human-review/classroom_category_failed",
        json={"status": "reviewed", "notes": "Reviewed category failure."},
    )
    assert review_response.status_code == 200

    reviewed_status_response = client.get(f"/inspection-runs/{run_id}")
    assert reviewed_status_response.status_code == 200
    assert reviewed_status_response.json()["status"] == "ready_for_report"


def test_upload_rejects_invalid_image_content_type(monkeypatch, tmp_path: Path) -> None:
    inspection_api_routes.RUNS.clear()
    monkeypatch.setattr(inspection_api_routes, "API_OUTPUT_ROOT", tmp_path)
    client = TestClient(create_app())
    run_id = create_run(client)

    response = client.post(
        f"/inspection-runs/{run_id}/sections/classroom/images",
        files={"file": ("classroom.png", png_bytes(), "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded image content type does not match its extension."


def test_upload_rejects_images_larger_than_limit(monkeypatch, tmp_path: Path) -> None:
    inspection_api_routes.RUNS.clear()
    monkeypatch.setattr(inspection_api_routes, "API_OUTPUT_ROOT", tmp_path)
    client = TestClient(create_app())
    run_id = create_run(client)

    response = client.post(
        f"/inspection-runs/{run_id}/sections/classroom/images",
        files={
            "file": (
                "classroom.png",
                b"0" * (inspection_api_routes.MAX_UPLOAD_BYTES + 1),
                "image/png",
            )
        },
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "Uploaded image is larger than 10 MB."


def test_failed_background_job_returns_sanitized_status_error(monkeypatch, tmp_path: Path) -> None:
    inspection_api_routes.RUNS.clear()
    monkeypatch.setattr(inspection_api_routes, "API_OUTPUT_ROOT", tmp_path)

    def fake_run_school_safety_pipeline(request, options):
        raise RuntimeError("Internal failure with local filesystem details.")

    monkeypatch.setattr(
        inspection_api_routes,
        "run_school_safety_pipeline",
        fake_run_school_safety_pipeline,
    )

    client = TestClient(create_app())
    run_id = create_run(client)
    upload_response = client.post(
        f"/inspection-runs/{run_id}/sections/classroom/images",
        files={"file": ("classroom.png", png_bytes(), "image/png")},
    )
    assert upload_response.status_code == 201

    start_response = client.post(f"/inspection-runs/{run_id}/start", json={"generate_report": True})
    assert start_response.status_code == 202

    status_response = client.get(f"/inspection-runs/{run_id}")
    assert status_response.status_code == 200
    status_payload = status_response.json()

    assert status_payload["status"] == "failed"
    assert status_payload["errors"] == ["Pipeline failed. Check server logs for details."]
    assert "Internal failure" not in str(status_payload)
