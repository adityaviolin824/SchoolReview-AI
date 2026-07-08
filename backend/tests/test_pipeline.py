from pathlib import Path

import pytest

from school_safety_validator import pipeline
from school_safety_validator.inspection_data_models import (
    CategoryFinalFeedback,
    FinalInspectionLLMReport,
    InspectionImageInput,
    InspectionSectionInput,
    PipelineExecutionOptions,
    SchoolInspectionRequest,
    SchoolMetadata,
)
from school_safety_validator.pipeline import (
    load_school_inspection_request_json,
    materialize_request_dataset,
    run_school_safety_pipeline,
)


def request_with_image(image_path: Path) -> SchoolInspectionRequest:
    return SchoolInspectionRequest(
        school=SchoolMetadata(
            name="Example Government School",
            inspection_date="2026-06-30",
            location="Example District, India",
        ),
        sections=[
            InspectionSectionInput(
                section_name="classroom",
                section_comment="Classroom section comment.",
                images=[InspectionImageInput(image_path=image_path, comment="Classroom image comment.")],
            )
        ],
    )


def final_report() -> FinalInspectionLLMReport:
    return FinalInspectionLLMReport(
        overall_status="maintenance_attention_required",
        provisional=False,
        executive_summary="Visible classroom maintenance attention is required.",
        key_risks=["Classroom maintenance concern."],
        category_feedback=[
            CategoryFinalFeedback(
                category="classroom",
                status="attention_required",
                priority="medium",
                short_summary="Classroom needs maintenance attention.",
                main_concerns=["Visible classroom concern."],
                recommended_next_steps=["Review classroom maintenance."],
                evidence_refs=["classroom_001.jpg"],
            )
        ],
        immediate_actions=[],
        maintenance_actions=["Review classroom maintenance."],
        documentation_followups=[],
        human_review_notes=[],
        limitations=[],
    )


class FakeClients:
    openai_client = object()


def test_load_school_inspection_request_json_resolves_relative_image_paths(tmp_path: Path) -> None:
    image_path = tmp_path / "school" / "classroom" / "images" / "classroom_001.jpg"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"fake image")
    request_path = tmp_path / "request.json"
    request_path.write_text(
        """
        {
          "school": {
            "name": "Example Government School",
            "inspection_date": "2026-06-30",
            "location": "Example District, India"
          },
          "sections": [
            {
              "section_name": "classroom",
              "section_comment": "Classroom section comment.",
              "images": [
                {
                  "image_path": "school/classroom/images/classroom_001.jpg",
                  "comment": "Classroom image comment."
                }
              ]
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    request = load_school_inspection_request_json(request_path)

    assert request.sections[0].images[0].image_path == image_path.resolve()


def test_materialize_request_dataset_copies_images_and_comments(tmp_path: Path) -> None:
    source_image = tmp_path / "source" / "classroom_001.jpg"
    source_image.parent.mkdir()
    source_image.write_bytes(b"fake image")
    request = request_with_image(source_image)
    input_root = tmp_path / "generated_input"

    warnings = materialize_request_dataset(request, input_root)

    assert warnings == []
    assert (input_root / "classroom" / "images" / "classroom_001.jpg").read_bytes() == b"fake image"
    assert (input_root / "classroom" / "comments" / "classroom_001.txt").read_text(encoding="utf-8") == (
        "Classroom image comment."
    )
    assert (input_root / "classroom" / "comments" / "overall_comments.txt").read_text(encoding="utf-8") == (
        "Classroom section comment."
    )


def test_materialize_request_dataset_rejects_unknown_section(tmp_path: Path) -> None:
    source_image = tmp_path / "source" / "image.jpg"
    source_image.parent.mkdir()
    source_image.write_bytes(b"fake image")
    request = SchoolInspectionRequest(
        school=SchoolMetadata(name="School", inspection_date="2026-06-30", location="District"),
        sections=[
            InspectionSectionInput(
                section_name="unknown_section",
                images=[InspectionImageInput(image_path=source_image)],
            )
        ],
    )

    with pytest.raises(ValueError, match="Unknown section_name"):
        materialize_request_dataset(request, tmp_path / "generated_input")


def test_run_school_safety_pipeline_orchestrates_existing_components(monkeypatch, tmp_path: Path) -> None:
    source_image = tmp_path / "source" / "classroom_001.jpg"
    source_image.parent.mkdir()
    source_image.write_bytes(b"fake image")
    request = request_with_image(source_image)
    output_root = tmp_path / "outputs"
    observed = {}

    async def fake_run_all_category_inspections(section_names, settings, clients):
        observed["section_names"] = section_names
        observed["input_root"] = settings.input_root
        observed["output_root"] = settings.output_root
        observed["clients"] = clients
        return {
            "run_category_names": ["classroom"],
            "processed_categories": ["classroom"],
            "failed_categories": [],
            "not_inspected_categories": [],
            "saved_run_summary_file": str(
                output_root / "test-run" / "run_outputs" / "all_category_run_summary.json"
            ),
            "saved_category_output_files": {
                "classroom": str(
                    output_root / "test-run" / "category_outputs" / "classroom_image_assessments.json"
                )
            },
            "all_human_review_queue": [],
            "category_summaries": {
                "classroom": {
                    "category_status": "attention_required",
                    "image_count": 1,
                    "human_review_required": False,
                }
            },
        }

    def fake_run_final_report_generation(settings, openai_client, full_run_state):
        observed["report_input_state"] = full_run_state
        observed["openai_client"] = openai_client
        return {
            "aggregation": {
                "final_report": final_report(),
                "global_rollup": {
                    "processed_categories": ["classroom"],
                    "not_inspected_categories": ["ceiling"],
                    "total_images": 1,
                    "human_review_required": False,
                },
                "paths": {
                    "final_aggregation_output": (
                        output_root / "test-run" / "final_reports" / "final_aggregation_output.json"
                    )
                },
            },
            "report_paths": {
                "markdown_report": (
                    output_root / "test-run" / "final_reports" / "school_safety_final_report.md"
                ),
                "html_report": output_root / "test-run" / "final_reports" / "school_safety_final_report.html",
            },
        }

    monkeypatch.setattr(pipeline, "run_all_category_inspections", fake_run_all_category_inspections)
    monkeypatch.setattr(pipeline, "run_final_report_generation", fake_run_final_report_generation)

    fake_clients = FakeClients()
    result = run_school_safety_pipeline(
        request,
        PipelineExecutionOptions(output_root=output_root, run_id="test-run"),
        clients=fake_clients,
    )

    assert result.pipeline_status == "completed"
    assert result.overall_status == "maintenance_attention_required"
    assert result.processed_sections == ["classroom"]
    assert result.not_inspected_sections == ["ceiling"]
    assert observed["section_names"] == ["classroom"]
    assert observed["input_root"] == (output_root.resolve() / "test-run" / "pipeline_inputs")
    assert observed["output_root"] == output_root.resolve() / "test-run"
    assert observed["clients"] is fake_clients
    assert observed["openai_client"] is fake_clients.openai_client
    assert result.artifact_paths["final_report:markdown_report"].endswith("school_safety_final_report.md")
