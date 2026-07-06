"""Configuration values for running one school inspection category.

The settings in this file replace the notebook's global constants for the
single-category workflow. Model clients are still created lazily so importing
the package never requires API keys.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ENV_FILE = BACKEND_ROOT / ".env"

CATEGORY_NAMES = [
    "ceiling",
    "classroom",
    "corridor",
    "electrical",
    "exterior",
    "fire_extinguisher",
    "staircase",
    "washroom",
    "other",
]


@dataclass(frozen=True)
class ValidatorSettings:
    """Runtime settings for the one-category inspection workflow."""

    input_root: Path = Path("sample_data") / "school"
    output_root: Path = Path("school_validation_outputs")
    primary_vlm_model: str = "gemini-3.1-flash-lite"
    backup_vlm_model: str = "gpt-4.1-mini"
    escalation_review_model: str = "gpt-4.1-mini"
    final_aggregation_model: str = "gpt-4.1-mini"
    final_report_model: str = "gpt-4.1-mini"
    max_gemini_attempts: int = 3
    request_delay_seconds: float = 5.0
    max_concurrent_requests: int = 1
    confidence_threshold: float = 0.60
    langsmith_project: str = "school-safety-validator"
    tracing_enabled: bool = True


def get_settings(
    input_root: Path | None = None,
    output_root: Path | None = None,
    tracing_enabled: bool | None = None,
    dotenv_override: bool = False,
) -> ValidatorSettings:
    """Load environment defaults and return workflow settings."""

    load_dotenv(dotenv_path=BACKEND_ENV_FILE, override=dotenv_override)

    settings = ValidatorSettings(
        langsmith_project=os.getenv("LANGSMITH_PROJECT", "school-safety-validator"),
        tracing_enabled=os.getenv("LANGSMITH_TRACING", "true").lower() not in {"0", "false", "no"},
    )
    if input_root is not None:
        settings = replace(settings, input_root=input_root)
    if output_root is not None:
        settings = replace(settings, output_root=output_root)
    if tracing_enabled is not None:
        settings = replace(settings, tracing_enabled=tracing_enabled)
    return settings


def require_model_api_keys() -> tuple[str, str]:
    """Return required provider API keys or raise a clear configuration error."""

    missing = [name for name in ("GEMINI_API_KEY", "OPENAI_API_KEY") if not os.getenv(name)]
    if missing:
        raise RuntimeError(
            "Missing required environment variables: "
            + ", ".join(missing)
            + ". Add them to your shell environment or backend/.env."
        )
    return os.environ["GEMINI_API_KEY"], os.environ["OPENAI_API_KEY"]
