from __future__ import annotations

import math
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar


MASTER_VOLUME_MINIMUM = 0
MASTER_VOLUME_MAXIMUM = 100
DEFAULT_VOLUME_STEP = 10

BRIGHTNESS_MINIMUM = 10
BRIGHTNESS_MAXIMUM = 100
DEFAULT_BRIGHTNESS_STEP = 10
READING_MODE_BRIGHTNESS = 30
PRIMARY_DISPLAY_INDEX = 0

NIGHT_LIGHT_SETTINGS_URI = "ms-settings:nightlight"


class SystemControlError(RuntimeError):
    """Raised when a safe Windows system control cannot be completed."""


@dataclass(frozen=True)
class VolumeState:
    """Current Windows master-volume state."""

    level: int
    muted: bool


@dataclass(frozen=True)
class BrightnessState:
    """Current built-in-display brightness state."""

    level: int


@dataclass(frozen=True)
class ReadingModeResult:
    """Result of setting a reading-friendly brightness and opening Settings."""

    brightness: BrightnessState
    night_light_settings_opened: bool


_ReturnValue = TypeVar("_ReturnValue")


def _validate_percentage(
    value: int,
    *,
    minimum: int,
    label: str,
) -> int:
    """Validate one integer percentage within a declared safe range."""
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
    ):
        raise SystemControlError(
            f"{label} must be a whole-number percentage."
        )

    if value < minimum or value > 100:
        raise SystemControlError(
            f"{label} must be between {minimum} and 100."
        )

    return value


def _normalise_observed_percentage(
    value: object,
    *,
    label: str,
) -> int:
    """Convert one hardware-reported percentage into a safe integer."""
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
    ):
        raise SystemControlError(
            f"{label} returned an invalid percentage."
        )

    numeric_value = float(value)

    if not math.isfinite(numeric_value):
        raise SystemControlError(
            f"{label} returned an invalid percentage."
        )

    return max(
        0,
        min(
            100,
            int(round(numeric_value)),
        ),
    )


def _normalise_volume_scalar(value: object) -> int:
    """Convert a Windows audio scalar from 0.0–1.0 into 0–100."""
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
    ):
        raise SystemControlError(
            "Windows audio returned an invalid volume value."
        )

    scalar = float(value)

    if not math.isfinite(scalar):
        raise SystemControlError(
            "Windows audio returned an invalid volume value."
        )

    return max(
        MASTER_VOLUME_MINIMUM,
        min(
            MASTER_VOLUME_MAXIMUM,
            int(round(scalar * 100)),
        ),
    )


def _with_default_volume_endpoint(
    operation: Callable[[object], _ReturnValue],
) -> _ReturnValue:
    """Run one operation against the Windows default audio endpoint."""
    try:
        import pythoncom
        from pycaw.pycaw import AudioUtilities
    except Exception as error:
        raise SystemControlError(
            f"Windows audio controls are unavailable: {error}"
        ) from error

    initialized = False

    try:
        pythoncom.CoInitialize()
        initialized = True

        device = AudioUtilities.GetSpeakers()
        endpoint = device.EndpointVolume

        return operation(endpoint)
    except SystemControlError:
        raise
    except Exception as error:
        raise SystemControlError(
            f"Could not access Windows master volume: {error}"
        ) from error
    finally:
        if initialized:
            pythoncom.CoUninitialize()


def _with_volume_endpoint(
    operation: Callable[[object], _ReturnValue],
    *,
    endpoint: object | None,
) -> _ReturnValue:
    """Use an injected endpoint in tests or the real default endpoint."""
    if endpoint is not None:
        return operation(endpoint)

    return _with_default_volume_endpoint(operation)


def _read_volume_state(endpoint: object) -> VolumeState:
    """Read one exact endpoint volume and mute state."""
    volume_scalar = endpoint.GetMasterVolumeLevelScalar()
    muted = bool(endpoint.GetMute())

    return VolumeState(
        level=_normalise_volume_scalar(volume_scalar),
        muted=muted,
    )


def get_master_volume(
    *,
    endpoint: object | None = None,
) -> VolumeState:
    """Read the current Windows master-volume state."""
    return _with_volume_endpoint(
        _read_volume_state,
        endpoint=endpoint,
    )


def set_master_volume(
    level: int,
    *,
    endpoint: object | None = None,
) -> VolumeState:
    """Set the exact Windows master-volume percentage without unmuting."""

    def operation(current_endpoint: object) -> VolumeState:
        current_endpoint.SetMasterVolumeLevelScalar(
            level / 100.0,
            None,
        )
        return _read_volume_state(current_endpoint)

    requested_level = _validate_percentage(
        level,
        minimum=MASTER_VOLUME_MINIMUM,
        label="Volume",
    )

    return _with_volume_endpoint(
        operation,
        endpoint=endpoint,
    )


