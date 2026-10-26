"""Hands-free, local wake-word voice control for DEBO.

The microphone stays open while DEBO is running. Speech is split using a simple
voice-activity detector, then transcribed locally with faster-whisper. Utterances
are ignored unless they contain the wake phrase, or follow it within the wake window.
"""
from __future__ import annotations

import math
import queue
import re
import struct
import tempfile
import threading
import time
import wave
from pathlib import Path

SAMPLE_RATE = 16_000
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2
DEFAULT_MODEL = "base.en"
FRAME_SECONDS = 0.10
SILENCE_SECONDS = 0.85
MIN_SPEECH_SECONDS = 0.30
MAX_SPEECH_SECONDS = 14.0
WAKE_WINDOW_SECONDS = 8.0
ENERGY_THRESHOLD = 430


class VoiceError(RuntimeError):
    """A recoverable microphone, transcription, or speech setup problem."""


class VoiceController:
    """Continuously listen for 'Hey DEBO', then automatically capture a command."""
    def __init__(self, spoken_responses: bool = True) -> None:
        self.spoken_responses = bool(spoken_responses)
        self._stream = None
        self._model = None
        self._model_lock = threading.Lock()
        self._closed = False
        self._listening = False
        self._audio_queue: queue.Queue[bytes | None] = queue.Queue(maxsize=240)
        self._listener_thread: threading.Thread | None = None
        self._event_callback = None
        self._wake_until = 0.0
        self._speech_queue: queue.Queue[str | None] = queue.Queue()
        self._speech_thread: threading.Thread | None = None

    @property
    def listening(self) -> bool:
        return self._listening and not self._closed

    def start_wake_listening(self, callback) -> None:
        """Start continuous microphone capture; callback receives (event, text)."""
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
            target=self._listen_loop, name="debo-wake-listener", daemon=True
        )
        self._listener_thread.start()

    def _emit(self, event: str, text: str = "") -> None:
        callback = self._event_callback
        if callback is not None and not self._closed:
            try:
                callback(event, text)
            except Exception:
                pass

    def _audio_callback(self, indata, _frames, _time_info, _status) -> None:
        if self._closed:
            return
        try:
            self._audio_queue.put_nowait(indata.tobytes())
        except queue.Full:
            # Keep recent audio rather than letting latency grow indefinitely.
            try:
                self._audio_queue.get_nowait()
                self._audio_queue.put_nowait(indata.tobytes())
            except (queue.Empty, queue.Full):
                pass

    @staticmethod
    def _rms(chunk: bytes) -> float:
        if len(chunk) < 2:
            return 0.0
        samples = struct.unpack("<" + "h" * (len(chunk) // 2), chunk[:len(chunk) // 2 * 2])
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
                if self._wake_until and time.monotonic() > self._wake_until:
                    self._wake_until = 0.0
                    self._emit("standby", "")
                continue
            if chunk is None:
                break
            if self._wake_until and time.monotonic() > self._wake_until:
                self._wake_until = 0.0
                self._emit("standby", "")
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
                if loud:
                    silence_frames = 0
                else:
                    silence_frames += 1
                if silence_frames >= frame_count or len(frames) >= max_frames:
                    utterance = b"".join(frames)
                    if len(frames) >= min_frames:
                        self._process_utterance(utterance)
                    frames, pre_roll = [], []
                    speech_started = False
                    silence_frames = 0

    def _process_utterance(self, audio: bytes) -> None:
        path = None
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
            self._emit("voice_error", str(error))
            return
        except Exception:
            self._emit("voice_error", "I had trouble processing that audio. I'm still listening for 'Hey DEBO'.")
            return
        finally:
            if path is not None:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
        normalised = self._normalise(transcript)
        wake = re.search(r"\b(?:hey|hi|okay|ok|hello)\s+(?:there\s+)?(?:debo|deebo|deb[o0])\b", normalised)
        if wake:
            remainder = normalised[wake.end():].strip(" ,.!?:;-")
            self._wake_until = time.monotonic() + WAKE_WINDOW_SECONDS
            self._emit("wake", transcript)
            if remainder:
                self._wake_until = 0.0
                self._emit("transcript", remainder)
            return
        if self._wake_until and time.monotonic() <= self._wake_until:
            self._wake_until = 0.0
            self._emit("transcript", transcript.strip())

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
            transcript = " ".join(segment.text.strip() for segment in segments).strip()
            return transcript
        except VoiceError:
            raise
        except Exception as error:
            raise VoiceError(
                "I couldn't run local speech recognition. The first model download needs internet; "
                "after that, recognition runs on this computer."
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
                        "I couldn't load DEBO's local speech model. Its first download needs internet."
                    ) from error
            return self._model

    def speak_async(self, text: str) -> None:
        cleaned = re.sub(r"https?://\S+", "", str(text))
        cleaned = " ".join(cleaned.split())
        if not cleaned or not self.spoken_responses or self._closed:
            return
        if self._speech_thread is None or not self._speech_thread.is_alive():
            self._speech_thread = threading.Thread(target=self._speech_loop, name="debo-speech-output", daemon=True)
            self._speech_thread.start()
        self._speech_queue.put(cleaned)

    def _speech_loop(self) -> None:
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", 178)
            engine.setProperty("volume", 0.9)
        except Exception:
            return
        while not self._closed:
            try:
                text = self._speech_queue.get(timeout=0.25)
            except queue.Empty:
                continue
            if text is None:
                break
            try:
                engine.say(text)
                engine.runAndWait()
            except Exception:
                continue
        try:
            engine.stop()
        except Exception:
            pass

    def close(self) -> None:
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
            pass
        self._speech_queue.put(None)
