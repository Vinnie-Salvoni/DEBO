from __future__ import annotations

from desk_robot.face import (
    DEFAULT_SETTINGS,
    EXPRESSION_ALIASES,
    EXPRESSION_PRESETS,
    DeboFace,
    EyeShape,
    morph_shape,
    smoothstep,
)


def test_expression_library_covers_personality_and_information_states() -> None:
    assert EXPRESSION_ALIASES["curious"] == "awe"
    assert EXPRESSION_ALIASES["confused"] == "skeptic"
    assert EXPRESSION_ALIASES["sleeping"] == "sleepy"
    assert EXPRESSION_ALIASES["weather"] == "focused"
    assert EXPRESSION_ALIASES["news"] == "focused"
    assert {"neutral", "listening", "thinking", "happy", "error", "sleepy"} <= set(EXPRESSION_PRESETS)


def test_smoothstep_has_stable_endpoints() -> None:
    assert smoothstep(0.0) == 0.0
    assert smoothstep(1.0) == 1.0


def test_eye_geometry_morph_interpolates_shape_parameters() -> None:
    start = EyeShape(width=1.0, height=1.0, x=0.0)
    end = EyeShape(width=0.5, height=0.2, x=10.0)

    middle = morph_shape(start, end, 0.5)

    assert middle.width == 0.75
    assert middle.height == 0.6
    assert middle.x == 5.0


def test_unknown_expression_names_do_not_require_a_new_renderer() -> None:
    assert "weather" in EXPRESSION_ALIASES
    assert "news" in EXPRESSION_ALIASES



def test_voice_commands_change_eye_colour_and_animation_speed(monkeypatch) -> None:
    monkeypatch.setattr("desk_robot.face.save_settings", lambda _settings: None)
    face = object.__new__(DeboFace)
    face.settings = DEFAULT_SETTINGS.copy()
    face.show_expression = lambda *_args, **_kwargs: True

    colour_response = face._handle_settings_command("change my eye colour to blue")
    assert colour_response == "Eye colour changed to blue."
    assert face.settings["eye_color"] == "#329BFF"

    speed_response = face._handle_settings_command("animation speed fast")
    assert speed_response == "Animation speed set to 2.0."
    assert face.settings["animation_speed"] == 2.0


def test_voice_commands_update_sound_and_speech_preferences(monkeypatch) -> None:
    monkeypatch.setattr("desk_robot.face.save_settings", lambda _settings: None)

    class FakeAudio:
        def __init__(self):
            self.enabled = None
            self.volume = None
            self.rate = None

        def set_enabled(self, value):
            self.enabled = value

        def set_volume(self, value):
            self.volume = value

        def set_rate(self, value):
            self.rate = value

    face = object.__new__(DeboFace)
    face.settings = DEFAULT_SETTINGS.copy()
    face.sound = FakeAudio()
    face.speech = FakeAudio()

    assert face._handle_settings_command("turn sound off") == "Sound effects are off."
    assert face.sound.enabled is False
    assert face._handle_settings_command("speech volume 70") == "Speech volume set to 70 percent."
    assert face.speech.volume == 0.7
    assert face._handle_settings_command("speech rate 170") == "Speech rate set to 170 words per minute."
    assert face.speech.rate == 170
