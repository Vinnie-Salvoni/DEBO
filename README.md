# DEBO — expressive desktop robot companion

DEBO is a software-first desk robot project. The current prototype runs on a desktop computer and combines an animated face, deterministic personality, local wake-word speech recognition, speech synthesis, electronic sound effects, and live weather/news tools.

The long-term plan is to build the brain first, then a reliable stationary physical companion, and add movement only much later. The current code is a desktop prototype; it does **not** control physical robot hardware.

## Quick start (Windows / PowerShell)

You need Git, Python **3.14 or newer**, and [uv](https://docs.astral.sh/uv/). From PowerShell:

```powershell
git clone https://github.com/Vinnie-Salvoni/DEBO.git
cd DEBO
uv sync --all-groups
uv run python -m desk_robot.face
```

If you already cloned DEBO, do not clone it again. Use the existing folder and follow **Update DEBO** below.

The first launch can take longer while the local `base.en` speech-recognition model is downloaded/cached. Allow microphone access in Windows privacy settings. Speech output uses an installed system voice. Internet access is needed for live weather, RSS headlines, and article reading. The app can still open if voice input is unavailable.

## Run DEBO

From the repository root:

```powershell
uv run python -m desk_robot.face
```

Say **“Hey DEBO”**, then give a command. You can also say the wake phrase and command in one utterance.

- “Weather in London” or “Do I need an umbrella in Manchester?”
- “Give me the weather” — DEBO asks for a city/town, then listens for the answer without requiring another wake phrase.
- “Show me the news”, “Next story”, “Read the full story”.
- “Change my eye colour to blue”; “Eye glow 65”; “Animation speed slow”.
- “Turn sound off/on”; “Turn speech off/on”; “Speech volume 70”; “Settings” for spoken help.
- “What did I just say?” and “Help”.
- Say “Never mind” or “Cancel” to abandon a weather-location question.

The clarification answer window is short and one-shot. If you do not answer in time, DEBO cancels the unfinished request and returns to wake-word standby. Speech playback pauses microphone capture to reduce DEBO hearing its own voice. The animated face is the display; normal in-app interaction is voice-only. The operating-system window close button remains available.

## Update DEBO after changes have been pushed to GitHub

This is the normal routine whenever changes have been pushed to `master`.

1. Close DEBO if it is running.
2. Open PowerShell in your existing local `DEBO` folder.
3. Run:

```powershell
git status
git pull --ff-only origin master
uv sync --all-groups
uv run python -m desk_robot.face
```

`git pull --ff-only` updates your local branch without creating an accidental merge commit. If Git says you have local changes or cannot fast-forward, stop and inspect `git status`; do not use `reset --hard` as a shortcut.

## Git commands you'll use

### Check your current state

```powershell
git status
git branch --show-current
git log -5 --oneline --decorate
git remote -v
```

- `git status` tells you whether local files differ from the last commit.
- `git branch --show-current` prints your current branch (normally `master`).
- `git log -5 --oneline` shows the latest five commits.
- `git remote -v` should show this repository as `origin`.

### Get the latest version

```powershell
git pull --ff-only origin master
uv sync --all-groups
```

Do this before making your own edits, especially if edits were made directly on GitHub.

### Save and push your own edits

Only do this when you deliberately made changes you want to keep:

```powershell
git status
git add README.md
# Replace README.md with the file(s) you actually changed.
git diff --cached
git commit -m "Describe your change"
git push origin master
```

To stage all changed files, use `git add .` only after checking `git status` and confirming generated files, recordings, local settings, and secrets will not be included. Never commit API keys, passwords, private recordings, local model files, or machine-specific settings.

If Git rejects your push because GitHub has newer commits, do not force-push. Run:

```powershell
git pull --rebase origin master
git push origin master
```

If Git reports conflicts, stop and share the exact output if you are unsure how to resolve them.

### Inspect changes

```powershell
git diff
git diff --cached
git log -5 --oneline
```

### Discard an uncommitted change to one file (careful)

This permanently discards your uncommitted edits to the named file and restores the last committed version:

```powershell
git diff
git restore path/to/file.py
```

Replace the example path with the actual file. Inspect `git diff` first.

### Undo a committed change safely

Prefer a new reversing commit, particularly if the commit was already pushed:

```powershell
git log -5 --oneline
git revert COMMIT_SHA
git push origin master
```

Replace `COMMIT_SHA` with the actual commit ID. Do not run `git reset --hard` or force-push unless we have specifically planned a recovery and confirmed what must be preserved.

### If something goes wrong

```powershell
git status
git log -5 --oneline --decorate
git remote -v
```

Copy the full output and error message into the chat. Do not delete or reclone the repository before checking whether you have local changes.

## Automated checks

Run from the repository root:

```powershell
uv sync --all-groups
uv run pytest
uv run ruff check .
```

The normal test suite should not require live provider endpoints, a microphone, or physical robot hardware. GitHub Actions runs the project's checks after pushes. A green workflow proves those automated checks passed; it does not prove microphone behaviour or physical hardware integration on every computer.

## Current architecture

```text
src/desk_robot/
├── __main__.py              # Application entry point
├── config.py                # Validated brain settings
├── core/                    # Capability state and semantic events
├── interfaces/              # Input and output contracts
├── robot.py                 # Intent handling and responses
├── personality.py           # Character voice and reactions
├── context.py               # Bounded session-only conversation context
├── information.py           # Weather/news provider adapters
├── face.py                  # Tkinter desktop UI and animation loop
├── face_geometry.py         # Eye shapes and semantic expressions
├── face_settings.py         # Persistent face preferences
├── voice.py                 # Local microphone and wake-word recognition
├── speech.py                # Operating-system speech output
└── sound.py                 # Electronic sound effects

tests/unit/                  # Hardware-independent automated tests
```

This is an incremental separation, not a claim that every interface is already wired into every subsystem. The face is the current renderer. New brain primitives should let future changes separate behaviour from rendering without breaking the working prototype.

## Brain configuration

Environment variables configure hardware-independent defaults:

| Variable | Default | Allowed values |
|---|---:|---|
| `DEBO_NAME` | `Debo` | 1–40 characters |
| `DEBO_CONTEXT_TURNS` | `5` | Integer, 1–50 |
| `DEBO_INFORMATION_TIMEOUT_SECONDS` | `8.0` | Number, 0.5–60 |
| `DEBO_NEWS_RESULT_LIMIT` | `5` | Integer, 1–20 |
| `DEBO_LAPTOP_BRIDGE_ENABLED` | `false` | true/false, 1/0, yes/no |

Invalid values raise a configuration error. Existing face preferences are stored locally. Provider credentials must never be committed or logged.

## Known limitations and roadmap

- The desktop prototype does not control physical robot hardware.
- Session conversation context is bounded and temporary; it is not long-term personal memory.
- Weather uses Open-Meteo and news uses RSS. The target-independent robot must eventually prove that it can retrieve information over its own connection with the development laptop powered off and Ollama unavailable.
- No final robot computer, network transport, display, enclosure, or movement hardware has been selected.
- The next software stages are to strengthen natural conversation and clarification handling, build a behaviour/reaction engine, improve voice turn-taking and latency, evaluate neural TTS, and design user-controlled memory. Hardware and movement come later.

Consult the project roadmap, technology decisions, and brain specification for the fuller requirements and decisions.
