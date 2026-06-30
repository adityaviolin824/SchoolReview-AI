"""Gemini and OpenAI model-client wrappers for image assessment."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path

from google import genai
from google.genai import types
from langsmith import wrappers as langsmith_wrappers
from langsmith.wrappers import wrap_openai
from openai import OpenAI

from .inspection_data_models import ImageAssessment
from .inspection_file_paths import image_mime_type
from .inspection_runtime_settings import ValidatorSettings, require_model_api_keys
from .structured_model_response_parsing import image_to_data_url, parse_openai_structured_response


@dataclass
class ModelClients:
    """Wrapped provider clients plus local Gemini rate-limit state."""

    gemini_client: object
    openai_client: OpenAI
    settings: ValidatorSettings
    _gemini_lock: asyncio.Lock
    _last_gemini_request_time: float = 0.0

    @classmethod
    def from_env(cls, settings: ValidatorSettings) -> "ModelClients":
        """Create wrapped Gemini and OpenAI clients from environment variables."""

        gemini_api_key, openai_api_key = require_model_api_keys()
        return cls(
            gemini_client=langsmith_wrappers.wrap_gemini(genai.Client(api_key=gemini_api_key)),
            openai_client=wrap_openai(OpenAI(api_key=openai_api_key)),
            settings=settings,
            _gemini_lock=asyncio.Lock(),
        )

    async def wait_for_gemini_request_slot(self) -> None:
        """Pause until the next Gemini request is allowed by the local delay."""

        async with self._gemini_lock:
            elapsed = time.monotonic() - self._last_gemini_request_time
            wait_seconds = max(0, self.settings.request_delay_seconds - elapsed)
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
            self._last_gemini_request_time = time.monotonic()


def explain_gemini_error(error: Exception) -> str:
    """Convert common Gemini failures into short messages for logs and JSON."""

    error_text = str(error)
    if "429" in error_text or "RESOURCE_EXHAUSTED" in error_text:
        return "Gemini quota or rate limit was hit."
    if "503" in error_text or "UNAVAILABLE" in error_text:
        return "Gemini model is temporarily unavailable or under high demand."
    if "timeout" in error_text.lower():
        return "Gemini request timed out."
    if "500" in error_text:
        return "Gemini returned a temporary server error."
    return "Gemini request failed."


def should_retry_gemini_error(error: Exception) -> bool:
    """Retry only temporary-looking Gemini failures."""

    error_text = str(error).lower()
    retry_markers = ["429", "resource_exhausted", "503", "unavailable", "timeout", "temporarily", "500"]
    return any(marker in error_text for marker in retry_markers)


async def call_gemini_with_retry(
    clients: ModelClients,
    user_prompt: str,
    image_path: Path,
    system_prompt: str,
) -> ImageAssessment:
    """Call Gemini with structured JSON output and bounded retries."""

    image_part = types.Part.from_bytes(data=image_path.read_bytes(), mime_type=image_mime_type(image_path))

    for attempt in range(clients.settings.max_gemini_attempts):
        try:
            await clients.wait_for_gemini_request_slot()
            response = await clients.gemini_client.aio.models.generate_content(
                model=clients.settings.primary_vlm_model,
                contents=[user_prompt, image_part],
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=ImageAssessment,
                    max_output_tokens=1200,
                    temperature=0.0,
                ),
            )
            return response.parsed
        except Exception as error:
            is_last_attempt = attempt == clients.settings.max_gemini_attempts - 1
            if not should_retry_gemini_error(error) or is_last_attempt:
                raise
            await asyncio.sleep(clients.settings.request_delay_seconds * (2**attempt))

    raise RuntimeError("Gemini request failed without returning an assessment.")


def run_openai_vision_assessment(
    clients: ModelClients,
    model_name: str,
    category_name: str,
    image_path: Path,
    officer_comment: str,
    system_prompt: str,
    purpose: str,
) -> ImageAssessment:
    """Run an OpenAI vision model and parse the response into ImageAssessment."""

    review_instruction = ""
    if purpose == "independent review":
        review_instruction = (
            "\nAs reviewer, keep assessing the image normally even if the officer comment is messy or unrelated. "
            "Set human review only when uncertainty, insufficient evidence, contradiction, "
            "or qualified interpretation remains after your review."
        )

    prompt = (
        f"{system_prompt}{review_instruction}\n\n"
        f"TASK: {purpose}\n"
        "Assess this single school inspection image using the schema exactly.\n"
        f"CATEGORY: {category_name}\n"
        f"IMAGE NAME: {image_path.name}\n"
        f"OFFICER COMMENT: {officer_comment or '[blank]'}\n"
        "Return JSON that matches the required schema exactly."
    )

    response = parse_openai_structured_response(
        clients.openai_client,
        model=model_name,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": image_to_data_url(image_path)},
                ],
            }
        ],
        text_format=ImageAssessment,
    )
    return response.output_parsed
