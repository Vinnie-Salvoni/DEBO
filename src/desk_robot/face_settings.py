"""Persistent desktop-face preferences, independent of the renderer."""

from __future__ import annotations

import json
from pathlib import Path

SETTINGS_PATH = Path.home() / ".debo_face_settings.json"

DEFAULT_SETTINGS = {
    "eye_color": "#00D9D0",
    "accent_color": "#4D9DFF",
    "glow": 58,
    "animation_speed": 1.0,
    "automatic_accents": True,
    "sound_enabled": True,
    "sound_volume": 55,
    "speech_enabled": True,
    "speech_volume": 85,
    "speech_rate": 178,
}

def load_settings() -> dict:
    """Load saved settings, validating values and falling back safely."""
    settings = DEFAULT_SETTINGS.copy()
    try:
        saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        if isinstance(saved, dict):
            settings.update({key: value for key, value in saved.items() if key in settings})
    except (OSError, json.JSONDecodeError):
        pass
    try:
        settings["glow"] = max(0, min(100, int(settings["glow"])))
        settings["animation_speed"] = max(0.5, min(2.0, float(settings["animation_speed"])))
        settings["sound_volume"] = max(0, min(100, int(settings["sound_volume"])))
        settings["speech_volume"] = max(0, min(100, int(settings["speech_volume"])))
        settings["speech_rate"] = max(120, min(230, int(settings["speech_rate"])))
        for key in ("automatic_accents", "sound_enabled", "speech_enabled"):
            settings[key] = bool(settings[key])
        for key in ("eye_color", "accent_color"):
            value = str(settings[key])
            if len(value) != 7 or not value.startswith("#"):
                raise ValueError(f"Invalid colour: {value}")
            int(value[1:], 16)
            settings[key] = value
    except (TypeError, ValueError, OverflowError):
        return DEFAULT_SETTINGS.copy()
    return settings


def save_settings(settings: dict) -> None:
    try:
        SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except OSError:
        pass


