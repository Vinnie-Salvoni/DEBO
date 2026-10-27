from __future__ import annotations

from pathlib import Path

import pytest

from desk_robot.voice import VoiceController, VoiceError


def test_normalise_cleans_transcript_spacing() -> None:
    assert VoiceController._normalise("  Hey   DEBO!  ") == "hey debo!"


def test_audio_callback_discards_audio_until_model_is_ready() -> None:
    voice = VoiceController()
    voice._audio_callback(b"audio", 1, None, None)
    assert voice._audio_queue.empty()


def test_transcription_failure_is_not_misreported_as_model_download() -> None:
    class BrokenModel:
        def transcribe(self, *_args, **_kwargs):
            raise RuntimeError("decoder failed")

    voice = VoiceController()
    voice._model = BrokenModel()

    with pytest.raises(VoiceError, match="transcription failed after the local model loaded"):
        voice._transcribe_file(Path("not-read-by-the-fake-model.wav"))



@pytest.mark.parametrize(
    "transcript",
    [
        "Hey DEBO!",
        "HEY DEEBO!",
        "Hey Devo, tell me a joke.",
        "Okay, thebo, how are you?",
        "Hello, DEB0.",
    ],
)
def test_find_wake_phrase_accepts_common_transcription_variants(transcript: str) -> None:
    assert VoiceController._find_wake_phrase(transcript) is not None


@pytest.mark.parametrize(
    "transcript",
    [
        "I was talking to Debo yesterday.",
        "Hey, that was a good idea.",
        "The weather is lovely today.",
        "I said hello to the robot.",
    ],
)
def test_find_wake_phrase_rejects_unrelated_phrases(transcript: str) -> None:
    assert VoiceController._find_wake_phrase(transcript) is None


def test_wake_match_returns_offsets_for_combined_command() -> None:
    transcript = "Hey Devo, tell me a joke!"
    match = VoiceController._find_wake_phrase(transcript)
    assert match is not None
    assert transcript[match[0]:match[1]].lower() == "hey devo"
    assert transcript[match[1]:].strip(" ,.!?:;-") == "tell me a joke"


def test_combined_wake_and_command_emits_both_events(monkeypatch) -> None:
    voice = VoiceController()
    voice._model_ready.set()
    voice._transcribe_file = lambda _path: "Hey Devo, how are you?"  # type: ignore[method-assign]
    events: list[tuple[str, str]] = []
    voice._event_callback = lambda kind, text: events.append((kind, text))

    # One short PCM sample is sufficient because transcription is mocked.
    voice._process_utterance(b"\\x00\\x00" * 160)

    assert [kind for kind, _text in events] == ["wake", "transcript"]
    assert events[1][1] == "how are you"
    assert voice._wake_until == 0.0



def test_voice_input_remains_separate_from_speech_output() -> None:
    package_dir = Path(__file__).resolve().parents[2] / "src" / "desk_robot"
    source = (package_dir / "voice.py").read_text(encoding="utf-8")
    speech_source = (package_dir / "speech.py").read_text(encoding="utf-8")
    sound_source = (package_dir / "sound.py").read_text(encoding="utf-8")

    assert "pyttsx3" not in source
    assert "def pause(" in source
    assert "def resume(" in source
    assert "class SpeechSynthesizer" in speech_source
    assert "pyttsx3" in speech_source
    assert "def speak(" not in sound_source



def test_microphone_pause_suppresses_playback_audio_and_resume_restores_input() -> None:
    class AudioFrame:
        def tobytes(self) -> bytes:
            return b"\\x01\\x00" * 8

    voice = VoiceController()
    voice._model_ready.set()
    voice.pause()
    voice._audio_callback(AudioFrame(), 8, None, None)
    assert voice._audio_queue.empty()

    voice.resume()
    voice._audio_callback(AudioFrame(), 8, None, None)
    assert voice._audio_queue.get_nowait() == b"\\x01\\x00" * 8


def test_follow_up_utterance_is_accepted_without_wake_phrase() -> None:
    import time
    voice = VoiceController()
    voice._model_ready.set()
    voice._followup_until = time.monotonic() + 10
    voice._transcribe_file = lambda _path: "Manchester"  # type: ignore[method-assign]
    events: list[tuple[str, str]] = []
    voice._event_callback = lambda kind, text: events.append((kind, text))
    voice._process_utterance(b"\\x00\\x00" * 160)
    assert events == [("transcript", "Manchester")]
    assert voice._followup_until == 0.0


def test_follow_up_window_is_bounded() -> None:
    voice = VoiceController()
    voice.listen_for_follow_up(500)
    assert voice._followup_until > 0
    assert voice._wake_until == 0.0
