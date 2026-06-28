from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

from huggingface_hub import hf_hub_download


PROJECT_ROOT = Path(__file__).resolve().parent
MODELS_DIR = PROJECT_ROOT / "models"
VOSK_MODEL_NAME = "vosk-model-small-en-us-0.15"
VOSK_MODEL_DIR = MODELS_DIR / VOSK_MODEL_NAME
VOSK_URL = (
    "https://alphacephei.com/vosk/models/"
    f"{VOSK_MODEL_NAME}.zip"
)

VOICE_PATH = PROJECT_ROOT / "voices" / "am_adam.pt"


def ensure_vosk_model() -> None:
    if VOSK_MODEL_DIR.exists():
        print(f"Vosk model already exists: {VOSK_MODEL_DIR}")
        return

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=MODELS_DIR) as temp_dir:
        temp_dir_path = Path(temp_dir)
        archive_path = temp_dir_path / f"{VOSK_MODEL_NAME}.zip"
        extract_dir = temp_dir_path / "extracted"

        print("Downloading Vosk wake-word model...")
        urlretrieve(VOSK_URL, archive_path)

        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(extract_dir)

        extracted_model = extract_dir / VOSK_MODEL_NAME

        if not extracted_model.exists():
            raise RuntimeError(
                "The downloaded Vosk archive did not contain the expected model folder."
            )

        shutil.move(str(extracted_model), str(VOSK_MODEL_DIR))

    print(f"Installed Vosk model: {VOSK_MODEL_DIR}")


def ensure_kokoro_voice() -> None:
    if VOICE_PATH.exists():
        print(f"Kokoro voice already exists: {VOICE_PATH}")
        return

    print("Downloading Kokoro am_adam voice...")
    downloaded_path = Path(
        hf_hub_download(
            repo_id="hexgrad/Kokoro-82M",
            filename="voices/am_adam.pt",
            local_dir=str(PROJECT_ROOT),
        )
    )

    VOICE_PATH.parent.mkdir(parents=True, exist_ok=True)

    if downloaded_path.resolve() != VOICE_PATH.resolve():
        shutil.copy2(downloaded_path, VOICE_PATH)

    print(f"Installed Kokoro voice: {VOICE_PATH}")


def main() -> None:
    ensure_vosk_model()
    ensure_kokoro_voice()

    print("\nAsset setup complete.")
    print("On first non-offline startup, Faster-Whisper and Kokoro may download model data.")


if __name__ == "__main__":
    main()
