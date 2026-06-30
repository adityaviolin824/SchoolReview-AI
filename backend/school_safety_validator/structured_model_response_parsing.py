"""Provider parsing helpers shared by model clients."""

from __future__ import annotations

import base64
import warnings
from pathlib import Path

from openai import OpenAI

from .inspection_file_paths import image_mime_type


def image_to_data_url(image_path: Path) -> str:
    """Encode an image as a data URL for OpenAI vision input."""

    image_base64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    return f"data:{image_mime_type(image_path)};base64,{image_base64}"


def parse_openai_structured_response(openai_client: OpenAI, **kwargs):
    """Call OpenAI structured parsing while hiding known Pydantic serializer noise."""

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"Pydantic serializer warnings.*",
            category=UserWarning,
        )
        return openai_client.responses.parse(**kwargs)
