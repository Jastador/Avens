from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final


DEFAULT_DISCORD_VOICE_CONFIG_PATH: Final = Path(
    "local_data/discord_voice_channels.json"
)


class DiscordVoiceConfigError(ValueError):
    """Raised when private Discord voice config is invalid."""


@dataclass(frozen=True)
class DiscordVoiceTarget:
    """One approved Discord voice target."""

    alias: str
    server_name: str
    channel_name: str
    quick_switcher_query: str | None = None


def _normalise_alias(value: str) -> str:
    """Normalise one configured alias without guessing."""
    return " ".join(
        value.strip().casefold().replace("-", " ").split()
    )


def _read_config_object(path: Path) -> dict[str, object]:
    """Read one Discord voice config JSON object."""
    try:
        raw_config = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as error:
        raise DiscordVoiceConfigError(
            f"Discord voice config is not valid JSON: {error}"
        ) from error

    if not isinstance(raw_config, dict):
        raise DiscordVoiceConfigError(
            "Discord voice config must be a JSON object."
        )

    return raw_config


def _read_required_string(
    target_config: object,
    *,
    field_name: str,
    alias: str,
) -> str:
    """Read one required string field from one target."""
    if not isinstance(target_config, dict):
        raise DiscordVoiceConfigError(
            f"Discord voice target '{alias}' must be a JSON object."
        )

    value = target_config.get(field_name)

    if not isinstance(value, str) or not value.strip():
        raise DiscordVoiceConfigError(
            f"Discord voice target '{alias}' must define "
            f"a non-empty '{field_name}'."
        )

    return value.strip()

def _read_optional_string(
    target_config: object,
    *,
    field_name: str,
    alias: str,
) -> str | None:
    """Read one optional non-empty string field from one target."""
    if not isinstance(target_config, dict):
        raise DiscordVoiceConfigError(
            f"Discord voice target '{alias}' must be a JSON object."
        )

    if field_name not in target_config:
        return None

    value = target_config.get(field_name)

    if not isinstance(value, str) or not value.strip():
        raise DiscordVoiceConfigError(
            f"Discord voice target '{alias}' must define "
            f"a non-empty '{field_name}' when provided."
        )

    return value.strip()


def load_discord_voice_targets(
    *,
    path: Path = DEFAULT_DISCORD_VOICE_CONFIG_PATH,
) -> tuple[DiscordVoiceTarget, ...]:
    """Load approved Discord voice targets from private local config."""
    raw_config = _read_config_object(path)
    raw_targets = raw_config.get("targets", {})

    if not isinstance(raw_targets, dict):
        raise DiscordVoiceConfigError(
            "Discord voice config field 'targets' must be an object."
        )

    targets: list[DiscordVoiceTarget] = []
    seen_aliases: set[str] = set()

    for raw_alias, target_config in raw_targets.items():
        alias = str(raw_alias).strip()
        normalised_alias = _normalise_alias(alias)

        if not normalised_alias:
            raise DiscordVoiceConfigError(
                "Discord voice target aliases cannot be empty."
            )

        if normalised_alias in seen_aliases:
            raise DiscordVoiceConfigError(
                f"Duplicate Discord voice target alias: {alias}"
            )

        seen_aliases.add(normalised_alias)

        server_name = _read_required_string(
            target_config,
            field_name="server_name",
            alias=alias,
        )
        channel_name = _read_required_string(
            target_config,
            field_name="channel_name",
            alias=alias,
        )
        quick_switcher_query = _read_optional_string(
            target_config,
            field_name="quick_switcher_query",
            alias=alias,
        )

        targets.append(
            DiscordVoiceTarget(
                alias=alias,
                server_name=server_name,
                channel_name=channel_name,
                quick_switcher_query=quick_switcher_query,
            )
        )

    return tuple(targets)


def get_discord_voice_target(
    requested_alias: str,
    *,
    path: Path = DEFAULT_DISCORD_VOICE_CONFIG_PATH,
) -> DiscordVoiceTarget:
    """Resolve one approved Discord voice target by exact alias."""
    normalised_requested_alias = _normalise_alias(requested_alias)

    if not normalised_requested_alias:
        raise DiscordVoiceConfigError(
            "Discord voice target alias cannot be empty."
        )

    for target in load_discord_voice_targets(path=path):
        if _normalise_alias(target.alias) == normalised_requested_alias:
            return target

    raise DiscordVoiceConfigError(
        f"No Discord voice target configured for "
        f"'{requested_alias.strip()}'."
    )