"""Pure DEBO eye geometry and semantic expression library.

This module contains no Tkinter code so expression design can be tested and
reused by other renderers. The Cozmo reference informs emotional readability;
these normalized shapes are provisional DEBO geometry, not copied source art.
"""

from __future__ import annotations

from dataclasses import dataclass

def blend(foreground: str, background: str, amount: float) -> str:
    """Blend hex colours; amount 0 is background, 1 is foreground."""
    amount = max(0.0, min(1.0, amount))
    fg, bg = foreground.lstrip("#"), background.lstrip("#")
    channels = [
        round(int(bg[i:i + 2], 16) * (1 - amount) + int(fg[i:i + 2], 16) * amount)
        for i in (0, 2, 4)
    ]
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def interpolate_colour(start: str, end: str, amount: float) -> str:
    amount = max(0.0, min(1.0, amount))
    channels = []
    for index in (1, 3, 5):
        first = int(start[index:index + 2], 16)
        second = int(end[index:index + 2], 16)
        channels.append(round(first + (second - first) * amount))
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def smoothstep(amount: float) -> float:
    amount = max(0.0, min(1.0, amount))
    return amount * amount * (3.0 - 2.0 * amount)


@dataclass(frozen=True)
class EyeShape:
    """A pair of independent, morphable eye silhouettes.

    Curvature is split between the upper and lower lids: this matters because
    Cozmo's happy/glee eyes are lid shapes, not smile lines drawn over eyes.
    Values are normalised and deliberately asymmetric expressions are allowed.
    """

    width: float = 1.0
    height: float = 1.0
    upper_curve: float = 0.0
    lower_curve: float = 0.0
    slant: float = 0.0
    tilt: float = 0.0
    x: float = 0.0
    y: float = 0.0
    roundness: float = 0.30
    x_eye: float = 0.0


