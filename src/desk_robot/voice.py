
"""Hands-free, local wake-word voice control for DEBO.

The microphone stays open while DEBO is running. Speech is split using a
simple voice-activity detector, then transcribed locally with faster-whisper.
Utterances are ignored unless they contain the wake phrase or follow it
within the wake window.
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
import difflib
import logging

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
    """A recoverable microphone, transcription, or speech setup problem."""


class VoiceController:
    """Continuously listen for 'Hey DEBO', then capture a command."""

    def __init__(self, spoken_responses: bool = True) -> None:
        self.spoken_responses = bool(spoken_responses)
        self._stream = None
        self._model = None
        self._model_lock = threading.Lock()
        self._closed = False
        self._listening = False

        self._audio_queue: queue.Queue[bytes | None] = queue.Queue(
            maxsize=240
        )
        self._listener_thread: threading.Thread | None = None
        self._model_thread: threading.Thread | None = None
        self._model_ready = threading.Event()
        self._model_error: str | None = None

        self._event_callback = None
        self._wake_until = 0.0

        self._speech_queue: queue.Queue[str | None] = queue.Queue()
        self._speech_thread: threading.Thread | None = None
        self._speaking = threading.Event()
        self._speech_state_lock = threading.Lock()
        self._speech_pending = 0

    @property
    def listening(self) -> bool:
        return self._listening and not self._closed

    def start_wake_listening(self, callback) -> None:
        """Start microphone capture. Callback receives (event, text)."""
        if self._closed:
            raise VoiceError(
                "Voice input is shutting down. Restart DEBO to use the microphone."
            )

        if self._listening:
            return

        try:
            import sounddevice as sd
        except ImportError as error:
            raise VoiceError(
                "Microphone support is missing. Run `uv sync --all-groups`."
            ) from error

        self._event_callback = callback

        try:
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=int(SAMPLE_RATE * FRAME_SECONDS),
                callback=self._audio_callback,
            )
            self._stream.start()
        except Exception as error:
            self._stream = None
            raise VoiceError(
                "I couldn't access a microphone. Check Windows microphone "
                "permissions and your input device."
            ) from error

        self._listening = True

        self._listener_thread = threading.Thread(
            target=self._listen_loop,
            name="debo-wake-listener",
            daemon=True,
        )
        self._listener_thread.start()

        # Start downloading/loading the model immediately in the background.
        self._emit(
            "model_loading",
            "Downloading/loading local speech model...",
        )
        self._model_thread = threading.Thread(
            target=self._warm_model,
            name="debo-model-warmup",
            daemon=True,
        )
        self._model_thread.start()

    def _warm_model(self) -> None:
        """Load the recognition model without blocking the GUI."""
        try:
            self._get_model()
            # Drop audio captured while the model was warming up before opening
            # the recognition gate, otherwise startup speech can be replayed.
            self._drain_audio_queue()
            self._model_ready.set()
            self._emit("model_ready", "Listening for Hey DEBO")
        except VoiceError as error:
            self._model_error = str(error)
            self._emit("model_error", self._model_error)

    def _emit(self, event: str, text: str = "") -> None:
        """Send an event to the GUI without touching GUI widgets here."""
        callback = self._event_callback
        if callback is not None and not self._closed:
            try:
                callback(event, text)
            except Exception:
                logger.exception("Voice event callback failed for event %r", event)

    def _audio_callback(
        self, indata, _frames, _time_info, _status
    ) -> None:
        """Called by sounddevice for each microphone audio block."""
        if self._closed or self._speaking.is_set() or not self._model_ready.is_set():
            return

        if _status:
            logger.warning("Microphone stream status: %s", _status)

        try:
            self._audio_queue.put_nowait(indata.tobytes())
        except queue.Full:
            # Discard the oldest block to prevent audio latency building up.
            try:
                self._audio_queue.get_nowait()
                self._audio_queue.put_nowait(indata.tobytes())
            except (queue.Empty, queue.Full):
                pass

    @staticmethod
    def _rms(chunk: bytes) -> float:
        """Calculate audio loudness for basic voice-activity detection."""
        usable_length = len(chunk) // 2 * 2
        if usable_length < 2:
            return 0.0

        samples = struct.unpack(
            "<" + "h" * (usable_length // 2),
            chunk[:usable_length],
        )
        return math.sqrt(
            sum(sample * sample for sample in samples) / len(samples)
        )

    def _listen_loop(self) -> None:
        """Split the live microphone stream into speech-sized recordings."""
        frames: list[bytes] = []
        pre_roll: list[bytes] = []
        speech_started = False
        silence_frames = 0
        was_speaking = False
        resume_quiet_frames = 0

        frame_count = max(
            1, round(SILENCE_SECONDS / FRAME_SECONDS)
        )
        min_frames = max(
            1, round(MIN_SPEECH_SECONDS / FRAME_SECONDS)
        )
        max_frames = max(
            1, round(MAX_SPEECH_SECONDS / FRAME_SECONDS)
        )

        while not self._closed and self._listening:
            try:
                chunk = self._audio_queue.get(timeout=0.2)
            except queue.Empty:
                if self._speaking.is_set():
                    frames = []
                    pre_roll = []
                    speech_started = False
                    silence_frames = 0
                    was_speaking = True
                    resume_quiet_frames = 3
                if (
                    self._wake_until
                    and time.monotonic() > self._wake_until
                ):
                    self._wake_until = 0.0
                    self._emit("standby", "")
                continue

            if chunk is None:
                break

            if self._speaking.is_set():
                frames = []
                pre_roll = []
                speech_started = False
                silence_frames = 0
                was_speaking = True
                resume_quiet_frames = 3
                continue

            if was_speaking:
                # Wait for real microphone silence after playback; do not
                # feed the speaker's acoustic tail into wake-word recognition.
                if self._rms(chunk) < ENERGY_THRESHOLD:
                    resume_quiet_frames -= 1
                else:
                    continue
                if resume_quiet_frames > 0:
                    continue
                was_speaking = False

            if (
                self._wake_until
                and time.monotonic() > self._wake_until
            ):
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

                if (
                    silence_frames >= frame_count
                    or len(frames) >= max_frames
                ):
                    utterance = b"".join(frames)

                    if len(frames) >= min_frames:
                        self._process_utterance(utterance)

                    frames = []
                    pre_roll = []
                    speech_started = False
                    silence_frames = 0

    def _process_utterance(self, audio: bytes) -> None:
        """Save and transcribe one utterance, then detect the wake phrase."""
        # Do not attempt transcription while the model is downloading.
        if (
            not self._model_ready.is_set()
            or self._speaking.is_set()
            or self._closed
        ):
            return

        path = None

        try:
            with tempfile.NamedTemporaryFile(
                prefix="debo_voice_",
                suffix=".wav",
                delete=False,
            ) as file:
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
            self._emit(
                "transcription_error",
                f"Audio transcription failed ({type(error).__name__}): {error}",
            )
            return
        finally:
            if path is not None:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass

        # TTS may have started while transcription was running. In that case
        # discard the result instead of treating it as a wake phrase or command.
        if self._speaking.is_set() or self._closed:
            return

        normalised = self._normalise(transcript)
        if not normalised:
            logger.debug("Whisper returned an empty transcript")
            return

        wake = self._find_wake_phrase(normalised)
        if wake is not None:
            # _find_wake_phrase returns character offsets, not a regex match.
            # Normalisation only changes case/whitespace, so these offsets are
            # valid for slicing the normalised transcript.
            remainder = normalised[wake[1]:].strip(" ,.!?:;-")
            self._wake_until = time.monotonic() + WAKE_WINDOW_SECONDS
            logger.info("Wake phrase recognised in a completed transcript")
            self._emit("wake", transcript)

            if remainder:
                # A combined wake phrase + command is a single interaction.
                self._wake_until = 0.0
                logger.info("Command captured with wake phrase (%d characters)", len(remainder))
                self._emit("transcript", remainder)
            return

        if self._wake_until and time.monotonic() <= self._wake_until:
            self._wake_until = 0.0
            command = transcript.strip()
            if command:
                logger.info("Command captured inside wake window (%d characters)", len(command))
                self._emit("transcript", command)
            return

        logger.debug("Ignoring transcript without wake phrase: %r", transcript)

    @staticmethod
    def _find_wake_phrase(text: str) -> tuple[int, int] | None:
        """Find 'Hey DEBO' with bounded tolerance for common Whisper variants.

        This is transcription-level fuzzy matching, not an acoustic wake-word
        model. Requiring a greeting plus a short name-like token sequence helps
        avoid triggering on unrelated words.
        """
        normalised = VoiceController._normalise(text)
        words = list(re.finditer(r"\b[\w']+\b", normalised))
        greetings = {"hey", "hi", "okay", "ok", "hello"}
        targets = ("debo", "deebo", "thebo", "deevo", "devo", "deb0")

        for index, word in enumerate(words):
            if word.group() not in greetings or index + 1 >= len(words):
                continue

            # Only inspect one or two following tokens; including command words
            # in the fuzzy candidate can create false positives.
            for end_index in range(index + 1, min(index + 3, len(words))):
                candidate_words = words[index + 1:end_index + 1]
                compact = "".join(match.group() for match in candidate_words)
                if not 3 <= len(compact) <= 6:
                    continue

                score = max(
                    difflib.SequenceMatcher(None, compact, target).ratio()
                    for target in targets
                )
                if compact in targets or score >= 0.75:
                    return word.start(), candidate_words[-1].end()

        return None

    @staticmethod
    def _normalise(text: str) -> str:
        return re.sub(r"\s+", " ", str(text).strip().lower())

    def _transcribe_file(self, path: Path) -> str:
        """Transcribe an audio file using the local Whisper model."""
        try:
            model = self._get_model()
            segments, _info = model.transcribe(
                str(path),
                language="en",
                beam_size=3,
                vad_filter=True,
                condition_on_previous_text=False,
            )
            return " ".join(
                segment.text.strip() for segment in segments
            ).strip()

        except VoiceError:
            raise
        except Exception as error:
            raise VoiceError(
                "Speech transcription failed after the local model loaded "
                f"({type(error).__name__}): {error}"
            ) from error

    def _get_model(self):
        """Create the model once; the lock prevents duplicate downloads."""
        with self._model_lock:
            if self._model is None:
                try:
                    from faster_whisper import WhisperModel
                except ImportError as error:
                    raise VoiceError(
                        "Speech recognition isn't installed. "
                        "Run `uv sync --all-groups`."
                    ) from error

                try:
                    self._model = WhisperModel(
                        DEFAULT_MODEL,
                        device="cpu",
                        compute_type="int8",
                    )
                except Exception as error:
                    raise VoiceError(
                        f"Could not load local speech model '{DEFAULT_MODEL}' "
                        f"({type(error).__name__}): {error}. Check the model cache "
                        "or network access if this is the first run."
                    ) from error

            return self._model

    def _drain_audio_queue(self) -> None:
        """Discard microphone blocks captured before recognition resumes."""
        while True:
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                return

    def speak_async(self, text: str) -> None:
        """Queue speech and suspend recognition until playback has finished."""
        cleaned = re.sub(r"https?://\S+", "", str(text))
        cleaned = " ".join(cleaned.split())
        if not cleaned or not self.spoken_responses or self._closed:
            return
        logger.info("Queueing TTS response (%d characters)", len(cleaned))
        with self._speech_state_lock:
            if self._speech_pending == 0:
                self._speaking.set()
                self._drain_audio_queue()
                self._emit("speaking_start", "")
            self._speech_pending += 1
            if self._speech_thread is None or not self._speech_thread.is_alive():
                self._speech_thread = threading.Thread(
                    target=self._speech_loop,
                    name="debo-speech-output",
                    daemon=True,
                )
                self._speech_thread.start()
            self._speech_queue.put(cleaned)

    def _finish_speech_item(self) -> None:
        with self._speech_state_lock:
            self._speech_pending = max(0, self._speech_pending - 1)
            if self._speech_pending == 0:
                # Keep capture muted while stale blocks are removed.
                self._drain_audio_queue()
                self._speaking.clear()
                self._emit("speaking_end", "")

    def _speech_loop(self) -> None:
        """Speak queued responses, isolating each Windows SAPI session.

        Recreate pyttsx3 for each response. On some Windows SAPI setups a
        reused engine returns from runAndWait quickly on later utterances
        without producing audible output.
        """
        logger.info("TTS worker started")
        while True:
            if self._closed and self._speech_queue.empty():
                break
            try:
                text = self._speech_queue.get(timeout=0.25)
            except queue.Empty:
                continue

            if text is None:
                self._speech_queue.task_done()
                break

            engine = None
            audio_path: Path | None = None
            stage = "initialisation"
            try:
                import pyttsx3

                logger.info("TTS stage=init: creating fresh pyttsx3 engine")
                engine = pyttsx3.init()
                voices = engine.getProperty("voices") or []
                selected = self._choose_robot_voice(voices)
                if selected is not None:
                    engine.setProperty("voice", selected.id)
                engine.setProperty("rate", 142)
                engine.setProperty("volume", 0.9)
                logger.info(
                    "TTS stage=init: engine ready; voices=%d selected=%s",
                    len(voices),
                    getattr(selected, "name", "system default"),
                )

                stage = "engine.render"
                delivered_text = self._robotic_delivery(text)
                with tempfile.NamedTemporaryFile(
                    prefix="debo_tts_", suffix=".wav", delete=False
                ) as audio_file:
                    audio_path = Path(audio_file.name)
                audio_path.unlink(missing_ok=True)

                logger.info(
                    "TTS stage=render: rendering %d characters to a temporary WAV",
                    len(delivered_text),
                )
                engine.save_to_file(delivered_text, str(audio_path))
                engine.runAndWait()

                stage = "audio.playback"
                logger.info("TTS stage=playback: applying robot effect and playing WAV")
                self._play_robot_voice_file(audio_path)
                logger.info("TTS stage=playback: output stream completed")
                audio_path.unlink(missing_ok=True)
            except Exception as error:
                logger.exception("TTS failed at stage=%s", stage)
                self._emit(
                    "tts_error",
                    f"TTS failed at {stage} ({type(error).__name__}): {error}",
                )
            finally:
                if audio_path is not None:
                    try:
                        audio_path.unlink(missing_ok=True)
                    except OSError:
                        logger.debug("Could not remove temporary TTS WAV", exc_info=True)
                if engine is not None:
                    try:
                        engine.stop()
                    except Exception:
                        logger.debug("TTS engine stop failed during cleanup", exc_info=True)
                self._speech_queue.task_done()
                self._finish_speech_item()

        logger.info("TTS worker stopped")

    @staticmethod
    def _play_robot_voice_file(path: Path) -> None:
        """Play rendered speech with a subtle electronic, robot-like timbre."""
        import numpy as np
        import sounddevice as sd

        with wave.open(str(path), "rb") as source:
            channels = source.getnchannels()
            sample_width = source.getsampwidth()
            sample_rate = source.getframerate()
            raw_audio = source.readframes(source.getnframes())

        if sample_width != 2:
            raise VoiceError(
                f"Speech renderer produced {sample_width * 8}-bit audio; expected 16-bit PCM."
            )

        samples = np.frombuffer(raw_audio, dtype="<i2")
        if channels > 1:
            samples = samples.reshape(-1, channels)
        audio = samples.astype(np.float32) / 32768.0

        # A restrained 32 Hz amplitude modulation adds an electronic edge
        # without destroying speech intelligibility. This is an original robot
        # effect, not an attempt to reproduce a specific character's voice.
        frame_count = len(audio)
        modulation = 0.84 + 0.16 * np.sin(
            2.0 * np.pi * 32.0 * np.arange(frame_count, dtype=np.float32) / sample_rate
        )
        if audio.ndim > 1:
            modulation = modulation[:, None]
        effected = np.tanh(audio * modulation * 1.12)
        effected = np.clip(effected, -1.0, 1.0)
        sd.play(effected, samplerate=sample_rate, blocking=True)

    @staticmethod
    def _choose_robot_voice(voices):
        """Prefer English voices, favouring lower/neutral voices if available."""
        ranked = []

        for voice in voices:
            name = (
                f"{getattr(voice, 'name', '')} "
                f"{getattr(voice, 'id', '')}"
            ).lower()

            languages = getattr(voice, "languages", []) or []
            language_text = " ".join(
                item.decode("utf-8", "ignore")
                if isinstance(item, bytes)
                else str(item)
                for item in languages
            ).lower()

            is_english = (
                "english" in name
                or "en" in name
                or "en" in language_text
            )
            score = 10 if is_english else 0

            if any(
                word in name
                for word in ("david", "mark", "guy", "male")
            ):
                score += 3

            if any(
                word in name
                for word in ("zira", "female", "samantha")
            ):
                score -= 1

            ranked.append((score, voice))

        return max(ranked, key=lambda pair: pair[0])[1] if ranked else None

    @staticmethod
    def _robotic_delivery(text: str) -> str:
        """Add pauses for a friendlier, more deliberate robot cadence."""
        text = re.sub(r"\s+", " ", str(text)).strip()
        text = re.sub(r"([.!?])\s+", r"\1 ... ", text)
        text = re.sub(r",\s+", ", ... ", text)
        return text

    def close(self) -> None:
        """Stop microphone capture and background audio workers."""
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

        try:
            self._speech_queue.put_nowait(None)
        except queue.Full:
            logger.warning("Could not queue TTS shutdown sentinel; worker will stop on close")
        logger.info("Voice controller shutdown requested")
