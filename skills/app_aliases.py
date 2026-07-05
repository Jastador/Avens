from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from skills.app_catalog import normalise_name


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ALIASES_FILE = (
    PROJECT_ROOT
    / "config"
    / "app_aliases.json"
)


def _normalise_alias_mapping(
    raw_aliases: Mapping[object, object],
) -> dict[str, str]:
    """Keep only non-empty alias-to-name mappings."""
    aliases: dict[str, str] = {}

    for raw_alias, raw_target in raw_aliases.items():
        if (
            not isinstance(raw_alias, str)
            or not isinstance(raw_target, str)
        ):
            continue

        alias = normalise_name(raw_alias)
        target = normalise_name(raw_target)

        if (
            not alias
            or not target
            or alias == target
        ):
            continue

        aliases[alias] = target

    return aliases


def load_app_aliases(
    alias_file: Path = APP_ALIASES_FILE,
) -> dict[str, str]:
    """Load local app aliases without treating config as executable code."""
    try:
        payload = alias_file.read_text(
            encoding="utf-8",
        )
        raw_aliases = json.loads(payload)
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(raw_aliases, dict):
        return {}

    return _normalise_alias_mapping(raw_aliases)


def resolve_alias_target(
    requested_name: str,
    *,
    aliases: Mapping[object, object] | None = None,
) -> str | None:
    """Return a configured exact target name for one spoken alias."""
    requested = normalise_name(requested_name)

    if not requested:
        return None

    available_aliases = (
        _normalise_alias_mapping(aliases)
        if aliases is not None
        else load_app_aliases()
    )

    target = available_aliases.get(requested)

    if target is None or target == requested:
        return None

    return target