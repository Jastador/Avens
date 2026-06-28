# Avens

Avens is a local-first Windows desktop voice assistant with wake-word activation, offline speech recognition, local text-to-speech, Ollama-based responses, desktop controls, memory, and a PyQt orb interface.

It is an early-stage personal project built for local use and experimentation. Most normal interaction runs locally; optional research or online-AI features may use the internet when explicitly enabled.

## Features

* Wake phrase detection with Vosk: **“Hey Avens”**
* Offline speech-to-text with Faster-Whisper
* Local text-to-speech with Kokoro
* Local Ollama-powered assistant responses
* Streaming responses with interruption support
* Desktop app launching
* Volume and brightness controls
* Timers and reminders
* Local vector memory with ChromaDB
* Optional local knowledge-base ingestion
* Screen analysis with Ollama's `moondream` model
* Camera and hand-gesture controls through MediaPipe
* Animated PyQt orb interface
* Private local profile, memory, and knowledge storage outside the repository

## Requirements

* Windows 10 or Windows 11
* Python 3.12
* A working microphone
* Ollama installed locally
* Internet access for first-time model downloads, unless assets are already cached
* Optional: a webcam for vision and gesture controls

## Quick Start

Clone the repository:

```powershell
git clone <repository-url>
cd Avens
```

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install Python dependencies:

```powershell
pip install -r requirements.txt
```

Create your local configuration file:

```powershell
Copy-Item .env.example .env
```

Download the required Vosk wake model and Kokoro voice asset:

```powershell
python setup_assets.py
```

Install the default local Ollama model:

```powershell
ollama pull phi3:instruct
```

Optional: install the local vision model for screen analysis:

```powershell
ollama pull moondream
```

Start Avens:

```powershell
python app.py
```

## First-Run Downloads

`setup_assets.py` installs:

* Vosk wake-word speech model
* Kokoro `am_adam` voice file

On a normal first run with offline mode disabled, Faster-Whisper and Kokoro may download their required model data into the local Hugging Face cache.

After all required assets are downloaded, set this in `.env` to prefer offline operation:

```text
AVENS_OFFLINE_MODE=true
```

## Configuration

Copy `.env.example` to `.env` and edit it for local preferences.

Example:

```text
AVENS_OLLAMA_MODEL=phi3:instruct
AVENS_OFFLINE_MODE=false
AVENS_USE_ONLINE_AI=false
```

Useful overrides:

```text
# Use a custom local Ollama model.
AVENS_OLLAMA_MODEL=my-local-model

# Choose where profile, memory, and knowledge files are stored.
AVENS_DATA_DIR=C:\Users\YourName\AppData\Local\Avens

# Use an existing Hugging Face cache.
AVENS_HF_HOME=C:\Path\To\HuggingFaceCache

# Use a custom profile file.
AVENS_PROFILE_PATH=C:\Path\To\profile.txt
```

## Private Local Data

Avens keeps personal data outside the repository by default:

```text
%LOCALAPPDATA%\Avens\
├── profile.txt
├── knowledge_base\
└── vector_db\
```

`profile.txt` is optional. It lets Avens use local preferences without storing them in Git.

Example:

```text
Name: Alex
Preferred response style: concise
Interests: gaming, fitness, programming
```

## Knowledge Base

Add `.md` or `.txt` files to:

```text
%LOCALAPPDATA%\Avens\knowledge_base
```

Then ingest them into local vector memory:

```powershell
python ingest_knowledge.py
```

The current ingestion tool appends memory chunks. Do not rerun it repeatedly on unchanged documents unless duplicate memories are intended.

## Project Structure

```text
Avens/
├── app.py                 # Main application loop and UI orchestration
├── config.py              # Public defaults and local configuration loading
├── setup_assets.py        # Downloads required Vosk and Kokoro assets
├── ingest_knowledge.py    # Imports local notes into vector memory
├── automation/
│   ├── commands.py        # Desktop controls and automation
│   └── scanner.py         # Installed-app discovery
├── core/
│   ├── brain.py           # Ollama and optional online-AI response logic
│   ├── memory.py          # Local ChromaDB memory
│   ├── profile.py         # Private local profile loading
│   ├── researcher.py      # Optional web research
│   ├── stt.py             # Faster-Whisper speech recognition
│   ├── tts.py             # Kokoro text-to-speech
│   ├── vision.py          # MediaPipe hand tracking
│   └── wake_word.py       # Vosk wake phrase detection
├── ui/
│   └── orb.py             # PyQt interface
└── utils/
    ├── internet_check.py
    └── mic_check.py
```

## Notes and Limitations

* Avens is currently Windows-focused. Several controls rely on Windows-specific APIs.
* The default configuration uses CPU inference for stability.
* Screen analysis requires the separate `moondream` Ollama model.
* Web research and optional online AI features require internet access.
* This is not a production security boundary. Review commands and local automation behavior before using it on a shared machine.

## Privacy

Do not commit or publish:

* `.env`
* Local profile files
* Local vector-memory databases
* Personal knowledge documents
* Fine-tuning datasets
* Downloaded model caches or large model files

These paths are excluded through `.gitignore`.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
