from __future__ import annotations

from desk_robot.face import (
    EXPRESSION_ALIASES,
    EXPRESSION_PRESETS,
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
