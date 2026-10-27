# DEBO — expressive desktop robot companion

DEBO is a Python/Tkinter desktop companion with a responsive, morphing face, local wake-word speech recognition, character sound effects, text-to-speech, live weather, and RSS news. The design goal is an original little robot personality: quick expressions, playful electronic chirps, and spoken responses.

## Requirements

- Python 3.14 or newer (matches `pyproject.toml`).
- `uv` for dependency and environment management.
- A microphone for wake-word interaction; local speech recognition downloads/loads the `base.en` model on first run.
- Internet access for live weather, news headlines, and article reading.
- Windows is the primary audio target. DEBO uses installed system voices through `pyttsx3`; on Windows, generated speech is subtly modulated for a more electronic timbre.

## Install and run on Windows

From the repository directory in PowerShell:

```powershell
uv lock
uv sync --all-groups
uv run python -m desk_robot.face
```

The first run may take longer while faster-whisper downloads its local recognition model. DEBO will still launch without microphone access, but wake-word input will report an unavailable state. The voice uses a locally installed system voice; no cloud TTS account is required.

## Voice commands

Say **“Hey DEBO”**, then give a command. You can combine the wake phrase and command in one utterance.

- “Weather in London” — current conditions and today's high/low when available. DEBO reads the result aloud when speech is enabled.
- “Show me the news” — presents the current headline and cycles through the full headline ticker automatically.
- “Next story” — selects the next headline.
- “Read the full story” — fetches and reads the currently selected article, when the publisher allows its text to be extracted.
- “Change my eye colour to blue” — also supports teal, light blue, purple, pink, green, lime, red, orange, yellow, white, and gold.
- “Animation speed fast”, “animation speed normal”, or “animation speed slow”.
- “Turn sound off” / “turn sound on”.
- “Turn speech off” / “turn speech on”.
- “Speech volume 70” or “sound volume 40”.
- “Settings” — gives examples of spoken preference commands.
- “What did I just say?” — recalls the previous user message.
- “Help” — lists supported interaction hints.

Speech pauses microphone capture while playing, then resumes wake-word detection, to avoid DEBO hearing its own voice. You can turn speech off and continue using the visual interface.

## Face and sound design

- Eye silhouettes are continuously interpolated, with shorter reaction morphs and interruptible blinks/gaze changes.
- The ticker scrolls each headline separately; long headlines naturally remain visible longer because the scroll time depends on their rendered width.
- Sound effects use layered harmonics, slight pitch bends and vibrato to produce richer electronic chirps instead of plain sine beeps.
- Speech uses the installed English system voice plus restrained audio modulation. This is an original DEBO sound, not an exact reproduction of Vector or WALL-E.
- Voice-controlled settings and the settings dialog both persist preferences in `~/.debo_face_settings.json`.

## Development checks

```powershell
uv lock
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

The RSS feed currently defaults to BBC News UK. Article text extraction is best-effort: some publishers render content dynamically, require sign-in, or block automated requests. In those cases DEBO will explain that the full story could not be extracted instead of reading an unrelated page.

## Project status

DEBO is still a desktop software prototype. It does not yet control physical robot hardware or movement. Test microphone permissions, system voice availability, speech playback, and live information retrieval on the target Windows machine.
