"""Tests for the minimal FastAPI inspection-run boundary."""

from __future__ import annotations

import io
import os
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from school_safety_validator.api import fastapi_application
from school_safety_validator.api import inspection_api_routes
from school_safety_validator.api.fastapi_application import create_app
from school_safety_validator.inspection_data_models import SchoolInspectionResult


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


def test_api_run_upload_start_status_human_review_and_artifact(monkeypatch, tmp_path: Path) -> None:
    inspection_api_routes.RUNS.clear()
    monkeypatch.setattr(inspection_api_routes, "API_OUTPUT_ROOT", tmp_path)

    def fake_run_school_safety_pipeline(request, options):
        assert options.output_root == tmp_path
        assert options.run_id
        assert request.sections[0].images[0].image_path.is_relative_to(
            tmp_path / options.run_id / "uploads" / "classroom"
        )

        artifact = tmp_path / options.run_id / "final_reports" / "school_safety_final_report.md"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text("# Report", encoding="utf-8")
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
                "final_report:markdown_report": str(artifact),
            },
            warnings=["Section warning."],
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
        data={"comment": "Classroom image comment."},
    )
    assert upload_response.status_code == 201

    start_response = client.post(f"/inspection-runs/{run_id}/start", json={"generate_report": True})
    assert start_response.status_code == 202

    status_response = client.get(f"/inspection-runs/{run_id}")
    assert status_response.status_code == 200
    status_payload = status_response.json()

    assert status_payload["status"] == "completed_with_human_review_required"
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
    assert status_payload["artifacts"] == ["final_report:markdown_report"]

    image_response = client.get(f"/inspection-runs/{run_id}/human-review/review-1/image")
    assert image_response.status_code == 200
    assert image_response.content == png_bytes()

    unknown_image_response = client.get(f"/inspection-runs/{run_id}/human-review/unknown-review/image")
    assert unknown_image_response.status_code == 404

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

    artifact_response = client.get(f"/inspection-runs/{run_id}/artifacts/final_report:markdown_report")
    assert artifact_response.status_code == 200
    assert artifact_response.text == "# Report"


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

    assert status_payload["processed_sections"] == ["classroom", "washroom"]
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

    start_response = client.post(f"/inspection-runs/{run_id}/start", json={"generate_report": True})
    assert start_response.status_code == 202

    status_response = client.get(f"/inspection-runs/{run_id}")
    assert status_response.status_code == 200
    status_payload = status_response.json()

    assert status_payload["status"] == "failed"
    assert status_payload["errors"] == ["Pipeline failed. Check server logs for details."]
    assert "Internal failure" not in str(status_payload)
