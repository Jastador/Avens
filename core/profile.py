from __future__ import annotations

import os
from pathlib import Path

from config import LOCAL_DATA_DIR


PROFILE_PATH = Path(
    os.getenv("AVENS_PROFILE_PATH", str(LOCAL_DATA_DIR / "profile.txt"))
).expanduser()


def load_user_profile() -> str:
    """Load private user context stored outside the Git repository."""
    if not PROFILE_PATH.exists():
        return "- No local user profile is configured."

    profile = PROFILE_PATH.read_text(encoding="utf-8").strip()
    return profile or "- No local user profile is configured."
