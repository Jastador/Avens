from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent
BASE_PATH = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT))

# Local overrides stay private in .env and are never committed.
load_dotenv(PROJECT_ROOT / ".env", override=False)

# Make direct module imports use the same private local Hugging Face cache
# and offline behaviour as the main Avens launcher.
os.environ["HF_HOME"] = os.getenv(
    "AVENS_HF_HOME",
    str(PROJECT_ROOT / "models" / "huggingface"),
)

offline_mode = os.getenv(
    "AVENS_OFFLINE_MODE",
    "false",
).strip().casefold() in {
    "1",
    "true",
    "yes",
    "on",
}

for variable in (
    "HF_HUB_OFFLINE",
    "HF_DATASETS_OFFLINE",
    "TRANSFORMERS_OFFLINE",
):
    os.environ[variable] = "1" if offline_mode else "0"

_default_data_root = Path(
    os.getenv("LOCALAPPDATA", str(Path.home() / ".local" / "share"))
) / "Avens"

LOCAL_DATA_DIR = Path(
    os.getenv("AVENS_DATA_DIR", str(_default_data_root))
).expanduser()

# Public default. Personal fine-tuned models can override this in .env.
OLLAMA_MODEL = os.getenv("AVENS_OLLAMA_MODEL", "phi3:instruct")

USE_ONLINE_AI = os.getenv(
    "AVENS_USE_ONLINE_AI",
    "false"
).strip().lower() in {"1", "true", "yes", "on"}
