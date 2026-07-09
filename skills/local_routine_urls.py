from __future__ import annotations

import json
import webbrowser
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from config import LOCAL_DATA_DIR


ROUTINE_URL_GROUPS_FILE = LOCAL_DATA_DIR / "routine_url_groups.json"
MAX_URLS_PER_GROUP = 20
MAX_URL_LENGTH = 2048


class LocalRoutineUrlError(RuntimeError):
    """Raised when approved routine URL groups are unsafe or invalid."""


class LocalRoutineUrlNotConfiguredError(LocalRoutineUrlError):
    """Raised when a requested routine URL group is not configured."""


@dataclass(frozen=True)
class UrlGroupOpenReport:
    """Result of opening one approved routine URL group."""

    group_name: str
    opened_urls: tuple[str, ...]


def _normalise_group_name(value: str) -> str:
    """Normalise one routine URL group name."""
    return " ".join(value.strip().casefold().replace("-", " ").split())


def _validate_group_name(value: object) -> str:
    """Validate one configured URL group name."""
    if not isinstance(value, str):
        raise LocalRoutineUrlError(
            "Routine URL group names must be strings."
        )

    group_name = _normalise_group_name(value)

    if not group_name:
        raise LocalRoutineUrlError(
            "Routine URL group names cannot be empty."
        )

    return group_name


def _validate_https_url(value: object) -> str:
    """Accept only complete https URLs with no whitespace."""
    if not isinstance(value, str):
        raise LocalRoutineUrlError(
            "Routine URLs must be strings."
        )

    url = value.strip()

    if not url:
        raise LocalRoutineUrlError(
            "Routine URLs cannot be empty."
        )

    if len(url) > MAX_URL_LENGTH:
        raise LocalRoutineUrlError(
            "Routine URLs must be 2048 characters or shorter."
        )

    if any(character.isspace() for character in url):
        raise LocalRoutineUrlError(
            "Routine URLs cannot contain whitespace."
        )

    parsed = urlsplit(url)

    if parsed.scheme != "https" or not parsed.netloc:
        raise LocalRoutineUrlError(
            "Routine URLs must be complete https:// URLs."
        )

    if parsed.username or parsed.password:
        raise LocalRoutineUrlError(
            "Routine URLs cannot contain usernames or passwords."
        )

    return url


def _normalise_url_groups(
    raw_groups: Mapping[object, object],
) -> dict[str, tuple[str, ...]]:
    """Validate and normalise all configured routine URL groups."""
    groups: dict[str, tuple[str, ...]] = {}

    for raw_name, raw_urls in raw_groups.items():
        group_name = _validate_group_name(raw_name)

        if not isinstance(raw_urls, list):
            raise LocalRoutineUrlError(
                f"Routine URL group '{group_name}' must be a list."
            )

        if not raw_urls:
            raise LocalRoutineUrlError(
                f"Routine URL group '{group_name}' cannot be empty."
            )

        if len(raw_urls) > MAX_URLS_PER_GROUP:
            raise LocalRoutineUrlError(
                f"Routine URL group '{group_name}' cannot contain "
                f"more than {MAX_URLS_PER_GROUP} URLs."
            )

        validated_urls = tuple(
            _validate_https_url(raw_url)
            for raw_url in raw_urls
        )

        if group_name in groups:
            raise LocalRoutineUrlError(
                f"Duplicate routine URL group '{group_name}'."
            )

        groups[group_name] = validated_urls

    return groups


def load_approved_url_groups(
    *,
    url_file: Path = ROUTINE_URL_GROUPS_FILE,
) -> dict[str, tuple[str, ...]]:
    """Load approved routine URL groups from private local JSON."""
    path = url_file.expanduser()

    if not path.exists():
        return {}

    try:
        raw_payload = json.loads(
            path.read_text(encoding="utf-8")
        )
    except OSError as error:
        raise LocalRoutineUrlError(
            f"Could not read routine URL groups: {error}"
        ) from error
    except json.JSONDecodeError as error:
        raise LocalRoutineUrlError(
            "Routine URL groups are not valid JSON."
        ) from error

    if not isinstance(raw_payload, dict):
        raise LocalRoutineUrlError(
            "Routine URL groups must be stored as a JSON object."
        )

    return _normalise_url_groups(raw_payload)


def open_approved_url_group(
    group_name: str,
    *,
    url_file: Path = ROUTINE_URL_GROUPS_FILE,
    open_url: Callable[[str], bool] = webbrowser.open,
) -> UrlGroupOpenReport:
    """Open one private approved URL group in the default browser."""
    normalised_group_name = _normalise_group_name(group_name)
    groups = load_approved_url_groups(url_file=url_file)
    urls = groups.get(normalised_group_name)

    if urls is None:
        raise LocalRoutineUrlNotConfiguredError(
            f"Approved URL group '{normalised_group_name}' "
            "is not configured."
        )

    opened_urls: list[str] = []

    for url in urls:
        opened = open_url(url)

        if opened is False:
            raise LocalRoutineUrlError(
                f"Could not open approved URL: {url}"
            )

        opened_urls.append(url)

    return UrlGroupOpenReport(
        group_name=normalised_group_name,
        opened_urls=tuple(opened_urls),
    )