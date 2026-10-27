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
    "startup": ((660, 0.075), (880, 0.11)),
    "send": ((520, 0.055),),
    "thinking": ((440, 0.065), (554, 0.07)),
    "success": ((660, 0.065), (784, 0.07), (1046, 0.12)),
    "error": ((330, 0.12), (247, 0.17)),
    "click": ((720, 0.04),),
    "curious": ((500, 0.075), (740, 0.10)),
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
        path = self._directory / f"{event}_{volume_level}.wav"
        if path.exists():
            return path

        volume = volume_level / 100
        amplitude = int(10000 * volume)
        audio = bytearray()

        for frequency, duration in SOUNDS[event]:
            sample_count = int(SAMPLE_RATE * duration)

            for index in range(sample_count):
                # Fade each note in and out to avoid harsh clicks.
                fade_in = min(1.0, index / 180)
                fade_out = min(1.0, (sample_count - index) / 260)
                envelope = max(0.0, min(fade_in, fade_out))
                sample = int(
                    amplitude
                    * envelope
                    * math.sin(2 * math.pi * frequency * index / SAMPLE_RATE)
                )
                audio.extend(sample.to_bytes(2, byteorder="little", signed=True))

            # A short silence makes consecutive notes sound like a chirp.
            audio.extend(b"\x00\x00" * int(SAMPLE_RATE * 0.018))

        with wave.open(os.fspath(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(SAMPLE_RATE)
            output.writeframes(audio)

        return path
