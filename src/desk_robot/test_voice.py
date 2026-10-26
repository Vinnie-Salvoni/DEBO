from __future__ import annotations

import sys
import types
from types import SimpleNamespace

from pathlib import Path

import pytest

from desk_robot.voice import VoiceController, VoiceError


class FakeEngine:
    def __init__(self) -> None:
        self.spoken: list[str] = []
        self.properties: dict[str, object] = {}
        self.stopped = False

    def getProperty(self, name: str):
        if name == "voices":
            return [SimpleNamespace(name="English David", id="en-david", languages=[b"en-US"])]
        return self.properties.get(name)

    def setProperty(self, name: str, value: object) -> None:
        self.properties[name] = value

    def say(self, text: str) -> None:
        self.spoken.append(text)

    def runAndWait(self) -> None:
        return None

    def stop(self) -> None:
        self.stopped = True


def test_robotic_delivery_adds_deliberate_pauses() -> None:
    assert VoiceController._robotic_delivery("Hello there. How are you, friend?") == (
        "Hello there. ... How are you, ... friend?"
    )


def test_normalise_cleans_transcript_spacing() -> None:
    assert VoiceController._normalise("  Hey   DEBO!  ") == "hey debo!"


def test_audio_callback_discards_audio_while_tts_is_active() -> None:
    voice = VoiceController()
    voice._speaking.set()
    voice._audio_callback(SimpleNamespace(tobytes=lambda: b"audio"), 1, None, None)
    assert voice._audio_queue.empty()


def test_audio_callback_discards_audio_until_model_is_ready() -> None:
    voice = VoiceController()
    voice._audio_callback(b"audio", 1, None, None)
    assert voice._audio_queue.empty()


def test_speech_worker_processes_multiple_utterances(monkeypatch) -> None:
    engine = FakeEngine()
    fake_module = types.SimpleNamespace(init=lambda: engine)
    monkeypatch.setitem(sys.modules, "pyttsx3", fake_module)

    voice = VoiceController()
    voice._speech_queue.put("First response.")
    voice._speech_queue.put("Second response.")
    voice._speech_queue.put(None)

    voice._speech_loop()

    assert len(engine.spoken) == 2
    assert engine.spoken[0].startswith("First response.")
    assert engine.spoken[1].startswith("Second response.")
    assert engine.stopped


def test_speech_worker_reports_playback_error_and_continues(monkeypatch) -> None:
    engine = FakeEngine()
    attempts = 0

    def fake_init():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("audio backend unavailable")
        return engine

    events: list[tuple[str, str]] = []
    monkeypatch.setitem(sys.modules, "pyttsx3", types.SimpleNamespace(init=fake_init))

    voice = VoiceController()
    voice._event_callback = lambda kind, text: events.append((kind, text))
    voice._speech_queue.put("This first attempt fails.")
    voice._speech_queue.put("This second response succeeds.")
    voice._speech_queue.put(None)

    voice._speech_loop()

    assert any(kind == "tts_error" for kind, _ in events)
    assert len(engine.spoken) == 1
    assert "second response" in engine.spoken[0].lower()


def test_speaking_gate_discards_queued_microphone_audio() -> None:
    voice = VoiceController()
    voice._audio_queue.put(b"old audio")
    voice._speaking.set()
    voice._drain_audio_queue()
    assert voice._audio_queue.empty()

def test_transcription_failure_is_not_misreported_as_model_download() -> None:
    class BrokenModel:
        def transcribe(self, *_args, **_kwargs):
            raise RuntimeError("decoder failed")

    voice = VoiceController()
    voice._model = BrokenModel()

    with pytest.raises(VoiceError, match="transcription failed after the local model loaded"):
        voice._transcribe_file(Path("not-read-by-the-fake-model.wav"))
