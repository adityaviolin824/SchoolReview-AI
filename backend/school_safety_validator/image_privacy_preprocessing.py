"""Local privacy preprocessing for inspection images before model calls."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


FACE_CASCADE_PATH = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
EYE_CASCADE_PATH = Path(cv2.data.haarcascades) / "haarcascade_eye.xml"

face_cascade = cv2.CascadeClassifier(str(FACE_CASCADE_PATH))
eye_cascade = cv2.CascadeClassifier(str(EYE_CASCADE_PATH))


def blur_region(image: np.ndarray, x: int, y: int, width: int, height: int) -> None:
    """Blur a detected region in-place."""

    region = image[y : y + height, x : x + width]
    if region.size == 0:
        return

    kernel_width = max(25, (width // 3) | 1)
    kernel_height = max(25, (height // 3) | 1)
    image[y : y + height, x : x + width] = cv2.GaussianBlur(region, (kernel_width, kernel_height), 0)


def blur_faces_in_image(input_path: Path, output_path: Path) -> Path:
    """Detect likely faces/eyes, blur them, and save the privacy image."""

    image = cv2.imread(str(input_path))
    if image is None:
        raise ValueError(f"Unable to read image: {input_path}")

    gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray_image, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))

    for (x, y, width, height) in faces:
        blur_region(image, x, y, width, height)

    eyes = eye_cascade.detectMultiScale(gray_image, scaleFactor=1.1, minNeighbors=10, minSize=(12, 12))
    for (x, y, width, height) in eyes:
        expanded_x = max(0, x - width // 2)
        expanded_y = max(0, y - height // 2)
        expanded_width = min(image.shape[1] - expanded_x, width * 2)
        expanded_height = min(image.shape[0] - expanded_y, height * 2)
        blur_region(image, expanded_x, expanded_y, expanded_width, expanded_height)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), image)
    return output_path
