"""Characterful speech synthesis for DEBO.

Uses the operating system's installed voice (via pyttsx3), then applies a
subtle, intelligibility-first modulation on Windows. This is an original
robotic treatment, not a copy of any character voice.
"""
from __future__ import annotations

import array
import logging
import math
import os
import sys
import tempfile
import threading
import wave
from pathlib import Path

try:
    import winsound
except ImportError:
    winsound = None


class SpeechSynthesizer:
    """Generate speech off the UI thread; optionally add a light robotic timbre."""

    def __init__(self, enabled: bool = True, volume: float = 0.85, rate: int = 178) -> None:
        self.enabled = bool(enabled)
        self.volume = max(0.0, min(1.0, float(volume)))
        self.rate = max(120, min(230, int(rate)))
        self._closed = False
        self._lock = threading.Lock()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)

    def set_volume(self, volume: float) -> None:
        self.volume = max(0.0, min(1.0, float(volume)))

    def set_rate(self, rate: int) -> None:
        self.rate = max(120, min(230, int(rate)))

    def speak(self, text: str) -> None:
        """Speak text synchronously; callers should use a dedicated worker thread."""
        text = " ".join(str(text).split())
        if not text or not self.enabled or self._closed:
            return
        try:
            import pyttsx3
        except ImportError as error:
            raise RuntimeError("Speech synthesis is missing. Run uv sync --all-groups.") from error

        engine = pyttsx3.init()
        try:
            engine.setProperty("rate", self.rate)
            engine.setProperty("volume", self.volume)
            self._select_english_voice(engine)
            if winsound is None:
                engine.say(text)
                engine.runAndWait()
                return

            with tempfile.TemporaryDirectory(prefix="debo_tts_") as directory:
                raw_path = Path(directory) / "speech.wav"
                processed_path = Path(directory) / "debo_voice.wav"
                engine.save_to_file(text, os.fspath(raw_path))
                engine.runAndWait()
                if not raw_path.exists() or raw_path.stat().st_size < 48:
                    # Some SAPI voices fail to render to file; retain speech rather than silence.
                    engine.say(text)
                    engine.runAndWait()
                    return
                self._robotise_wav(raw_path, processed_path)
                if not self.enabled or self._closed:
                    return
                with self._lock:
                    winsound.PlaySound(
                        os.fspath(processed_path),
                        winsound.SND_FILENAME | winsound.SND_SYNC | winsound.SND_NODEFAULT,
                    )
        finally:
            try:
                engine.stop()
            except (RuntimeError, OSError, AttributeError):
                logging.getLogger(__name__).debug("Could not stop TTS engine", exc_info=True)

    @staticmethod
    def _select_english_voice(engine) -> None:
        try:
            voices = engine.getProperty("voices") or []
            descriptors = [
                (voice, f"{getattr(voice, 'id', '')} {getattr(voice, 'name', '')}".lower())
                for voice in voices
            ]
            preferred_markers = ("engb", "en-gb", "en_gb", "british", "united kingdom")
            for voice, descriptor in descriptors:
                if any(marker in descriptor for marker in preferred_markers):
                    engine.setProperty("voice", voice.id)
                    return
            for voice, descriptor in descriptors:
                if "english" in descriptor or "en-us" in descriptor or "en_us" in descriptor:
                    engine.setProperty("voice", voice.id)
                    return
        except (RuntimeError, OSError, AttributeError, TypeError):
            logging.getLogger(__name__).debug("Could not select an English TTS voice", exc_info=True)

    @staticmethod
    def _robotise_wav(source: Path, destination: Path) -> None:
        """Apply restrained ring modulation and saturation while preserving speech."""
        with wave.open(os.fspath(source), "rb") as reader:
            params = reader.getparams()
            raw = reader.readframes(reader.getnframes())
        if params.sampwidth != 2 or params.nchannels not in (1, 2):
            with wave.open(os.fspath(destination), "wb") as writer:
                writer.setparams(params)
                writer.writeframes(raw)
            return

        samples = array.array("h")
        samples.frombytes(raw)
        if sys.byteorder != "little":
            samples.byteswap()
        rate = params.framerate
        for index, sample in enumerate(samples):
            time_seconds = (index // params.nchannels) / max(1, rate)
            carrier = (
                0.78
                + 0.22 * math.sin(2.0 * math.pi * 34.0 * time_seconds)
                + 0.06 * math.sin(2.0 * math.pi * 57.0 * time_seconds)
            )
            value = sample * carrier
            # A tiny soft clip rounds harsh peaks without making speech unintelligible.
            shaped = int(32767.0 * math.tanh(value / 39000.0))
            samples[index] = max(-32768, min(32767, shaped))
        if sys.byteorder != "little":
            samples.byteswap()
        with wave.open(os.fspath(destination), "wb") as writer:
            writer.setparams(params)
            writer.writeframes(samples.tobytes())

    def close(self) -> None:
        self._closed = True
        if winsound is not None:
            try:
                winsound.PlaySound(None, winsound.SND_PURGE)
            except RuntimeError:
                logging.getLogger(__name__).debug("Could not purge speech playback", exc_info=True)
