from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from skills.discord_voice_config import (
    DEFAULT_DISCORD_VOICE_CONFIG_PATH,
    DiscordVoiceConfigError,
    DiscordVoiceTarget,
    get_discord_voice_target,
)


DISCORD_VOICE_TARGET_COMMAND_PATTERN: Final = re.compile(
    r"^\s*"
    r"(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?"
    r"(?:join|open|connect(?:\s+to)?)\s+"
    r"(?P<alias>[a-z0-9][a-z0-9\s_-]*?)\s+"
    r"(?:discord\s+)?voice(?:\s+channel)?"
    r"(?:\s+please)?"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DiscordVoiceTargetResolution:
    """Result of resolving one Discord voice target command."""

    success: bool
    alias: str
    target: DiscordVoiceTarget | None
    message: str


def parse_discord_voice_target_alias(
    user_input: str,
) -> str | None:
    """Parse a Discord voice target alias from one strict command."""
    match = DISCORD_VOICE_TARGET_COMMAND_PATTERN.match(user_input)

    if match is None:
        return None

    alias = match.group("alias").strip()

    if not alias:
        return None

    return alias


def resolve_discord_voice_target_command(
    user_input: str,
    *,
    path: Path = DEFAULT_DISCORD_VOICE_CONFIG_PATH,
) -> DiscordVoiceTargetResolution | None:
    """Resolve one read-only Discord voice target command."""
    alias = parse_discord_voice_target_alias(user_input)

    if alias is None:
        return None

    try:
        target = get_discord_voice_target(
            alias,
            path=path,
        )
    except DiscordVoiceConfigError as error:
        return DiscordVoiceTargetResolution(
            success=False,
            alias=alias,
            target=None,
            message=str(error),
        )

    return DiscordVoiceTargetResolution(
        success=True,
        alias=alias,
        target=target,
        message=(
            "Discord voice target resolved: "
            f"server '{target.server_name}', "
            f"channel '{target.channel_name}'. "
            "UI joining is not implemented yet, sir."
        ),
    )