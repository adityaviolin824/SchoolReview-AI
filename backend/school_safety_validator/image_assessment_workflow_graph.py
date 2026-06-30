"""LangGraph workflow for assessing one inspection image."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .deterministic_assessment_rules import (
    build_human_review_item,
    finalize_human_review_fields,
    finalize_model_assessment,
    should_use_review_model,
)
from .image_privacy_preprocessing import blur_faces_in_image
from .inspection_data_models import ImageAssessmentState
from .inspection_runtime_settings import ValidatorSettings
from .vision_model_provider_clients import (
    ModelClients,
    call_gemini_with_retry,
    explain_gemini_error,
    run_openai_vision_assessment,
)


def build_image_assessment_graph(clients: ModelClients, settings: ValidatorSettings):
    """Compile the image-level graph for one configured workflow run."""

    async def privacy_preprocess_node(state: ImageAssessmentState) -> dict:
        """Create the privacy image before sending anything to a model."""

        blur_faces_in_image(state["raw_image_path"], state["privacy_image_path"])
        return {"privacy_image_path": state["privacy_image_path"]}

    async def run_primary_model_node(state: ImageAssessmentState) -> dict:
        """Try the primary Gemini model first."""

        raw_image_path = state["raw_image_path"]
        privacy_image_path = state["privacy_image_path"]
        officer_comment = state["officer_comment"]

        user_prompt = (
            "Assess this single school inspection image using only visible evidence.\n"
            f"CATEGORY: {state['category_name']}\n"
            f"IMAGE NAME: {raw_image_path.name}\n"
            f"OFFICER COMMENT: {officer_comment or '[blank]'}"
        )

        try:
            assessment = await call_gemini_with_retry(
                clients,
                user_prompt,
                privacy_image_path,
                state["system_prompt"],
            )
            assessment = finalize_model_assessment(
                assessment,
                raw_image_path.name,
                state["category_name"],
                officer_comment,
            )
            return {
                "primary_assessment": assessment,
                "final_assessment": assessment,
                "final_assessment_source": "primary_model",
                "primary_error": None,
            }
        except Exception as error:
            return {"primary_error": explain_gemini_error(error)}

    def route_review(state: ImageAssessmentState) -> str:
        """Route to review model only when the current final assessment needs it."""

        if state.get("status") == "failed":
            return "finalize_image"
        if state.get("final_assessment") and should_use_review_model(
            state["final_assessment"],
            settings.confidence_threshold,
        ):
            return "run_review_model"
        return "finalize_image"

    def route_after_primary(state: ImageAssessmentState) -> str:
        """Route to backup only when Gemini did not produce an assessment."""

        if state.get("final_assessment") is None:
            return "run_backup_model"
        return route_review(state)

    async def run_backup_model_node(state: ImageAssessmentState) -> dict:
        """Use OpenAI backup model when Gemini fails."""

        try:
            assessment = run_openai_vision_assessment(
                clients,
                settings.backup_vlm_model,
                state["category_name"],
                state["privacy_image_path"],
                state["officer_comment"],
                state["system_prompt"],
                "backup availability review",
            )
            assessment = finalize_model_assessment(
                assessment,
                state["raw_image_path"].name,
                state["category_name"],
                state["officer_comment"],
            )
            return {
                "backup_assessment": assessment,
                "final_assessment": assessment,
                "final_assessment_source": "backup_model",
                "backup_used": True,
            }
        except Exception as error:
            return {
                "status": "failed",
                "error": {"error_type": type(error).__name__, "error_message": str(error)[:1000]},
                "backup_used": True,
            }

    async def run_review_model_node(state: ImageAssessmentState) -> dict:
        """Use the review model when the first successful assessment needs deeper checking."""

        try:
            assessment = run_openai_vision_assessment(
                clients,
                settings.escalation_review_model,
                state["category_name"],
                state["privacy_image_path"],
                state["officer_comment"],
                state["system_prompt"],
                "independent review",
            )
            assessment = finalize_model_assessment(
                assessment,
                state["raw_image_path"].name,
                state["category_name"],
                state["officer_comment"],
            )
            return {
                "review_assessment": assessment,
                "final_assessment": assessment,
                "final_assessment_source": "review_model",
                "review_used": True,
                "review_error": None,
            }
        except Exception as error:
            review_reason = "Independent review failed; use the prior model assessment only as provisional."
            return {
                "review_error": str(error)[:1000],
                "review_used": True,
                "human_review_required": True,
                "human_review_status": "pending",
                "human_review_item": build_human_review_item(state, review_reason),
                "human_review_notes": review_reason,
            }

    def finalize_image_node(state: ImageAssessmentState) -> dict:
        """Finish the image state and queue human review if needed."""

        if state.get("status") == "failed":
            return {}
        return {"status": "completed", **finalize_human_review_fields(state)}

    graph = StateGraph(ImageAssessmentState)
    graph.add_node("privacy_preprocess", privacy_preprocess_node)
    graph.add_node("run_primary_model", run_primary_model_node)
    graph.add_node("run_backup_model", run_backup_model_node)
    graph.add_node("run_review_model", run_review_model_node)
    graph.add_node("finalize_image", finalize_image_node)

    graph.add_edge(START, "privacy_preprocess")
    graph.add_edge("privacy_preprocess", "run_primary_model")
    graph.add_conditional_edges("run_primary_model", route_after_primary)
    graph.add_conditional_edges("run_backup_model", route_review)
    graph.add_edge("run_review_model", "finalize_image")
    graph.add_edge("finalize_image", END)
    return graph.compile()
