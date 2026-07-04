# Avens

Avens is a **local-first Windows desktop voice assistant** built in Python. It listens for **“Hey Avens”**, runs its normal voice and reasoning workflow locally, and provides optional online AI and visual-search modes only after an explicit spoken mode change.

It is a personal portfolio project for experimenting with local AI, desktop automation, voice interaction, and privacy-aware multimodal features. It is not presented as a production security boundary, an always-correct assistant, or a magic computer genie. Those remain regrettably fictional.

## Highlights

* **Wake word:** Vosk recognition for “Hey Avens”
* **Speech-to-text:** Faster-Whisper `distil-small.en` on CPU with `int8` inference
* **Text-to-speech:** Kokoro using the local `am_adam` voice
* **Local brain:** Ollama, selected through `AVENS_OLLAMA_MODEL`
* **Offline by default:** the brain and camera start in local mode
* **Explicit online switching:** GPT, Gemini, and online camera search require a spoken mode change
* **Desktop automation:** launch applications, control volume and brightness, manage timers and reminders, and interact with Windows
* **Local memory:** profile, memory, and knowledge-base storage remain local
* **Screen and camera features:** on-demand screen analysis, live camera dashboard, local object identification, description, and text reading
* **Optional Lens Scan:** SerpApi Google Lens with a temporary Cloudinary upload that is deleted after use
* **Local observability:** optional JSONL performance traces under `logs/performance`, with no external telemetry

## Architecture

```text
Microphone
   │
   ├── Vosk wake-word listener: “Hey Avens”
   │
   └── Faster-Whisper STT: distil-small.en, CPU int8
            │
            ▼
      Runtime mode controller
            │
            ├── Offline brain
            │     └── Local Ollama model via AVENS_OLLAMA_MODEL
            │
            ├── Online brain, only after spoken mode change
            │     ├── OpenAI GPT
            │     └── Google Gemini
            │
            ├── Offline camera
            │     ├── Identify: MiniCPM v4.6 1B
            │     └── Describe/read: Qwen2.5-VL 3B
            │
            └── Online camera, only after spoken mode change
                  └── SerpApi Google Lens via temporary Cloudinary upload
            │
            ▼
      Memory, automation, UI, and voice response
            │
            └── Kokoro TTS with local am_adam voice
```

## Local-First Privacy Design

Avens begins with both its **brain** and **camera** in offline mode.

* Offline brain requests go to local Ollama.
* Offline camera identification uses local vision models through Ollama.
* Local camera processing receives an in-memory frame, prepares it for the selected local model, and discards temporary references after the request.
* Profile data, local memory, knowledge-base files, downloaded assets, model caches, performance logs, and `.env` configuration are intended to stay outside Git.
* Performance tracing writes local JSONL files only. Avens does not send telemetry to an external analytics service.

Online features are deliberately separated from ordinary local use. They are not selected merely because credentials exist in `.env`.

### Online context sharing

When an online brain is selected, Avens does **not** share local profile data, memory, or prior conversation history by default.

Set this only if you deliberately want local context included in requests to an online brain provider:

```env
AVENS_SHARE_LOCAL_CONTEXT_ONLINE=true
```

Treat that setting seriously. A checkbox disguised as an environment variable is still a checkbox.

## Runtime Modes

Avens uses an explicit runtime mode controller rather than silently changing providers.

| Area          | Offline mode                       | Online mode                        |
| ------------- | ---------------------------------- | ---------------------------------- |
| Brain         | Local Ollama model                 | OpenAI GPT or Google Gemini        |
| Camera        | Local vision models through Ollama | SerpApi Google Lens                |
| Default state | Enabled at startup                 | Disabled until explicitly selected |

A spoken request to go online or offline asks whether the change applies to the **brain**, **camera**, or **both**.

### Offline brain

The offline brain uses Ollama and reads the model name from:

```env
AVENS_OLLAMA_MODEL=custom_avens
```

The maintainer normally uses a local Ollama model named `custom_avens`. That model is a machine-local custom model or alias and is not included in this repository.

For a clean public setup, configure `AVENS_OLLAMA_MODEL` to any compatible local Ollama chat model you have installed. The current public fallback in code is `phi3:instruct`.

### Online brain

Online brain modes are available only after explicit selection:

* **GPT mode:** requires `OPENAI_API_KEY`
* **Gemini mode:** requires `GEMINI_API_KEY`

If a selected online provider is unavailable or its credentials are missing, Avens falls back to local Ollama.

### Offline camera

The local camera pipeline uses separate models based on the request:

| Request  | Local model       | Purpose                                                                           |
| -------- | ----------------- | --------------------------------------------------------------------------------- |
| Identify | `minicpm-v4.6:1b` | Fast broad-category identification of an object held near the centre of the frame |
| Describe | `qwen2.5vl:3b`    | Concise scene and object description                                              |
| Read     | `qwen2.5vl:3b`    | Reading clearly legible text near the centre of the frame                         |