# Provisional DEBO silhouettes: the reference informs the emotional vocabulary,
# while these normalized parameters are tuned for DEBO and remain editable.
# Curves describe the filled eye itself, not decorative marks over it. A positive
# upper_curve lowers the centre of the upper lid; a negative one raises it.
EXPRESSION_PRESETS: dict[str, tuple[EyeShape, EyeShape]] = {
    "neutral": (EyeShape(), EyeShape()),
    "blink_high": (
        EyeShape(height=0.055, roundness=0.12),
        EyeShape(height=0.055, roundness=0.12),
    ),
    "happy": (
        EyeShape(width=0.88, height=0.48, upper_curve=-0.70, lower_curve=-0.42,
                 roundness=0.40, y=0.015),
        EyeShape(width=0.88, height=0.48, upper_curve=-0.70, lower_curve=-0.42,
                 roundness=0.40, y=0.015),
    ),
    "glee": (
        EyeShape(width=0.83, height=0.31, upper_curve=-0.82, lower_curve=-0.52,
                 roundness=0.43, y=0.035),
        EyeShape(width=0.83, height=0.31, upper_curve=-0.82, lower_curve=-0.52,
                 roundness=0.43, y=0.035),
    ),
    "blink_low": (
        EyeShape(height=0.035, roundness=0.10, y=0.08),
        EyeShape(height=0.035, roundness=0.10, y=0.08),
    ),
    "sad_down": (
        EyeShape(width=0.70, height=0.25, upper_curve=0.10, lower_curve=-0.04,
                 slant=0.10, roundness=0.24, y=0.34),
        EyeShape(width=0.70, height=0.25, upper_curve=0.10, lower_curve=-0.04,
                 slant=-0.10, roundness=0.24, y=0.34),
    ),
    "sad_up": (
        EyeShape(width=0.70, height=0.25, upper_curve=0.12, lower_curve=-0.02,
                 slant=-0.11, roundness=0.24, y=-0.19),
        EyeShape(width=0.70, height=0.25, upper_curve=0.12, lower_curve=-0.02,
                 slant=0.11, roundness=0.24, y=-0.19),
    ),
    "worried": (
        EyeShape(width=0.90, height=0.82, upper_curve=0.05, slant=0.08,
                 roundness=0.28, y=0.02),
        EyeShape(width=0.90, height=0.82, upper_curve=0.05, slant=-0.08,
                 roundness=0.28, y=0.02),
    ),
    "focused": (
        EyeShape(width=0.88, height=0.37, upper_curve=0.02, lower_curve=-0.01,
                 roundness=0.12, y=0.03),
        EyeShape(width=0.88, height=0.37, upper_curve=0.02, lower_curve=-0.01,
                 roundness=0.12, y=0.03),
    ),
    "annoyed": (
        EyeShape(width=0.78, height=0.30, upper_curve=0.02, slant=0.16,
                 roundness=0.16, y=0.02),
        EyeShape(width=0.78, height=0.30, upper_curve=0.02, slant=-0.16,
                 roundness=0.16, y=0.02),
    ),
    "surprised": (
        EyeShape(width=1.05, height=1.20, roundness=0.37),
        EyeShape(width=1.05, height=1.20, roundness=0.37),
    ),
    "skeptic": (
        EyeShape(width=0.90, height=0.40, upper_curve=0.02, roundness=0.16,
                 y=0.02),
        EyeShape(width=0.83, height=0.56, upper_curve=-0.02, roundness=0.23,
                 tilt=-0.025, y=-0.01),
    ),
    "frustrated": (
        EyeShape(width=0.74, height=0.22, upper_curve=0.03, lower_curve=-0.02,
                 roundness=0.15, y=0.08),
        EyeShape(width=0.74, height=0.22, upper_curve=0.03, lower_curve=-0.02,
                 roundness=0.15, y=0.08),
    ),
    "unimpressed": (
        EyeShape(width=0.76, height=0.19, upper_curve=0.00, lower_curve=0.00,
                 roundness=0.12, y=0.08),
        EyeShape(width=0.76, height=0.19, upper_curve=0.00, lower_curve=0.00,
                 roundness=0.12, y=0.08),
    ),
    "sleepy": (
        EyeShape(width=0.52, height=0.24, upper_curve=0.02, lower_curve=0.03,
                 slant=-0.08, roundness=0.18, y=0.07),
        EyeShape(width=0.52, height=0.24, upper_curve=0.02, lower_curve=0.03,
                 slant=0.08, roundness=0.18, y=0.07),
    ),
    "suspicious": (
        EyeShape(width=0.77, height=0.25, upper_curve=0.01, lower_curve=0.00,
                 slant=-0.03, roundness=0.13, y=0.03),
        EyeShape(width=0.77, height=0.25, upper_curve=0.01, lower_curve=0.00,
                 slant=0.03, roundness=0.13, y=0.03),
    ),
    "squint": (
        EyeShape(width=0.82, height=0.18, upper_curve=0.00, lower_curve=0.00,
                 roundness=0.12, y=0.07),
        EyeShape(width=0.82, height=0.18, upper_curve=0.00, lower_curve=0.00,
                 roundness=0.12, y=0.07),
    ),
    "angry": (
        EyeShape(width=0.82, height=0.40, upper_curve=0.00, lower_curve=0.00,
                 slant=-0.24, roundness=0.12, y=0.02),
        EyeShape(width=0.82, height=0.40, upper_curve=0.00, lower_curve=0.00,
                 slant=0.24, roundness=0.12, y=0.02),
    ),
    "furious": (
        EyeShape(width=0.76, height=0.43, upper_curve=0.00, lower_curve=0.00,
                 slant=-0.34, roundness=0.08, y=0.015),
        EyeShape(width=0.76, height=0.43, upper_curve=0.00, lower_curve=0.00,
                 slant=0.34, roundness=0.08, y=0.015),
    ),
    "scared": (
        EyeShape(width=0.72, height=0.92, upper_curve=0.04, roundness=0.23,
                 y=-0.05),
        EyeShape(width=0.72, height=0.92, upper_curve=0.04, roundness=0.23,
                 y=-0.05),
    ),
    "awe": (
        EyeShape(width=0.94, height=1.12, roundness=0.44),
        EyeShape(width=0.94, height=1.12, roundness=0.44),
    ),
    "thinking": (
        EyeShape(width=0.84, height=0.46, upper_curve=0.02, roundness=0.18,
                 tilt=-0.025, y=0.035),
        EyeShape(width=0.84, height=0.46, upper_curve=0.02, roundness=0.18,
                 tilt=0.025, y=0.035),
    ),
    "listening": (
        EyeShape(width=1.02, height=1.03, roundness=0.32),
        EyeShape(width=1.02, height=1.03, roundness=0.32),
    ),
    "error": (
        EyeShape(width=0.90, height=0.90, x_eye=1.0, roundness=0.08),
        EyeShape(width=0.90, height=0.90, x_eye=1.0, roundness=0.08),
    ),
}

# Map application states onto DEBO's expression library. Public aliases are
# retained for compatibility with existing settings commands and tests.
EXPRESSION_ALIASES = {
    "idle": "neutral", "speaking": "neutral", "happy": "happy",
    "glee": "glee", "success": "glee", "pleased": "happy",
    "curious": "awe", "interested": "awe", "waking": "surprised",
    "confused": "skeptic", "sleeping": "sleepy", "weather": "focused",
    "news": "focused", "sad": "sad_down", "skeptical": "skeptic",
    "focused/determined": "focused", "annoyed": "annoyed",
    "frustrated/bored": "frustrated", "unimpressed": "unimpressed",
    "sleepy eyes": "sleepy", "blink (high)": "blink_high",
    "blink (low)": "blink_low", "sad (looking down)": "sad_down",
    "sad (looking up to user)": "sad_up", "worried": "worried",
    "surprised": "surprised", "suspicious": "suspicious", "squint": "squint",
    "angry": "angry", "furious": "furious", "scared": "scared", "awe": "awe",
}
# Keep the existing state-based animation API intact.
EXPRESSIONS = {
    state: EXPRESSION_PRESETS[EXPRESSION_ALIASES.get(state, state)]
    for state in ("idle", "listening", "thinking", "happy", "speaking", "error")
}


def morph_shape(start: EyeShape, end: EyeShape, amount: float) -> EyeShape:
    """Ease between every geometric parameter for a smooth silhouette morph."""
    t = smoothstep(amount)
    return EyeShape(**{
        field: getattr(start, field) + (getattr(end, field) - getattr(start, field)) * t
        for field in EyeShape.__dataclass_fields__
    })

