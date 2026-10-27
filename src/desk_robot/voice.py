"""Hands-free local wake-word voice input for DEBO.

This module owns microphone capture and speech recognition only. DEBO's
responses are visual; no speech synthesis or audio playback pipeline exists.
"""
from __future__ import annotations

import difflib
import logging
import math
import queue
import re
import struct
import tempfile
import threading
import time
import wave
from pathlib import Path

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16_000
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2
DEFAULT_MODEL = "base.en"
FRAME_SECONDS = 0.10
SILENCE_SECONDS = 0.85
MIN_SPEECH_SECONDS = 0.30
MAX_SPEECH_SECONDS = 14.0
WAKE_WINDOW_SECONDS = 8.0
ENERGY_THRESHOLD = 100


class VoiceError(RuntimeError):
    """A recoverable microphone or transcription setup problem."""


class VoiceController:
    """Continuously listen for 'Hey DEBO', then capture a command."""

    def __init__(self) -> None:
        self._stream = None
        self._model = None
        self._model_lock = threading.Lock()
        self._closed = False
        self._listening = False
        self._audio_queue: queue.Queue[bytes | None] = queue.Queue(maxsize=240)
        self._listener_thread: threading.Thread | None = None
        self._model_thread: threading.Thread | None = None
        self._model_ready = threading.Event()
        self._model_error: str | None = None
        self._event_callback = None
        self._wake_until = 0.0

    @property
    def listening(self) -> bool:
        return self._listening and not self._closed

    def start_wake_listening(self, callback) -> None:
        """Start microphone capture. Callback receives (event, text)."""
        if self._closed:
            raise VoiceError("Voice input is shutting down. Restart DEBO to use the microphone.")
        if self._listening:
            return
        try:
            import sounddevice as sd
        except ImportError as error:
            raise VoiceError("Microphone support is missing. Run `uv sync --all-groups`.") from error

        self._event_callback = callback
        try:
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="int16",
                blocksize=int(SAMPLE_RATE * FRAME_SECONDS), callback=self._audio_callback,
            )
            self._stream.start()
        except Exception as error:
            self._stream = None
            raise VoiceError(
                "I couldn't access a microphone. Check Windows microphone permissions and your input device."
            ) from error

        self._listening = True
        self._listener_thread = threading.Thread(
            target=self._listen_loop, name="debo-wake-listener", daemon=True,
        )
        self._listener_thread.start()
        self._emit("model_loading", "Preparing local speech recognition…")
        self._model_thread = threading.Thread(
            target=self._warm_model, name="debo-model-warmup", daemon=True,
        )
        self._model_thread.start()

    def _warm_model(self) -> None:
        try:
            self._get_model()
            self._drain_audio_queue()
            if not self._closed:
                self._model_ready.set()
                self._emit("model_ready", "Listening for Hey DEBO")
        except VoiceError as error:
            self._model_error = str(error)
            self._emit("model_error", self._model_error)

    def _emit(self, event: str, text: str = "") -> None:
        callback = self._event_callback
        if callback is not None and not self._closed:
            try:
                callback(event, text)
            except Exception:
                logger.exception("Voice event callback failed for event %r", event)

    def _audio_callback(self, indata, _frames, _time_info, status) -> None:
        if self._closed or not self._model_ready.is_set():
            return
        if status:
            logger.warning("Microphone stream status: %s", status)
        try:
            self._audio_queue.put_nowait(indata.tobytes())
        except queue.Full:
            try:
                self._audio_queue.get_nowait()
                self._audio_queue.put_nowait(indata.tobytes())
            except (queue.Empty, queue.Full):
                pass

    @staticmethod
    def _rms(chunk: bytes) -> float:
        usable_length = len(chunk) // 2 * 2
        if usable_length < 2:
            return 0.0
        samples = struct.unpack("<" + "h" * (usable_length // 2), chunk[:usable_length])
        return math.sqrt(sum(sample * sample for sample in samples) / len(samples))

    def _listen_loop(self) -> None:
        frames: list[bytes] = []
        pre_roll: list[bytes] = []
        speech_started = False
        silence_frames = 0
        frame_count = max(1, round(SILENCE_SECONDS / FRAME_SECONDS))
        min_frames = max(1, round(MIN_SPEECH_SECONDS / FRAME_SECONDS))
        max_frames = max(1, round(MAX_SPEECH_SECONDS / FRAME_SECONDS))

        while not self._closed and self._listening:
            try:
                chunk = self._audio_queue.get(timeout=0.2)
            except queue.Empty:
                self._expire_wake_window()
                continue
            if chunk is None:
                break
            self._expire_wake_window()
            loud = self._rms(chunk) >= ENERGY_THRESHOLD
            if not speech_started:
                pre_roll.append(chunk)
                pre_roll = pre_roll[-3:]
                if loud:
                    speech_started = True
                    frames = list(pre_roll)
                    silence_frames = 0
            else:
                frames.append(chunk)
                silence_frames = 0 if loud else silence_frames + 1
                if silence_frames >= frame_count or len(frames) >= max_frames:
                    if len(frames) >= min_frames:
                        self._process_utterance(b"".join(frames))
                    frames, pre_roll = [], []
                    speech_started = False
                    silence_frames = 0

    def _expire_wake_window(self) -> None:
        if self._wake_until and time.monotonic() > self._wake_until:
            self._wake_until = 0.0
            self._emit("standby", "")

    def _process_utterance(self, audio: bytes) -> None:
        if not self._model_ready.is_set() or self._closed:
            return
        path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(prefix="debo_voice_", suffix=".wav", delete=False) as file:
                path = Path(file.name)
            with wave.open(str(path), "wb") as output:
                output.setnchannels(CHANNELS)
                output.setsampwidth(SAMPLE_WIDTH_BYTES)
                output.setframerate(SAMPLE_RATE)
                output.writeframes(audio)
            transcript = self._transcribe_file(path)
        except VoiceError as error:
            self._emit("transcription_error", str(error))
            return
        except Exception as error:
            self._emit("transcription_error", f"Audio transcription failed ({type(error).__name__}): {error}")
            return
        finally:
            if path is not None:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    logger.debug("Could not remove temporary voice recording", exc_info=True)

        if self._closed:
            return
        normalised = self._normalise(transcript)
        if not normalised:
            return
        wake = self._find_wake_phrase(normalised)
        if wake is not None:
            remainder = normalised[wake[1]:].strip(" ,.!?:;-")
            self._wake_until = time.monotonic() + WAKE_WINDOW_SECONDS
            self._emit("wake", transcript)
            if remainder:
                self._wake_until = 0.0
                self._emit("transcript", remainder)
            return
        if self._wake_until and time.monotonic() <= self._wake_until:
            self._wake_until = 0.0
            command = transcript.strip()
            if command:
                self._emit("transcript", command)

    @staticmethod
    def _find_wake_phrase(text: str) -> tuple[int, int] | None:
        normalised = VoiceController._normalise(text)
        words = list(re.finditer(r"\b[\w']+\b", normalised))
        greetings = {"hey", "hi", "okay", "ok", "hello"}
        targets = ("debo", "deebo", "thebo", "deevo", "devo", "deb0")
        for index, word in enumerate(words):
            if word.group() not in greetings or index + 1 >= len(words):
                continue
            for end_index in range(index + 1, min(index + 3, len(words))):
                candidate_words = words[index + 1:end_index + 1]
                compact = "".join(match.group() for match in candidate_words)
                if not 3 <= len(compact) <= 6:
                    continue
                score = max(difflib.SequenceMatcher(None, compact, target).ratio() for target in targets)
                if compact in targets or score >= 0.75:
                    return word.start(), candidate_words[-1].end()
        return None

    @staticmethod
    def _normalise(text: str) -> str:
        return re.sub(r"\s+", " ", str(text).strip().lower())

    def _transcribe_file(self, path: Path) -> str:
        try:
            model = self._get_model()
            segments, _info = model.transcribe(
                str(path), language="en", beam_size=3, vad_filter=True,
                condition_on_previous_text=False,
            )
            return " ".join(segment.text.strip() for segment in segments).strip()
        except VoiceError:
            raise
        except Exception as error:
            raise VoiceError(
                f"Speech transcription failed after the local model loaded ({type(error).__name__}): {error}"
            ) from error

    def _get_model(self):
        with self._model_lock:
            if self._model is None:
                try:
                    from faster_whisper import WhisperModel
                except ImportError as error:
                    raise VoiceError("Speech recognition isn't installed. Run `uv sync --all-groups`.") from error
                try:
                    self._model = WhisperModel(DEFAULT_MODEL, device="cpu", compute_type="int8")
                except Exception as error:
                    raise VoiceError(
                        f"Could not load local speech model '{DEFAULT_MODEL}' ({type(error).__name__}): {error}. "
                        "Check the model cache or network access if this is the first run."
                    ) from error
            return self._model

    def _drain_audio_queue(self) -> None:
        while True:
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                return

    def close(self) -> None:
        """Stop microphone capture and join input workers without blocking the UI indefinitely."""
        if self._closed:
            return
        self._closed = True
        self._listening = False
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass
        try:
            self._audio_queue.put_nowait(None)
        except queue.Full:
            try:
                self._audio_queue.get_nowait()
                self._audio_queue.put_nowait(None)
            except (queue.Empty, queue.Full):
                pass
        current = threading.current_thread()
        for worker in (self._listener_thread, self._model_thread):
            if worker is not None and worker is not current:
                worker.join(timeout=0.5)
        logger.info("Voice input shutdown complete")
