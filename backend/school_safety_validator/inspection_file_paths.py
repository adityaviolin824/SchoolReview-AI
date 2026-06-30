"""Path helpers for category inputs and generated one-category outputs."""

from __future__ import annotations

from pathlib import Path

from .inspection_data_models import CategoryPaths
from .inspection_runtime_settings import CATEGORY_NAMES, ValidatorSettings


SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def build_category_paths(category_name: str, settings: ValidatorSettings) -> CategoryPaths:
    """Build all paths needed to run one configured category."""

    if category_name not in CATEGORY_NAMES:
        raise ValueError(f"Unknown category '{category_name}'. Expected one of: {CATEGORY_NAMES}")

    category_root = settings.input_root / category_name
    return {
        "images_path": category_root / "images",
        "comments_path": category_root / "comments",
        "overall_comment_path": category_root / "comments" / "overall_comments.txt",
        "privacy_images_path": settings.output_root / "privacy_images" / category_name,
        "model_output_path": settings.output_root / "model_outputs" / category_name,
    }


def discover_image_paths(images_path: Path) -> list[Path]:
    """Return supported category images in stable filename order."""

    if not images_path.exists():
        return []
    return sorted(
        path
        for path in images_path.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
    )


def ensure_output_dirs(category_paths: CategoryPaths, output_root: Path) -> None:
    """Create only generated-output directories for a category run."""

    category_paths["privacy_images_path"].mkdir(parents=True, exist_ok=True)
    category_paths["model_output_path"].mkdir(parents=True, exist_ok=True)
    (output_root / "category_outputs").mkdir(parents=True, exist_ok=True)


def image_mime_type(image_path: Path) -> str:
    """Return a provider-friendly MIME type for a supported image path."""

    if image_path.suffix.lower() in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if image_path.suffix.lower() == ".png":
        return "image/png"
    raise ValueError(f"Unsupported image extension: {image_path.suffix}")