Camera processing is intentionally conservative:

* It works from an on-demand in-memory frame.
* It avoids identifying people or inferring sensitive personal traits.
* It asks the model to state uncertainty rather than guess.
* Object identification is designed to return a broad category, not a claimed brand or exact model.

### Online camera: Lens Scan

Online camera identification uses **SerpApi Google Lens** only after the camera is explicitly switched online.

The flow is:

1. Avens prepares one camera crop in memory.
2. It uploads the crop temporarily to Cloudinary.
3. SerpApi performs a Google Lens lookup using that temporary URL.
4. Avens removes the Cloudinary asset in a cleanup step.
5. The spoken result is framed as a visual match, not proof of an exact product model.

This mode requires SerpApi and Cloudinary credentials. It is optional and not needed for local camera features.

## Features

### Voice interaction

* Vosk wake-word detection for **“Hey Avens”**
* Faster-Whisper speech recognition using `distil-small.en` on CPU `int8`
* Kokoro speech synthesis with the local `am_adam` voice
* Streaming assistant responses
* Wake-word interruption while Avens is speaking

### Local reasoning and memory

* Ollama-backed local assistant responses
* Private local profile support
* Local ChromaDB memory
* Optional local knowledge-base ingestion from `.txt` and `.md` files
* Memory retrieval for relevant local context during offline conversations

### Windows automation

Avens includes Windows-focused automation for tasks such as:

* Launching installed applications
* Window interaction
* Volume control
* Brightness control
* Timers and reminders
* Browser and desktop actions

Review automation behaviour before using Avens on a shared machine. A voice assistant with desktop control is useful; an unattended voice assistant with desktop control is how humans accidentally invent new problems.

### Screen and vision features

* Animated PyQt orb interface
* Expandable vision dashboard
* Live webcam and hand-gesture support
* On-demand screen analysis
* Local camera identification, scene description, and text reading
* Optional online Lens Scan for visual search

## Requirements

* Windows 10 or Windows 11
* Python 3.12
* Ollama installed and running locally
* A working microphone
* Internet access for first-time Python or model downloads, unless all required assets are already cached
* Optional: webcam for camera, gesture, and visual-search features

## Setup

### 1. Clone the repository

```powershell
git clone https://github.com/Jastador/Avens.git
cd Avens
```

### 2. Create a Python 3.12 virtual environment

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks activation for the current terminal session:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 3. Create private local configuration

```powershell
Copy-Item .env.example .env
```

Open `.env` and configure the local Ollama brain model you intend to use:

```env
AVENS_OLLAMA_MODEL=custom_avens
```

`custom_avens` is the maintainer’s local model name. Replace it with your own installed Ollama model when necessary.

### 4. Download local Avens assets

```powershell
python setup_assets.py
```

This installs the project assets used by the local wake-word and voice setup, including the Vosk wake model and Kokoro `am_adam` voice asset.

### 5. Install required Ollama models

Start Ollama, then install the models selected in your configuration.

```powershell
# Local brain: choose the model configured in AVENS_OLLAMA_MODEL.
# Example public fallback:
ollama pull phi3:instruct

# Local camera models:
ollama pull minicpm-v4.6:1b
ollama pull qwen2.5vl:3b
```

If you use a custom local brain model:

```powershell
ollama list
```

Confirm that the model name in `.env` matches the name shown by Ollama.

### 6. Run Avens

```powershell
python app.py
```

## Configuration

Copy `.env.example` to `.env`. The example file contains commented, secret-free settings for local models, performance tracing, and optional online services.

### Core local configuration

```env
# Your local Ollama chat model.
AVENS_OLLAMA_MODEL=custom_avens

# Local camera models.
AVENS_FAST_VISION_MODEL=minicpm-v4.6:1b
AVENS_DEEP_VISION_MODEL=qwen2.5vl:3b

# Keep-alive values for local Ollama models.
AVENS_LOCAL_BRAIN_KEEP_ALIVE=5m
AVENS_FAST_VISION_KEEP_ALIVE=2m
AVENS_DEEP_VISION_KEEP_ALIVE=0

# Kokoro CPU thread count.
AVENS_TTS_CPU_THREADS=4
```

### Offline asset behaviour

After the necessary assets have been downloaded and cached, this setting makes Hugging Face-dependent components prefer offline use:

```env
AVENS_OFFLINE_MODE=true
```

Useful optional local paths:

```env
# AVENS_DATA_DIR=C:\Users\YourName\AppData\Local\Avens
# AVENS_HF_HOME=C:\Path\To\HuggingFaceCache
# AVENS_PROFILE_PATH=C:\Path\To\profile.txt
```

## Local Data and Knowledge Base

Avens is designed to keep personal state outside the repository by default.

Typical local data lives under:

```text
%LOCALAPPDATA%\Avens\
├── profile.txt
├── knowledge_base\
└── vector_db\
```

