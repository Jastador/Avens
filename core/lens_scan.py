"""Temporary online visual search for Avens Lens Scan.

This module only runs after an explicit user request. It crops one in-memory
camera frame, uploads that crop temporarily for SerpApi Google Lens, returns a
likely match, and deletes the Cloudinary asset in a finally block.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import os
from typing import Any, Final
import uuid

import cv2
import numpy as np
import requests


SERPAPI_SEARCH_URL: Final = "https://serpapi.com/search"

SCAN_CROP_WIDTH_RATIO: Final = 0.72
SCAN_CROP_HEIGHT_RATIO: Final = 0.86
MAX_IMAGE_SIDE: Final = 1024
JPEG_QUALITY: Final = 90
REQUEST_TIMEOUT_SECONDS: Final = 45


@dataclass(frozen=True)
class LensMatch:
    """One cautious visual-search result suitable for Avens to speak."""

    title: str
    source: str
    link: str | None
    exact_match: bool = False


class LensScanError(RuntimeError):
    """Raised when temporary upload or Google Lens search cannot complete."""


def is_lens_scan_configured() -> bool:
    """Return whether all required online Lens credentials are present."""
    required_names = (
        "SERPAPI_API_KEY",
        "CLOUDINARY_CLOUD_NAME",
        "CLOUDINARY_API_KEY",
        "CLOUDINARY_API_SECRET",
    )

    return all(os.getenv(name, "").strip() for name in required_names)


def scan_frame_with_google_lens(frame: np.ndarray) -> LensMatch:
    """Run one explicit online visual search and remove the temporary upload."""
    if frame is None or frame.size == 0:
        raise LensScanError("No usable camera frame was available.")

    _validate_configuration()

    public_id: str | None = None

    try:
        prepared_frame = _prepare_scan_frame(frame)
        image_data_uri = _encode_as_data_uri(prepared_frame)

        public_id, image_url = _upload_temporary_image(image_data_uri)

        result_data = _request_google_lens(image_url)

        return _select_best_match(result_data)

    finally:
        if public_id:
            _delete_temporary_image(public_id)


def format_lens_match_for_speech(match: LensMatch) -> str:
    """Turn a visual-search result into a careful spoken answer."""
    if match.exact_match:
        prefix = "Google Lens found an exact visual match"
    else:
        prefix = "Google Lens found a close visual match"

    if match.source:
        return (
            f"{prefix}: {match.title}. "
            f"Source: {match.source}. "
            "Treat the exact model as unconfirmed."
        )

    return (
        f"{prefix}: {match.title}. "
        "Treat the exact model as unconfirmed."
    )

def _validate_configuration() -> None:
    """Fail clearly instead of leaking a half-configured API exception."""
    if is_lens_scan_configured():
        return

    raise LensScanError(
        "Lens Scan is not configured. Check the SerpApi and Cloudinary "
        "variables in your .env file."
    )


def _prepare_scan_frame(frame: np.ndarray) -> np.ndarray:
    """Crop the centre region, then resize for a practical upload size."""
    height, width = frame.shape[:2]

    crop_width = max(1, int(width * SCAN_CROP_WIDTH_RATIO))
    crop_height = max(1, int(height * SCAN_CROP_HEIGHT_RATIO))

    left = max(0, (width - crop_width) // 2)
    top = max(0, (height - crop_height) // 2)

    cropped = frame[
        top:top + crop_height,
        left:left + crop_width,
    ].copy()

    crop_height, crop_width = cropped.shape[:2]
    longest_side = max(crop_height, crop_width)

    if longest_side <= MAX_IMAGE_SIDE:
        return cropped

    scale = MAX_IMAGE_SIDE / longest_side

    return cv2.resize(
        cropped,
        (
            int(crop_width * scale),
            int(crop_height * scale),
        ),
        interpolation=cv2.INTER_AREA,
    )


def _encode_as_data_uri(frame: np.ndarray) -> str:
    """Encode an in-memory BGR image without writing a file."""
    success, encoded = cv2.imencode(
        ".jpg",
        frame,
        [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY],
    )

    if not success:
        raise LensScanError("The camera crop could not be encoded.")

    image_base64 = base64.b64encode(encoded.tobytes()).decode("ascii")

    return f"data:image/jpeg;base64,{image_base64}"


def _upload_temporary_image(image_data_uri: str) -> tuple[str, str]:
    """Upload one temporary image and return its Cloudinary ID and URL."""
    try:
        import cloudinary
        import cloudinary.uploader
    except ImportError as error:
        raise LensScanError(
            "Cloudinary SDK is not installed in this virtual environment."
        ) from error

    cloudinary.config(
        cloud_name=os.environ["CLOUDINARY_CLOUD_NAME"],
        api_key=os.environ["CLOUDINARY_API_KEY"],
        api_secret=os.environ["CLOUDINARY_API_SECRET"],
        secure=True,
    )

    upload_result = cloudinary.uploader.upload(
        image_data_uri,
        folder="avens_lens_temporary",
        public_id=f"scan_{uuid.uuid4().hex}",
        resource_type="image",
        overwrite=False,
        unique_filename=False,
        tags=["avens_lens_temporary"],
    )

    public_id = str(upload_result.get("public_id", "")).strip()
    secure_url = str(upload_result.get("secure_url", "")).strip()

    if not public_id or not secure_url:
        raise LensScanError(
            "Cloudinary upload completed without a usable image URL."
        )

    print("☁️ Temporary Lens image uploaded.")

    return public_id, secure_url


def _request_google_lens(image_url: str) -> dict[str, Any]:
    """Ask SerpApi for fresh Google Lens visual matches."""
    params = {
        "engine": "google_lens",
        "url": image_url,
        "type": "all",
        "auto_crop": "true",
        "hl": "en",
        "country": "in",
        "safe": "active",
        "no_cache": "true",
        "api_key": os.environ["SERPAPI_API_KEY"],
    }

    try:
        response = requests.get(
            SERPAPI_SEARCH_URL,
            params=params,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.Timeout as error:
        raise LensScanError(
            "Google Lens search took too long to respond."
        ) from error
    except requests.RequestException as error:
        raise LensScanError(
            "Google Lens search could not be reached."
        ) from error

    try:
        data = response.json()
    except ValueError as error:
        raise LensScanError(
            "Google Lens returned an unreadable response."
        ) from error

    if response.status_code != 200:
        message = str(data.get("error", "")).strip()

        raise LensScanError(
            message or f"Google Lens returned HTTP {response.status_code}."
        )

    if data.get("error"):
        raise LensScanError(str(data["error"]))

    return data


def _select_best_match(data: dict[str, Any]) -> LensMatch:
    """Choose the strongest available visual result without overclaiming."""
    visual_matches = data.get("visual_matches", [])

    if isinstance(visual_matches, list):
        for item in visual_matches:
            if not isinstance(item, dict):
                continue

            title = _clean_text(item.get("title", ""))

            if not title:
                continue

            source = _clean_text(item.get("source", ""))
            link = _clean_text(item.get("link", "")) or None
            exact_match = bool(item.get("exact_matches", False))

            return LensMatch(
                title=title,
                source=source,
                link=link,
                exact_match=exact_match,
            )

    related_content = data.get("related_content", [])

    if isinstance(related_content, list):
        for item in related_content:
            if not isinstance(item, dict):
                continue

            query = _clean_text(item.get("query", ""))

            if query:
                return LensMatch(
                    title=query,
                    source="Google Lens related content",
                    link=_clean_text(item.get("link", "")) or None,
                    exact_match=False,
                )

    raise LensScanError(
        "Google Lens did not return a confident visual match."
    )


def _delete_temporary_image(public_id: str) -> None:
    """Delete the uploaded image even after failed Lens searches."""
    try:
        import cloudinary.uploader

        delete_result = cloudinary.uploader.destroy(
            public_id,
            resource_type="image",
            invalidate=True,
        )

        result = str(delete_result.get("result", "")).casefold()

        if result == "ok":
            print("🗑️ Temporary Lens image deleted.")
        else:
            print(
                "⚠️ Temporary Lens image deletion returned:",
                delete_result,
            )

    except Exception as error:
        print(f"⚠️ Could not delete temporary Lens image: {error}")


def _clean_text(value: object) -> str:
    """Keep external search text compact before Avens speaks it."""
    text = " ".join(str(value or "").split())

    if len(text) <= 220:
        return text

    shortened = text[:220].rsplit(" ", 1)[0]

    return f"{shortened}..."