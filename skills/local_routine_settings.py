from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from config import LOCAL_DATA_DIR


ROUTINE_SETTINGS_FILE = LOCAL_DATA_DIR / "routine_settings.json"

BRIGHTNESS_MINIMUM = 10
PERCENT_MAXIMUM = 100
VOLUME_MINIMUM = 0


class LocalRoutineSettingsError(RuntimeError):
    """Raised when private routine settings are unsafe or invalid."""


@dataclass(frozen=True)
class RoutineSettings:
    """Private per-routine runtime settings."""

    brightness: int | None = None
    volume: int | None = None


def _normalise_routine_id(value: str) -> str:
    """Normalise routine ids and spoken-ish config keys."""
    return "_".join(
        value.strip().casefold().replace("-", " ").split()
    )


def _validate_percent(
    value: object,
    *,
    label: str,
    minimum: int,
) -> int:
    """Validate one explicit percentage value."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise LocalRoutineSettingsError(
            f"{label} must be an integer percentage."
        )

    if value < minimum or value > PERCENT_MAXIMUM:
        raise LocalRoutineSettingsError(
            f"{label} must be between {minimum} and "
            f"{PERCENT_MAXIMUM}."
        )

    return value


def _parse_routine_settings(
    routine_id: str,
    raw_settings: object,
) -> RoutineSettings:
    """Parse one routine's private settings object."""
    if not isinstance(raw_settings, dict):
        raise LocalRoutineSettingsError(
            f"Routine settings for '{routine_id}' must be an object."
        )

    allowed_keys = {"brightness", "volume"}
    unknown_keys = set(raw_settings) - allowed_keys

    if unknown_keys:
        unknown_list = ", ".join(sorted(unknown_keys))
        raise LocalRoutineSettingsError(
            f"Unknown routine setting for '{routine_id}': "
            f"{unknown_list}."
        )

    brightness = None
    volume = None

    if "brightness" in raw_settings:
        brightness = _validate_percent(
            raw_settings["brightness"],
            label="Brightness",
            minimum=BRIGHTNESS_MINIMUM,
        )

    if "volume" in raw_settings:
        volume = _validate_percent(
            raw_settings["volume"],
            label="Volume",
            minimum=VOLUME_MINIMUM,
        )

    if brightness is None and volume is None:
        raise LocalRoutineSettingsError(
            f"Routine settings for '{routine_id}' must include "
            "brightness or volume."
        )

    return RoutineSettings(
        brightness=brightness,
        volume=volume,
    )


def load_routine_settings(
    *,
    settings_file: Path = ROUTINE_SETTINGS_FILE,
) -> dict[str, RoutineSettings]:
    """Load private routine settings from local JSON."""
    path = settings_file.expanduser()

    if not path.exists():
        return {}

    try:
        raw_payload = json.loads(
            path.read_text(encoding="utf-8")
        )
    except OSError as error:
        raise LocalRoutineSettingsError(
            f"Could not read routine settings: {error}"
        ) from error
    except json.JSONDecodeError as error:
        raise LocalRoutineSettingsError(
            "Routine settings are not valid JSON."
        ) from error

    if not isinstance(raw_payload, dict):
        raise LocalRoutineSettingsError(
            "Routine settings must be stored as a JSON object."
        )

    settings: dict[str, RoutineSettings] = {}

    for raw_routine_id, raw_settings in raw_payload.items():
        if not isinstance(raw_routine_id, str):
            raise LocalRoutineSettingsError(
                "Routine setting keys must be strings."
            )

        routine_id = _normalise_routine_id(raw_routine_id)

        if not routine_id:
            raise LocalRoutineSettingsError(
                "Routine setting keys cannot be empty."
            )

        if routine_id in settings:
            raise LocalRoutineSettingsError(
                f"Duplicate routine settings for '{routine_id}'."
            )

        settings[routine_id] = _parse_routine_settings(
            routine_id,
            raw_settings,
        )

    return settings


def get_routine_settings(
    routine_id: str,
    *,
    settings_file: Path = ROUTINE_SETTINGS_FILE,
) -> RoutineSettings:
    """Return private settings for one routine, or empty defaults."""
    normalised_routine_id = _normalise_routine_id(routine_id)

    if not normalised_routine_id:
        raise LocalRoutineSettingsError(
            "Routine id cannot be empty."
        )

    return load_routine_settings(
        settings_file=settings_file
    ).get(
        normalised_routine_id,
        RoutineSettings(),
    )