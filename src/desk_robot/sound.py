"""Small, dependency-free sound effects system for DEBO.

Windows playback uses winsound. Other platforms safely remain silent.
"""

from __future__ import annotations

import math
import os
import tempfile
import threading
import wave
from pathlib import Path

try:
    import winsound
except ImportError:  # Not available outside Windows.
    winsound = None


SAMPLE_RATE = 22050

# Each event is a sequence of (frequency in Hz, duration in seconds).
SOUNDS: dict[str, tuple[tuple[float, float], ...]] = {
    "startup": ((520, 0.055), (740, 0.07), (1040, 0.12)),
    "send": ((610, 0.045), (830, 0.055)),
    "thinking": ((430, 0.08), (575, 0.065), (500, 0.10)),
    "success": ((620, 0.055), (820, 0.06), (1120, 0.08), (940, 0.13)),
    "error": ((390, 0.075), (310, 0.10), (225, 0.15)),
    "click": ((760, 0.035), (1020, 0.025)),
    "curious": ((460, 0.065), (690, 0.055), (920, 0.12)),
}


class SoundManager:
    """Generate and asynchronously play short robotic sounds."""

    def __init__(
        self,
        enabled: bool = True,
        volume: float = 0.55,
    ) -> None:
        self.enabled = bool(enabled)
        self.volume = self._clamp_volume(volume)
        self._closed = False
        self._lock = threading.Lock()
        self._directory = Path(tempfile.gettempdir()) / "debo_sounds"
        self._directory.mkdir(parents=True, exist_ok=True)
        self._files: dict[tuple[str, int], Path] = {}

    @staticmethod
    def _clamp_volume(volume: float) -> float:
        return max(0.0, min(1.0, float(volume)))

    def play(self, event: str) -> None:
        """Play a named sound without blocking the calling UI thread."""
        if (
            not self.enabled
            or self._closed
            or winsound is None
            or event not in SOUNDS
            or self.volume <= 0
        ):
            return

        try:
            volume_level = round(self.volume * 100)
            key = (event, volume_level)
            path = self._files.get(key)

            if path is None or not path.exists():
                path = self._generate_wav(event, volume_level)
                self._files[key] = path

            with self._lock:
                if self._closed or not self.enabled:
                    return
                winsound.PlaySound(
                    os.fspath(path),
                    winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
                )
        except OSError, RuntimeError:
            # Audio is optional; sound failures must not break DEBO.
            return

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        if not self.enabled:
            self._stop_playback()

    def set_volume(self, volume: float) -> None:
        self.volume = self._clamp_volume(volume)

    def _stop_playback(self) -> None:
        if winsound is None:
            return
        try:
            winsound.PlaySound(None, winsound.SND_PURGE)
        except RuntimeError:
            pass

    def close(self) -> None:
        self._closed = True
        self._stop_playback()

    def _generate_wav(self, event: str, volume_level: int) -> Path:
        """Create a small 16-bit mono WAV file for one sound event."""
        path = self._directory / f"v2_{event}_{volume_level}.wav"
        if path.exists():
            return path

        volume = volume_level / 100
        amplitude = int(10000 * volume)
        audio = bytearray()

        for note_index, (frequency, duration) in enumerate(SOUNDS[event]):
            sample_count = int(SAMPLE_RATE * duration)
            # Each note bends and wobbles slightly; layered harmonics make it
            # feel like a tiny electro-mechanical voice rather than a pure beep.
            bend = 1.0 if note_index % 2 == 0 else 0.88
            phase = 0.0
            for index in range(sample_count):
                progress = index / max(1, sample_count - 1)
                fade_in = min(1.0, index / 150)
                fade_out = min(1.0, (sample_count - index) / 240)
                envelope = max(0.0, min(fade_in, fade_out))
                wobble = math.sin(2 * math.pi * 7.0 * index / SAMPLE_RATE) * 0.018
                instant_frequency = frequency * (bend + (1.0 - bend) * progress + wobble)
                phase += 2 * math.pi * instant_frequency / SAMPLE_RATE
                fundamental = math.sin(phase)
                harmonic = 0.32 * math.sin(phase * 2.01 + 0.2)
                overtone = 0.12 * math.sin(phase * 3.97 + 0.7)
                sample = int(amplitude * envelope * (fundamental + harmonic + overtone) * 0.68)
                audio.extend(sample.to_bytes(2, byteorder="little", signed=True))

            # A tiny breath-like gap helps each multi-tone chirp read as a phrase.
            audio.extend(b"\x00\x00" * int(SAMPLE_RATE * 0.012))

        with wave.open(os.fspath(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(SAMPLE_RATE)
            output.writeframes(audio)

        return path