### Local profile

A profile file is optional. It can contain preferences that should remain on your own machine.

```text
Name: Alex
Preferred response style: concise
Interests: gaming, fitness, programming
```

### Local knowledge base

Add `.txt` or `.md` files to:

```text
%LOCALAPPDATA%\Avens\knowledge_base\
```

Then ingest them into local vector memory:

```powershell
python ingest_knowledge.py
```

The current ingestion flow appends memory chunks. Avoid repeatedly ingesting unchanged documents unless duplicate entries are intended.

## Optional Online Services

Offline operation does not require any cloud credentials.

| Service       | Used for                                    | Required variables                                                     |
| ------------- | ------------------------------------------- | ---------------------------------------------------------------------- |
| OpenAI        | Explicitly selected GPT brain mode          | `OPENAI_API_KEY`, optional `AVENS_OPENAI_MODEL`                        |
| Google Gemini | Explicitly selected Gemini brain mode       | `GEMINI_API_KEY`, optional `AVENS_GEMINI_MODEL`                        |
| SerpApi       | Explicitly selected online camera Lens Scan | `SERPAPI_API_KEY`                                                      |
| Cloudinary    | Temporary image hosting for Lens Scan       | `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` |

Online modes stay disabled unless you explicitly switch the relevant runtime area online.

Never commit a real `.env` file. It may contain personal paths, local model names, API keys, or other information that has no business being in public Git history.

## Performance Observability

Avens includes optional local performance tracing for understanding real behaviour on your own hardware.

When enabled, it writes compact JSONL traces under:

```text
logs/performance\
```

Tracing can record timings across stages such as:

* Startup and asset loading
* Wake-word waiting and detection
* Speech recognition
* Local memory lookup
* Ollama response generation
* Camera preparation and local vision inference
* Text-to-speech generation and playback

Enable it in `.env`:

```env
AVENS_PERF_ENABLED=true
AVENS_PERF_LOG_DIR=logs/performance
AVENS_PERF_LOG_PROMPTS=false
```

`AVENS_PERF_LOG_PROMPTS` should remain `false` unless you intentionally want prompts written into local performance traces.

These traces are meant for diagnosing bottlenecks and comparing changes on the same machine. They are not a benchmark suite, do not guarantee latency, and will vary with hardware, model size, cache state, microphone conditions, and whatever other chaos Windows has chosen for the day.

## Project Structure

```text
Avens/
├── app.py                     # Main application loop and orchestration
├── config.py                  # Environment loading and local defaults
├── setup_assets.py            # Local Vosk and Kokoro asset setup
├── ingest_knowledge.py        # Local knowledge-base ingestion
├── automation/
│   ├── commands.py            # Windows automation and desktop controls
│   └── scanner.py             # Installed application discovery
├── core/
│   ├── brain.py               # Local Ollama and optional online-brain routing
│   ├── mode_controller.py     # Explicit offline/online runtime state
│   ├── memory.py              # Local ChromaDB memory
│   ├── profile.py             # Private local profile loading
│   ├── stt.py                 # Faster-Whisper speech recognition
│   ├── tts.py                 # Kokoro text-to-speech
│   ├── wake_word.py           # Vosk “Hey Avens” detection
│   ├── camera_intelligence.py # Local camera identify, describe, and read flow
│   ├── lens_scan.py           # Optional SerpApi Google Lens workflow
│   ├── performance.py         # Local JSONL performance traces
│   └── vision.py              # Camera and gesture coordination
├── ui/                        # PyQt orb, visualizer, and vision dashboard
└── utils/                     # Microphone, internet, and shared helpers
```

## Limitations

* Avens is currently Windows-focused. Several automation features rely on Windows APIs.
* CPU inference is prioritised for local reliability, not maximum speed.
* Local model quality depends on your selected Ollama models and available hardware.
* Camera identification, OCR, and gesture recognition depend heavily on lighting, framing, focus, and webcam quality.
* Online features require an internet connection and valid third-party credentials.
* Cloud visual search introduces an intentional external request path and should be used only when appropriate.
* The maintainer’s local `custom_avens` model is not packaged with this repository.
* This project is under active personal development and may change without stable API guarantees.

## Roadmap

Potential future work includes:

* A smoother first-run setup and dependency validation flow
* More configuration controls in the UI
* Improved test coverage around mode switching and provider fallbacks
* Better local model diagnostics and setup guidance
* Additional accessibility and voice-control improvements
* More polished packaging for Windows distribution

## Privacy and Repository Hygiene

Do not commit or publish:

* `.env` files or API keys
* Local profiles and personal knowledge documents
* ChromaDB vector-memory files
* Performance traces
* Downloaded model assets, caches, or custom model files
* Temporary camera outputs or personal screenshots
* Fine-tuning data or personal datasets

These files should remain private and excluded from Git.

## License

This project is licensed under the [MIT License](LICENSE).
