"""Tests for local privacy image preprocessing failure handling."""

from pathlib import Path

import numpy as np
import pytest

from school_safety_validator import image_privacy_preprocessing


class EmptyCascade:
    def detectMultiScale(self, *args, **kwargs):
        return []


def test_blur_faces_in_image_raises_when_privacy_image_write_fails(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(image_privacy_preprocessing.cv2, "imread", lambda path: np.zeros((5, 5, 3), dtype=np.uint8))
    monkeypatch.setattr(
        image_privacy_preprocessing.cv2,
        "cvtColor",
        lambda image, conversion_code: np.zeros((5, 5), dtype=np.uint8),
    )
    monkeypatch.setattr(image_privacy_preprocessing, "face_cascade", EmptyCascade())
    monkeypatch.setattr(image_privacy_preprocessing, "eye_cascade", EmptyCascade())
    monkeypatch.setattr(image_privacy_preprocessing.cv2, "imwrite", lambda path, image: False)

    with pytest.raises(ValueError, match="Unable to write privacy image"):
        image_privacy_preprocessing.blur_faces_in_image(
            tmp_path / "input.jpg",
            tmp_path / "privacy" / "input.jpg",
        )
