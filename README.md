# DEBO — visual-first desktop companion

DEBO is a Python/Tkinter desktop companion with a morphing animated face, local wake-word speech recognition, concise command handling, live weather, and RSS news. Its responses are visual-first: **there is no text-to-speech output pipeline**.

## Requirements

- Python 3.14 or newer (matches `pyproject.toml`).
- `uv` for dependency and environment management.
- A microphone for wake-word interaction; local speech recognition downloads/loads the `base.en` model on first run.
- Internet access for live weather and news. Weather uses Open-Meteo; news uses the configured BBC News UK RSS feed.

## Install and run on Windows

From the repository directory in PowerShell:

```powershell
uv sync --all-groups
uv run python -m desk_robot.face
```

The first run may take longer while faster-whisper downloads its local recognition model. DEBO will still launch without microphone access, but wake-word input will report an unavailable state.

## Commands

Say **“Hey DEBO”**, then ask for a supported command. You can combine the wake phrase and command in one utterance.

- Greetings and basic personality interactions.
- “Weather in London” — current conditions plus today's high/low when the provider supplies them.
- “Show me the news” — a featured headline and a smoothly scrolling ticker.
- “Next story” — advances the featured news item from the latest retrieved feed.
- “What did I just say?” — recalls the previous user message.
- “Help” — lists the supported interaction hints.

Weather and news are retrieved asynchronously, and the interface shows source/retrieval metadata where available. If a provider is unavailable or returns incomplete data, DEBO displays an unavailable state rather than inventing live facts.

## Development checks

```powershell
uv lock
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Run `uv lock` after pulling this change to regenerate `uv.lock` for the removal of speech-synthesis dependencies. The repository's existing lockfile could not be regenerated in the remote editing environment.

## Interaction design

- The eye renderer uses native Tkinter Canvas geometry and eased shape interpolation.
- Wake-word listening and transcription stay in background threads; Tkinter widgets are only updated on the UI thread.
- Weather and news network requests run through the existing background command executor.
- New commands supersede stale UI responses by request ID, so a late result does not replace the newest interaction.
- Idle blinking, gaze changes, and expression morphs remain interruptible by active interaction.

## Notes

The project is still a desktop software prototype. It does not yet control physical robot hardware or movement. Live provider integrations and microphone behaviour should be tested on the target Windows machine.
