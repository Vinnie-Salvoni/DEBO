# DEBO — expressive desktop robot companion

DEBO is a software-first desk robot project. The current prototype runs on a desktop computer and combines an original, animated Cozmo/Vector-inspired face, deterministic personality, local wake-word speech recognition, speech synthesis, electronic sound effects, and live weather/news tools.

The long-term plan is to build the brain first, then a reliable stationary physical companion, and add movement only much later. The current code is a desktop prototype; it does not control physical robot hardware.

## Current architecture

```text
src/desk_robot/
├── __main__.py              # Application entry point
├── config.py                # Validated brain settings
├── core/                    # Capability state and semantic events
├── interfaces/              # Input and output contracts
├── robot.py                 # Deterministic interaction and intent handling
├── personality.py           # Character voice and reactions
├── context.py               # Bounded session-only conversation context
├── information.py           # Weather/news models and provider adapters
├── face.py                  # Tkinter desktop UI and animation loop
├── face_geometry.py         # Pure eye shapes and semantic expressions
├── face_settings.py         # Validated persistent face preferences
├── voice.py                 # Local microphone and wake-word recognition
├── speech.py                # Operating-system speech output
└── sound.py                 # Original electronic sound effects

tests/unit/                  # Hardware-independent automated tests
```

This is an incremental separation, not a claim that every interface is already wired into every subsystem. The face remains the current desktop renderer; new brain primitives are intended to let future changes separate behaviour from rendering without breaking the working prototype.

## Requirements and setup

- Python 3.14 or newer; `uv` manages dependencies and the environment.
- A microphone for wake-word interaction; local recognition loads the `base.en` model on first run.
- Internet access for live weather, headlines, and article reading.
- Windows is the primary audio target. Speech uses an installed system voice; no cloud TTS account is required.

From the repository directory in PowerShell:

```powershell
uv sync --all-groups
uv run python -m desk_robot.face
```

The first run may take longer while faster-whisper downloads its model. DEBO can launch without microphone access; wake-word input will report an unavailable state, and the visual interface remains usable.

## Voice commands

Say **“Hey DEBO”**, then give a command. You can combine the wake phrase and command in one utterance.

- “Weather in London” — current conditions and today's high/low when available.
- “Show me the news”, “Next story”, or “Read the full story”.
- “Change my eye colour to blue”; other supported colours are available through the settings dialog.
- “Eye glow high”, “eye glow low”, or “eye glow 65”.
- “Animation speed fast”, “normal”, or “slow”.
- “Turn sound off/on”, “turn speech off/on”, or “Settings”.
- “What did I just say?” or “Help”.

Speech pauses microphone capture during playback to avoid DEBO hearing its own voice. Speech can be disabled while keeping the visual interface.

## Brain configuration

Environment variables configure hardware-independent defaults; they contain no secrets.

| Variable | Default | Allowed values |
|---|---:|---|
| `DEBO_NAME` | `Debo` | 1–40 characters |
| `DEBO_CONTEXT_TURNS` | `5` | Integer, 1–50 |
| `DEBO_INFORMATION_TIMEOUT_SECONDS` | `8.0` | Number, 0.5–60 |
| `DEBO_NEWS_RESULT_LIMIT` | `5` | Integer, 1–20 |
| `DEBO_LAPTOP_BRIDGE_ENABLED` | `false` | true/false, 1/0, yes/no |

Invalid values raise a clear configuration error. Existing face preferences remain in the separate local settings file until that subsystem is migrated. Provider credentials must never be committed or logged.

## Information independence

The current desktop prototype uses Open-Meteo for weather and RSS for news. Weather/news requests are handled by provider adapters, not invented by an AI model. Provider outages should be reported honestly.

**Unfinished release requirement:** genuine weather and news must be retrieved over DEBO's own network connection while the development laptop is powered off and Ollama is unavailable. This has not yet been proven on target hardware. No final robot computer or laptop/Ollama bridge has been selected or implemented.

## Development checks

```powershell
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

The normal test suite should not require live provider endpoints, a microphone, or a physical robot.

## Roadmap

1. **Brain foundation:** configuration, capability state, semantic events, interfaces, tests, reliable startup.
2. **Personality and interaction:** modular behaviour, bounded context, graceful fallbacks.
3. **Information tools:** provider contracts, freshness, error handling, independent-internet acceptance tests.
4. **Stationary prototype:** expressive face and selected input/output, still without movement.
5. **Physical integration:** choose hardware from measured requirements; use Onshape for editable CAD.
6. **Movement:** research and implement only after the stationary device is reliable.

Consult the project roadmap, technology decisions, and brain specification for the full requirements. Hardware, providers, network transport, display, and enclosure choices remain open until researched and tested.
