from __future__ import annotations

import math
import wave

from desk_robot.speech import SpeechSynthesizer


def test_robotic_audio_processing_preserves_wav_format_and_frame_count(tmp_path) -> None:
    source = tmp_path / "source.wav"
    destination = tmp_path / "processed.wav"
    sample_rate = 22050
    samples = bytearray()
    for index in range(sample_rate // 4):
        sample = int(7000 * math.sin(2 * math.pi * 440 * index / sample_rate))
        samples.extend(sample.to_bytes(2, "little", signed=True))
    with wave.open(str(source), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(samples)

    SpeechSynthesizer._robotise_wav(source, destination)

    with wave.open(str(source), "rb") as original, wave.open(str(destination), "rb") as processed:
        assert processed.getparams() == original.getparams()
        assert processed.getnframes() == original.getnframes()
        assert processed.readframes(processed.getnframes()) != original.readframes(original.getnframes())


def test_speech_volume_and_rate_are_clamped() -> None:
    speech = SpeechSynthesizer(volume=2.0, rate=999)

    assert speech.volume == 1.0
    assert speech.rate == 230
    speech.set_volume(-1.0)
    assert speech.volume == 0.0