def adjust_master_volume(
    change: int,
    *,
    endpoint: object | None = None,
) -> VolumeState:
    """Adjust master volume by a signed amount and clamp it safely."""
    if (
        not isinstance(change, int)
        or isinstance(change, bool)
        or change == 0
    ):
        raise SystemControlError(
            "Volume adjustment must be a non-zero whole number."
        )

    def operation(current_endpoint: object) -> VolumeState:
        current_state = _read_volume_state(current_endpoint)
        requested_level = max(
            MASTER_VOLUME_MINIMUM,
            min(
                MASTER_VOLUME_MAXIMUM,
                current_state.level + change,
            ),
        )

        current_endpoint.SetMasterVolumeLevelScalar(
            requested_level / 100.0,
            None,
        )

        return _read_volume_state(current_endpoint)

    return _with_volume_endpoint(
        operation,
        endpoint=endpoint,
    )


def set_master_mute(
    muted: bool,
    *,
    endpoint: object | None = None,
) -> VolumeState:
    """Set the exact Windows master mute state."""
    if not isinstance(muted, bool):
        raise SystemControlError(
            "Mute state must be true or false."
        )

    def operation(current_endpoint: object) -> VolumeState:
        current_endpoint.SetMute(muted, None)
        return _read_volume_state(current_endpoint)

    return _with_volume_endpoint(
        operation,
        endpoint=endpoint,
    )


def _get_brightness_api(
    brightness_api: object | None,
) -> object:
    """Return an injected brightness API or load the Windows library."""
    if brightness_api is not None:
        return brightness_api

    try:
        import screen_brightness_control as sbc
    except Exception as error:
        raise SystemControlError(
            f"Brightness controls are unavailable: {error}"
        ) from error

    return sbc


def _read_primary_brightness(
    brightness_api: object,
) -> BrightnessState:
    """Read only the built-in primary display brightness."""
    try:
        raw_levels = brightness_api.get_brightness(
            display=PRIMARY_DISPLAY_INDEX,
        )
    except Exception as error:
        raise SystemControlError(
            f"Could not read built-in display brightness: {error}"
        ) from error

    if isinstance(raw_levels, (list, tuple)):
        if len(raw_levels) != 1:
            raise SystemControlError(
                "Built-in display brightness returned an unexpected result."
            )

        raw_level = raw_levels[0]
    else:
        raw_level = raw_levels

    return BrightnessState(
        level=_normalise_observed_percentage(
            raw_level,
            label="Built-in display brightness",
        )
    )


def get_primary_brightness(
    *,
    brightness_api: object | None = None,
) -> BrightnessState:
    """Read the built-in display brightness without touching externals."""
    return _read_primary_brightness(
        _get_brightness_api(brightness_api)
    )


def set_primary_brightness(
    level: int,
    *,
    brightness_api: object | None = None,
) -> BrightnessState:
    """Set built-in display brightness while keeping a visible floor."""
    requested_level = _validate_percentage(
        level,
        minimum=BRIGHTNESS_MINIMUM,
        label="Brightness",
    )
    api = _get_brightness_api(brightness_api)

    try:
        api.set_brightness(
            requested_level,
            display=PRIMARY_DISPLAY_INDEX,
        )
    except Exception as error:
        raise SystemControlError(
            f"Could not set built-in display brightness: {error}"
        ) from error

    return _read_primary_brightness(api)


def adjust_primary_brightness(
    change: int,
    *,
    brightness_api: object | None = None,
) -> BrightnessState:
    """Adjust built-in display brightness without dropping below 10%."""
    if (
        not isinstance(change, int)
        or isinstance(change, bool)
        or change == 0
    ):
        raise SystemControlError(
            "Brightness adjustment must be a non-zero whole number."
        )

    api = _get_brightness_api(brightness_api)
    current_state = _read_primary_brightness(api)

    requested_level = max(
        BRIGHTNESS_MINIMUM,
        min(
            BRIGHTNESS_MAXIMUM,
            current_state.level + change,
        ),
    )

    return set_primary_brightness(
        requested_level,
        brightness_api=api,
    )


def _open_windows_uri(uri: str) -> None:
    """Open one fixed Windows Settings URI without shell execution."""
    startfile = getattr(os, "startfile", None)

    if startfile is None:
        raise SystemControlError(
            "Windows Settings URIs are unavailable on this system."
        )

    startfile(uri)


def open_night_light_settings(
    *,
    open_uri: Callable[[str], None] = _open_windows_uri,
) -> None:
    """Open the official Windows Night Light Settings page."""
    try:
        open_uri(NIGHT_LIGHT_SETTINGS_URI)
    except SystemControlError:
        raise
    except Exception as error:
        raise SystemControlError(
            f"Could not open Night Light Settings: {error}"
        ) from error


def start_reading_mode(
    *,
    brightness_api: object | None = None,
    open_uri: Callable[[str], None] = _open_windows_uri,
) -> ReadingModeResult:
    """Set reading brightness and open Night Light Settings for the user."""
    brightness = set_primary_brightness(
        READING_MODE_BRIGHTNESS,
        brightness_api=brightness_api,
    )
    open_night_light_settings(open_uri=open_uri)

    return ReadingModeResult(
        brightness=brightness,
        night_light_settings_opened=True,
    )