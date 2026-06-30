"""Tests for provider wrapper behavior that should not call live model APIs.

These tests use small fake clients so retry behavior can be checked without
reading API keys, calling Gemini, calling OpenAI, or depending on network access.
"""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from school_safety_validator.inspection_data_models import (
    ImageAssessment,
    OfficerCommentAssessment,
    RecommendedAction,
    RiskAssessment,
    VisualFinding,
)
from school_safety_validator.inspection_runtime_settings import ValidatorSettings
from school_safety_validator.vision_model_provider_clients import call_gemini_with_retry


def sample_image_assessment() -> ImageAssessment:
    """Return the smallest valid ImageAssessment used by fake Gemini responses."""

    return ImageAssessment(
        image_name="image.jpg",
        category="classroom",
        visual_findings=[
            VisualFinding(
                issue_type="no visible issue",
                visibility="not_visible",
                severity="none",
                evidence="No visible issue is asserted in this fake response.",
                confidence=0.9,
            )
        ],
        risk_assessment=RiskAssessment(
            severity="none",
            requires_human_review=False,
            reason="Fake response for retry testing.",
        ),
        officer_comment_assessment=OfficerCommentAssessment(
            text="",
            status="missing",
            agreement="no_comment",
            reason="No officer comment is used in this fake response.",
            documentation_gap=False,
        ),
        recommended_action=RecommendedAction(
            action_type="none",
            action_text="No action in fake response.",
        ),
        uncertainties=[],
    )


class FakeGeminiModels:
    """Fake Gemini models endpoint with a configured sequence of outcomes."""

    def __init__(self, outcomes: list[object]):
        self.outcomes = outcomes
        self.call_count = 0

    async def generate_content(self, **kwargs):
        self.call_count += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(parsed=outcome)


class FakeModelClients:
    """Tiny stand-in for ModelClients with only the fields used by the retry code."""

    def __init__(self, fake_models: FakeGeminiModels):
        self.settings = ValidatorSettings(max_gemini_attempts=3, request_delay_seconds=0)
        self.gemini_client = SimpleNamespace(aio=SimpleNamespace(models=fake_models))

    async def wait_for_gemini_request_slot(self) -> None:
        return None


def write_fake_image(tmp_path: Path) -> Path:
    """Create a local file with a supported image suffix for provider wrapper tests."""

    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"fake image bytes")
    return image_path


def test_call_gemini_with_retry_retries_temporary_error_and_returns_parsed_response(tmp_path: Path) -> None:
    fake_assessment = sample_image_assessment()
    fake_models = FakeGeminiModels([RuntimeError("503 unavailable"), fake_assessment])

    result = asyncio.run(
        call_gemini_with_retry(
            FakeModelClients(fake_models),
            user_prompt="Assess this image.",
            image_path=write_fake_image(tmp_path),
            system_prompt="Use the schema.",
        )
    )

    assert result is fake_assessment
    assert fake_models.call_count == 2


def test_call_gemini_with_retry_does_not_retry_non_temporary_error(tmp_path: Path) -> None:
    fake_models = FakeGeminiModels([RuntimeError("400 bad request")])

    with pytest.raises(RuntimeError, match="400 bad request"):
        asyncio.run(
            call_gemini_with_retry(
                FakeModelClients(fake_models),
                user_prompt="Assess this image.",
                image_path=write_fake_image(tmp_path),
                system_prompt="Use the schema.",
            )
        )

    assert fake_models.call_count == 1
