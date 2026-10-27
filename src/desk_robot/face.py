"""DEBO's expressive animated desktop face.

Launch from the project root with ``uv run python -m desk_robot.face``.
Tkinter is used for rendering; all Canvas operations remain on the UI thread.
"""

from __future__ import annotations

import json
import math
import queue
import random
import logging
import tkinter as tk
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from tkinter import colorchooser, ttk

from desk_robot.robot import DeskRobot
from desk_robot.sound import SoundManager
from desk_robot.voice import VoiceController, VoiceError

SETTINGS_PATH = Path.home() / ".debo_face_settings.json"
BG = "#05080D"
PANEL = "#0C131D"
TEXT = "#E8F5FF"
MUTED = "#8298AA"
DEFAULT_SETTINGS = {
    "eye_color": "#00D9D0",
    "accent_color": "#4D9DFF",
    "glow": 58,
    "animation_speed": 1.0,
    "automatic_accents": True,
    "sound_enabled": True,
    "sound_volume": 55,
}
COLOUR_TRANSITION_SECONDS = 0.75
GAZE_MIN_INTERVAL = 2.2
GAZE_MAX_INTERVAL = 4.0
FRAME_MS = 16


def load_settings() -> dict:
    """Load saved settings, validating values and falling back safely."""
    settings = DEFAULT_SETTINGS.copy()
    try:
        saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        if isinstance(saved, dict):
            settings.update({key: value for key, value in saved.items() if key in settings})
    except (OSError, json.JSONDecodeError):
        pass
    try:
        settings["glow"] = max(0, min(100, int(settings["glow"])))
        settings["animation_speed"] = max(0.5, min(2.0, float(settings["animation_speed"])))
        settings["sound_volume"] = max(0, min(100, int(settings["sound_volume"])))
        for key in ("automatic_accents", "sound_enabled"):
            settings[key] = bool(settings[key])
        for key in ("eye_color", "accent_color"):
            value = str(settings[key])
            if len(value) != 7 or not value.startswith("#"):
                raise ValueError(f"Invalid colour: {value}")
            int(value[1:], 16)
            settings[key] = value
    except (TypeError, ValueError, OverflowError):
        return DEFAULT_SETTINGS.copy()
    return settings


def save_settings(settings: dict) -> None:
    try:
        SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except OSError:
        pass


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


# These silhouettes are transcribed from the project's Cozmo reference sheet.
# The values describe the *filled eye itself*, not decorative marks over it.
# A positive upper_curve lowers the centre of the upper lid; a negative one
# raises it. lower_curve does the equivalent for the lower lid.
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

# Internal application states map onto the closest sheet expression.  All 21
# reference-sheet poses remain available through show_expression().
EXPRESSION_ALIASES = {
    "idle": "neutral", "speaking": "neutral", "happy": "happy",
    "glee": "glee", "sad": "sad_down", "skeptical": "skeptic",
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


class DeboFace:
    """Tkinter UI with a responsive background worker and morphable eye geometry."""
    logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(threadName)s %(name)s: %(message)s",
        )
    def __init__(self) -> None:
        self.settings = load_settings()
        self.robot = DeskRobot()
        self.sound = SoundManager(
            enabled=self.settings["sound_enabled"],
            volume=self.settings["sound_volume"] / 100,
        )
        self.voice = VoiceController()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="debo-brain")
        self.results: queue.Queue[tuple[str, str, int]] = queue.Queue()

        self.state = "idle"
        self.time = 0.0
        self.busy = False
        self.closed = False
        self.response = "Hey! I'm DEBO. What's on your mind?"
        self.idle_callback: str | None = None
        self._request_id = 0
        self._expression_started = 0.0
        self._expression_from = EXPRESSIONS["idle"]
        self._expression_to = EXPRESSIONS["idle"]
        self._expression_duration = 0.32
        self._happy_until = 0.0
        self._thinking_bob_started: float | None = None
        self._thinking_bob_duration = 0.30
        self._thinking_bobs = 0

        self.blink_started: float | None = None
        self.blink_duration = 0.2
        self.blink_amount = 0.0
        self.next_blink = random.uniform(1.8, 4.0)

        self.look_x = self.look_y = 0.0
        self.target_x = self.target_y = 0.0
        self.next_gaze_change = random.uniform(0.5, 1.2)
        self.gaze_pause_until = 0.0

        self.display_eye_color = self.settings["eye_color"]
        self.display_accent_color = self.settings["accent_color"]
        self._colour_target_eye = self.display_eye_color
        self._colour_target_accent = self.display_accent_color
        self._colour_from_eye = self.display_eye_color
        self._colour_from_accent = self.display_accent_color
        self._colour_started = 0.0
        self._accent_started = 0.0

        self.root = tk.Tk()
        self.root.title("DEBO | Desktop Companion")
        self.root.geometry("900x760")
        self.root.minsize(620, 560)
        self.root.configure(bg=BG)
        self._build_interface()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.status.configure(text="STARTING UP…")
        self.sound.play("startup")
        self.animate()
        try:
            self.voice.start_wake_listening(self._on_voice_event)
            self.status.configure(text="LOADING VOICE MODEL…")
        except VoiceError as error:
            self.response = str(error)
            self.response_label.configure(text=self.response)
            self.status.configure(text="VOICE INPUT UNAVAILABLE")
        self.root.mainloop()

    def _build_interface(self) -> None:
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=24, pady=(18, 8))
        tk.Label(header, text="D E B O", bg=BG, fg=TEXT,
                 font=("Segoe UI", 13, "bold")).pack(side="left")
        self.status = tk.Label(header, text="READY WHEN YOU ARE", bg=BG, fg=MUTED,
                               font=("Segoe UI", 8, "bold"))
        self.status.pack(side="right")

        self.canvas = tk.Canvas(self.root, bg=BG, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True, padx=12, pady=4)

        self.info_panel = tk.Frame(self.root, bg="#0A111B", padx=18, pady=12,
                                   highlightthickness=1, highlightbackground="#1A2C3C")
        self.info_title = tk.Label(self.info_panel, text="", bg="#0A111B", fg="#65DCD4",
                                   font=("Segoe UI", 9, "bold"), anchor="w")
        self.info_title.pack(fill="x")
        self.info_main = tk.Label(self.info_panel, text="", bg="#0A111B", fg=TEXT,
                                  font=("Segoe UI", 17, "bold"), anchor="w",
                                  justify="left", wraplength=800)
        self.info_main.pack(fill="x", pady=(4, 2))
        self.info_meta = tk.Label(self.info_panel, text="", bg="#0A111B", fg=MUTED,
                                  font=("Segoe UI", 9), anchor="w", justify="left")
        self.info_meta.pack(fill="x", pady=(0, 8))
        self.ticker_canvas = tk.Canvas(self.info_panel, height=30, bg="#101C29",
                                       highlightthickness=0, bd=0)
        self.ticker_canvas.pack(fill="x")
        self._ticker_text = ""
        self._ticker_item = self.ticker_canvas.create_text(
            0, 15, text="", anchor="w", fill="#C8E8F4",
            font=("Segoe UI", 10, "bold"),
        )
        self._ticker_x = 0.0
        self._ticker_speed = 1.25
        self.next_story_button = tk.Button(
            self.info_panel, text="NEXT STORY  →", command=lambda: self.submit_message("next story"),
            bg="#12313A", fg="#D9FFFF", activebackground="#1B4C58",
            activeforeground="#FFFFFF", relief="flat", padx=12, pady=6,
            font=("Segoe UI", 9, "bold"), cursor="hand2",
        )
        self.info_panel.pack(fill="x", padx=24, pady=(4, 8))
        self.info_panel.pack_forget()
        response_panel = tk.Frame(self.root, bg=PANEL, padx=18, pady=14)
        response_panel.pack(fill="x", padx=24, pady=(4, 14))
        self.response_label = tk.Label(
            response_panel, text=self.response, bg=PANEL, fg="#C9D9E5",
            font=("Segoe UI", 11), wraplength=720, justify="center",
        )
        self.response_label.pack(fill="x")

        controls = tk.Frame(self.root, bg=BG)
        controls.pack(fill="x", padx=24, pady=(0, 18))
        self.listen_hint = tk.Label(
            controls,
            text="SAY “HEY DEBO” TO TALK",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 9, "bold"),
        )
        self.listen_hint.pack(side="left", fill="x", expand=True, anchor="w")
        tk.Button(
            controls, text="⚙", command=self.open_settings, font=("Segoe UI", 13),
            bg="#111923", fg="#D4E5F2", activebackground="#263444",
            activeforeground="#FFFFFF", relief="flat", bd=0, padx=13, pady=7,
            cursor="hand2",
        ).pack(side="right")

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self._cancel_idle_callback()
        save_settings(self.settings)
        try:
            self.sound.close()
        except (AttributeError, RuntimeError):
            pass
        self.voice.close()
        self.executor.shutdown(wait=False, cancel_futures=True)
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _set_expression(self, state: str, duration: float = 0.32) -> None:
        """Begin a single cancellable morph from the currently displayed geometry."""
        target = EXPRESSIONS.get(state, EXPRESSIONS["idle"])
        self._set_expression_shapes(target, duration)

    def show_expression(self, name: str, duration: float = 0.28) -> bool:
        """Morph to any expression from the project's Cozmo reference sheet.

        Names accept either preset keys (``sad_down``) or human-readable labels
        (``Sad (looking down)``). Returns False for unknown names.
        """
        key = name.strip().lower().replace("-", "_")
        key = EXPRESSION_ALIASES.get(key, key)
        if key not in EXPRESSION_PRESETS:
            return False
        self._set_expression_shapes(EXPRESSION_PRESETS[key], duration)
        return True

    def _set_expression_shapes(
        self, target: tuple[EyeShape, EyeShape], duration: float = 0.28
    ) -> None:
        self._expression_from = self._current_shapes()
        self._expression_to = target
        self._expression_started = self.time
        self._expression_duration = max(0.01, duration / self._speed())

    def set_state(self, state: str) -> None:
        if state == self.state:
            return
        self._set_expression(state, 0.34 if state in {"happy", "thinking"} else 0.28)
        self.state = state
        if state == "thinking":
            self._thinking_bob_started = self.time
            self._thinking_bobs = 0
            self.target_x = self.target_y = 0.0
            self.gaze_pause_until = float("inf")
        elif self._thinking_bob_started is not None:
            self._thinking_bob_started = None
            self._thinking_bobs = 0
            self.gaze_pause_until = self.time + 0.45
        labels = {
            "idle": "STANDBY",
            "listening": "LISTENING TO YOU",
            "thinking": "PROCESSING",
            "speaking": "SPEAKING",
            "happy": "RESPONSE READY",
            "error": "RECOVERABLE ERROR",
        }
        self.status.configure(text=labels.get(state, "READY WHEN YOU ARE"))
        self.status.configure(fg=self.current_accent())

    def _on_voice_event(self, event: str, text: str) -> None:
        """Queue voice events for the Tk thread; the audio worker never touches widgets."""
        self.results.put((event, text, -1))

    def submit_message(self, message: str) -> None:
        """Process a recognised voice transcript without any text-entry UI."""
        message = str(message).strip()
        if not message or self.busy or self.closed:
            return
        self._request_id += 1
        request_id = self._request_id
        self.busy = True
        self.response = ""
        self.response_label.configure(text="Let me think about that…")
        self._cancel_idle_callback()
        self._happy_until = 0.0
        self.set_state("thinking")
        self.sound.play("send")
        self.root.after(
            180,
            lambda: self.sound.play("thinking")
            if not self.closed and self.busy and request_id == self._request_id
            else None,
        )
        lowered = message.lower()
        if any(word in lowered for word in ("weather", "temperature", "forecast")):
            self.show_information_loading("weather")
        elif any(word in lowered for word in ("news", "headlines", "latest stories", "what's happening", "what is happening", "next story", "another story", "next headline")):
            self.show_information_loading("news")
        else:
            self.hide_information()
        future = self.executor.submit(self.robot.respond, message)
        future.add_done_callback(
            lambda result, rid=request_id: self._collect_result(result, rid)
        )

    def _collect_result(self, future: Future[str], request_id: int) -> None:
        """Worker callback: queue results only; never call Tk from this thread."""
        try:
            self.results.put(("ok", str(future.result()), request_id))
        except Exception as error:  # noqa: BLE001
            self.results.put(("error", str(error), request_id))

    def _poll_results(self) -> None:
        while True:
            try:
                kind, result, request_id = self.results.get_nowait()
            except queue.Empty:
                return
            if self.closed:
                continue

            if kind == "model_loading":
                if not self.busy:
                    self.status.configure(text="LOADING SPEECH MODEL…", fg=self.current_accent())
                    self.response_label.configure(text="Preparing my local ears…")
                continue

            if kind == "model_ready":
                if not self.busy:
                    self.status.configure(text="WAITING FOR HEY DEBO", fg=self.current_accent())
                    self.response_label.configure(text="I'm ready. Say “Hey DEBO” when you need me.")
                    if self.state == "error":
                        self.set_state("idle")
                    self.status.configure(text="WAITING FOR HEY DEBO", fg=self.current_accent())
                continue

            if kind == "model_error":
                self.response = result
                self.response_label.configure(text=f"Speech model unavailable: {result}")
                self.set_state("error")
                continue

            if kind == "transcription_error":
                self.response = result
                self.response_label.configure(text=result)
                if not self.busy:
                    self.set_state("error")
                    self.idle_callback = self.root.after(3500, self.return_to_idle)
                continue

            if kind == "wake":
                self._cancel_idle_callback()
                if not self.busy:
                    # Show the listening pose immediately when the wake phrase
                    # is confirmed; do not spend its short visible window in a
                    # separate surprised animation.
                    self.set_state("listening")
                    self.show_expression("listening", 0.22)
                    self.response_label.configure(text="I'm listening — go ahead!")
                    self.sound.play("curious")
                continue

            if kind == "standby":
                if not self.busy and self.state == "listening":
                    self.return_to_idle()
                continue

            if kind == "voice_error":
                self.response = result
                self.response_label.configure(text=result)
                if not self.busy:
                    self.set_state("error")
                    self.idle_callback = self.root.after(3500, self.return_to_idle)
                continue

            if request_id != -1 and request_id != self._request_id:
                continue

            if kind == "transcript":
                transcript = result.strip()
                if not transcript:
                    if not self.busy:
                        self.set_state("idle")
                    continue
                self.busy = False
                if self.state == "listening":
                    # The wake and command events can arrive in the same GUI
                    # poll. Briefly hold the listening pose so it is actually
                    # rendered before the response/thinking animation replaces it.
                    self.root.after(
                        450,
                        lambda text=transcript: self.submit_message(text)
                        if not self.closed else None,
                    )
                else:
                    self.submit_message(transcript)
                continue

            self.response = result
            self.response_label.configure(text=result)
            self.busy = False
            if kind == "ok":
                self._present_latest_information()
            elif getattr(self.robot, "last_intent", "") in {"weather", "news", "next_news"}:
                self.info_panel.pack(fill="x", padx=24, pady=(4, 8))
                self.info_title.configure(text=f"{self.robot.last_intent.upper()}  /  UNAVAILABLE")
                self.info_main.configure(text="I couldn't reach the information service. Please try again.")
                self.info_meta.configure(text="The rest of DEBO is still ready.")
                self._set_ticker("LIVE INFORMATION UNAVAILABLE")
            self._cancel_idle_callback()
            if kind == "error":
                self._happy_until = 0.0
                self.set_state("error")
                self.sound.play("error")
                self.idle_callback = self.root.after(2500, self.return_to_idle)
            else:
                self.set_state("happy")
                self._happy_until = self.time + 1.0 / self._speed()
                self.sound.play("success")
                # The callback is a fallback; the animation clock owns the happy hold.
                self.idle_callback = self.root.after(5200, self.return_to_idle)


    def hide_information(self) -> None:
        self.info_panel.pack_forget()
        self.next_story_button.pack_forget()
        self.ticker_canvas.itemconfigure(self._ticker_item, text="")
        self._ticker_text = ""

    def show_information_loading(self, kind: str) -> None:
        self.info_panel.pack(fill="x", padx=24, pady=(4, 8))
        self.next_story_button.pack_forget()
        self.info_title.configure(text=f"{kind.upper()}  /  CONNECTING")
        self.info_main.configure(text="One moment — I'm checking the latest information.")
        self.info_meta.configure(text="Live data · Network requests run in the background")
        self._set_ticker(f"DEBO IS FETCHING {kind.upper()}…")

    def _set_ticker(self, text: str) -> None:
        self._ticker_text = "     •     ".join(part.strip() for part in str(text).splitlines() if part.strip())
        self._ticker_x = float(self.ticker_canvas.winfo_width() or 700)
        self.ticker_canvas.itemconfigure(self._ticker_item, text=self._ticker_text)
        self.ticker_canvas.coords(self._ticker_item, self._ticker_x, 15)

    def _animate_ticker(self) -> None:
        if not self._ticker_text or not self.info_panel.winfo_ismapped():
            return
        self._ticker_x -= self._ticker_speed
        bounds = self.ticker_canvas.bbox(self._ticker_item)
        if bounds and bounds[2] < 0:
            self._ticker_x = float(self.ticker_canvas.winfo_width() or 700)
        self.ticker_canvas.coords(self._ticker_item, self._ticker_x, 15)

    def present_weather(self, report) -> None:
        condition = str(report.condition or "Conditions unavailable")
        lowered = condition.lower()
        symbol = "☀" if any(word in lowered for word in ("clear", "sun")) else (
            "❄" if "snow" in lowered or "freez" in lowered else (
                "ϟ" if "thunder" in lowered else ("☂" if "rain" in lowered or "drizzle" in lowered else "☁")
            )
        )
        self.info_panel.pack(fill="x", padx=24, pady=(4, 8))
        self.info_title.configure(text=f"WEATHER  /  {str(report.location).upper()}")
        self.info_main.configure(text=f"{symbol}   {report.temperature_c:.1f}°C   ·   {condition}")
        observed = report.observed_at.strftime("%H:%M") if report.observed_at else "time unavailable"
        fetched = report.fetched_at.strftime("%H:%M UTC") if report.fetched_at else "time unavailable"
        high_low = ""
        if report.daily_high_c is not None and report.daily_low_c is not None:
            high_low = f"  ·  Today H {report.daily_high_c:.0f}° / L {report.daily_low_c:.0f}°C"
        forecast = f"  ·  Outlook {report.forecast_condition}" if report.forecast_condition else ""
        self.info_meta.configure(text=f"{report.provider}  ·  Observed {observed}  ·  Retrieved {fetched}{high_low}{forecast}")
        self.next_story_button.pack_forget()
        ticker = f"CURRENT CONDITIONS  •  {report.location}  •  {condition}  •  {report.temperature_c:.1f}°C"
        if high_low:
            ticker += f"  •  {high_low.strip(' ·')}"
        if forecast:
            ticker += f"  •  {forecast.strip(' ·')}"
        self._set_ticker(ticker)

    def present_news(self, report) -> None:
        articles = tuple(report.articles or ())
        self.info_panel.pack(fill="x", padx=24, pady=(4, 8))
        if not articles:
            self.info_title.configure(text="NEWS  /  NO STORIES")
            self.info_main.configure(text="I couldn't find any readable headlines just now.")
            self.info_meta.configure(text=f"{report.provider} · Try again in a moment")
            self._set_ticker("NO HEADLINES AVAILABLE")
            return
        index = int(getattr(self.robot, "last_news_index", 0)) % len(articles)
        first = articles[index]
        self.info_title.configure(text=f"NEWS  /  TOP STORY  ·  {index + 1} OF {len(articles)}")
        self.info_main.configure(text=first.title)
        self.next_story_button.pack(anchor="e", pady=(8, 0))
        published = first.published_at.strftime("%d %b · %H:%M UTC") if first.published_at else "publication time unavailable"
        self.info_meta.configure(text=f"{first.source or report.provider}  ·  {published}  ·  Retrieved {report.fetched_at.strftime('%H:%M UTC')}")
        self._set_ticker("     •     ".join(f"{index}. {article.title} — {article.source}" for index, article in enumerate(articles, start=1)))

    def _present_latest_information(self) -> None:
        weather = getattr(self.robot, "last_weather_report", None)
        news = getattr(self.robot, "last_news_report", None)
        if weather is not None:
            self.present_weather(weather)
        elif news is not None:
            self.present_news(news)

    def _cancel_idle_callback(self) -> None:
        if self.idle_callback is not None:
            try:
                self.root.after_cancel(self.idle_callback)
            except tk.TclError:
                pass
            self.idle_callback = None

    def return_to_idle(self) -> None:
        self.idle_callback = None
        if not self.busy and self.state in {"speaking", "error", "happy", "listening"}:
            self.set_state("idle")

    def current_accent(self) -> str:
        if self.settings["automatic_accents"]:
            colours = {
                "thinking": "#B49AFF", "listening": "#65B8FF", "error": "#FF7D8A",
                "happy": "#FFD166", "speaking": "#68E5CE",
            }
            return colours.get(self.state, str(self.settings["accent_color"]))
        return str(self.settings["accent_color"])

    def _update_colours(self) -> None:
        target_eye = str(self.settings["eye_color"])
        target_accent = self.current_accent()
        if target_eye != self._colour_target_eye:
            self._colour_from_eye = self.display_eye_color
            self._colour_target_eye = target_eye
            self._colour_started = self.time
        if target_accent != self._colour_target_accent:
            self._colour_from_accent = self.display_accent_color
            self._colour_target_accent = target_accent
            self._accent_started = self.time
        duration = COLOUR_TRANSITION_SECONDS
        eye_progress = smoothstep((self.time - self._colour_started) / duration)
        accent_progress = smoothstep((self.time - self._accent_started) / duration)
        self.display_eye_color = interpolate_colour(
            self._colour_from_eye, self._colour_target_eye, eye_progress
        )
        self.display_accent_color = interpolate_colour(
            self._colour_from_accent, self._colour_target_accent, accent_progress
        )

    def _speed(self) -> float:
        try:
            return max(0.5, min(2.0, float(self.settings["animation_speed"])))
        except (TypeError, ValueError):
            return 1.0

    def _current_shapes(self) -> tuple[EyeShape, EyeShape]:
        amount = (self.time - self._expression_started) / self._expression_duration
        if amount >= 1.0:
            self._expression_from = self._expression_to
            return self._expression_to
        return (
            morph_shape(self._expression_from[0], self._expression_to[0], amount),
            morph_shape(self._expression_from[1], self._expression_to[1], amount),
        )

    def _update_blink(self, speed: float) -> None:
        # No random blink can interrupt the held thinking pose or the response reveal.
        if self.state not in {"thinking", "happy", "error"}:
            if self.blink_started is None and self.time >= self.next_blink:
                self.blink_started = self.time
                self.blink_duration = 0.34 if random.random() < 0.18 else random.uniform(0.16, 0.24)
        if self.blink_started is None:
            return
        progress = (self.time - self.blink_started) / max(0.08, self.blink_duration / speed)
        if progress >= 1:
            self.blink_started = None
            self.blink_amount = 0.0
            self.next_blink = self.time + random.uniform(1.8, 4.2) / speed
        else:
            self.blink_amount = math.sin(progress * math.pi) ** 2

    def _update_gaze(self, speed: float) -> None:
        if self.state == "thinking":
            # Gaze is frozen while thinking so the two intentional bobs are the only motion.
            self.target_x = self.target_y = 0.0
        elif self.time >= self.next_gaze_change and self.time >= self.gaze_pause_until:
            self.next_gaze_change = self.time + random.uniform(
                GAZE_MIN_INTERVAL, GAZE_MAX_INTERVAL
            ) / speed
            if self.state in {"speaking", "happy"}:
                choices = [(-1, 0), (1, 0), (0, -0.3), (0, 0.3)]
            else:
                choices = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0),
                           (-1, 1), (0, 1), (1, 1), (0, 0)]
            gx, gy = random.choice(choices)
            self.target_x = gx * 10.0
            self.target_y = gy * 6.0
        smoothing = min(0.11, 0.065 * speed)
        self.look_x += (self.target_x - self.look_x) * smoothing
        self.look_y += (self.target_y - self.look_y) * smoothing

    @staticmethod
    def _eye_points(cx: float, cy: float, width: float, height: float,
                    shape: EyeShape, blink: float, side: int) -> list[float]:
        """Build a rounded, independently curved upper/lower-lid silhouette.

        A superellipse gives the characteristic near-rectangular Cozmo eye;
        the two lid curves and mirrored slant then change the actual contour
        for happy, sleepy, sad, suspicious and angry poses.
        """
        height *= max(0.035, 1.0 - blink * 0.965)
        width = max(1.0, width)
        height = max(1.0, height)
        points: list[float] = []
        count = 64
        exponent = 2.0 + (1.0 - max(0.05, min(0.8, shape.roundness))) * 2.0
        for index in range(count):
            angle = (2.0 * math.pi * index) / count
            cosine, sine = math.cos(angle), math.sin(angle)
            x_norm = math.copysign(abs(cosine) ** (2.0 / exponent), cosine)
            y_norm = math.copysign(abs(sine) ** (2.0 / exponent), sine)
            # In Tk coordinates negative y is above the eye.
            curve_weight = max(0.0, 1.0 - x_norm * x_norm)
            if y_norm < 0:
                y_norm += shape.upper_curve * curve_weight
            else:
                y_norm += shape.lower_curve * curve_weight
            # Mirror the slope so the inner/outer corners remain anatomically
            # consistent between the left and right eye.
            y_norm += shape.slant * x_norm * (-side) * 0.75
            px = x_norm * width / 2
            py = y_norm * height / 2
            angle_offset = shape.tilt
            rotated_x = px * math.cos(angle_offset) - py * math.sin(angle_offset)
            rotated_y = px * math.sin(angle_offset) + py * math.cos(angle_offset)
            points.extend((cx + rotated_x, cy + rotated_y))
        return points

    def _draw_eye(self, cx: float, cy: float, width: float, height: float,
                  shape: EyeShape, color: str, glow: float, blink: float, tag: str,
                  side: int) -> None:
        points = self._eye_points(cx, cy, width, height, shape, blink, side)
        # Glow layers use the same contour as the eye, not a rectangular halo.
        layer_count = round(glow * 5)
        for layer in range(layer_count, 0, -1):
            spread = layer * (1.2 + glow * 2.0)
            expanded = self._eye_points(cx, cy, width + spread * 2,
                                        height + spread * 2, shape, blink, side)
            self.canvas.create_polygon(
                expanded, fill=blend(color, BG, 0.07 + glow * 0.10 / layer),
                outline="", smooth=True, splinesteps=12, tags=("face", tag),
            )
        fill = blend(color, BG, 0.76 + glow * 0.18)
        self.canvas.create_polygon(
            points, fill=fill, outline="", smooth=True, splinesteps=16,
            tags=("face", tag),
        )
        if shape.x_eye > 0.01:
            # The X is the error expression's actual glyph; fade it in with its shape.
            alpha = min(1.0, shape.x_eye)
            line_color = blend(color, BG, 0.35 + 0.45 * (1.0 - alpha))
            half_w, half_h = width * 0.29, height * 0.29 * max(0.035, 1 - blink * 0.965)
            line_width = max(2.0, width * 0.075)
            self.canvas.create_line(cx - half_w, cy - half_h, cx + half_w, cy + half_h,
                                    fill=line_color, width=line_width, capstyle="round",
                                    tags=("face", tag))
            self.canvas.create_line(cx + half_w, cy - half_h, cx - half_w, cy + half_h,
                                    fill=line_color, width=line_width, capstyle="round",
                                    tags=("face", tag))

    def draw_face(self) -> None:
        self.canvas.delete("face")
        width = max(self.canvas.winfo_width(), 1)
        height = max(self.canvas.winfo_height(), 1)
        center_x, center_y = width / 2, height * 0.48
        scale = min(width / 700, height / 390)
        speed = self._speed()
        glow = max(0, min(100, int(self.settings["glow"]))) / 100

        self._update_blink(speed)
        self._update_gaze(speed)
        self._update_colours()

        if self.state == "thinking" and self._thinking_bob_started is not None:
            elapsed = (self.time - self._thinking_bob_started) * speed
            bob_period = self._thinking_bob_duration
            # Exactly two compact pulses; no residual oscillation after pulse two.
            if self._thinking_bobs < 2 and elapsed < bob_period * 2:
                phase = (elapsed % bob_period) / bob_period
                bob_offset = -5.0 * math.sin(math.pi * phase) * scale
                self._thinking_bobs = min(2, int(elapsed / bob_period))
            else:
                bob_offset = 0.0
                self._thinking_bobs = 2
                self._thinking_bob_started = None
                self.gaze_pause_until = float("inf")
        else:
            bob_offset = 0.0

        shapes = self._current_shapes()
        eye_width, eye_height = 128 * scale, 112 * scale
        gap = 44 * scale
        eye_color = self.display_eye_color
        active_color = self.display_accent_color if self.state in {
            "thinking", "listening", "error", "happy"
        } else eye_color
        for index, shape in enumerate(shapes):
            side = -1 if index == 0 else 1
            cx = center_x + side * (gap / 2 + eye_width * shape.width / 2)
            cx += (self.look_x + shape.x * 12.0) * scale
            cy = center_y + (self.look_y + shape.y * 16.0 + bob_offset) * scale
            # Keep geometry parameters proportional, while preserving per-eye asymmetry.
            eye_w = eye_width * shape.width
            eye_h = eye_height * shape.height
            self._draw_eye(cx, cy, eye_w, eye_h, shape, active_color, glow,
                           self.blink_amount, f"eye{index}", side)

        if self.state == "happy" and self._happy_until and self.time >= self._happy_until:
            # The happy hold expires on the animation clock; one morph takes over cleanly.
            self._happy_until = 0.0
            self.set_state("idle")

    def animate(self) -> None:
        if self.closed:
            return
        self.time += (FRAME_MS / 1000.0) * self._speed()
        self._poll_results()
        self.draw_face()
        self._animate_ticker()
        self.root.after(FRAME_MS, self.animate)

    def open_settings(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("DEBO — Settings")
        window.configure(bg=PANEL)
        window.resizable(False, False)
        window.transient(self.root)
        window.grab_set()
        panel = tk.Frame(window, bg=PANEL, padx=22, pady=20)
        panel.pack(fill="both", expand=True)
        tk.Label(panel, text="DEBO settings", bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(0, 16))

        color_row = tk.Frame(panel, bg=PANEL)
        color_row.pack(fill="x")
        tk.Label(color_row, text="Eye colour", bg=PANEL, fg="#D4E5F2").pack(side="left")

        def choose_color() -> None:
            chosen = colorchooser.askcolor(color=self.settings["eye_color"],
                                           title="Choose DEBO's eye colour", parent=window)[1]
            if chosen:
                self.settings["eye_color"] = chosen
                color_button.configure(bg=chosen)

        color_button = tk.Button(color_row, text="Choose colour", command=choose_color,
                                 bg=self.settings["eye_color"], fg="#061015", relief="flat", padx=12)
        color_button.pack(side="right")
        tk.Label(panel, text="Glow intensity", bg=PANEL, fg="#D4E5F2").pack(
            anchor="w", pady=(16, 0))
        glow_var = tk.IntVar(value=int(self.settings["glow"]))
        ttk.Scale(panel, from_=0, to=100, variable=glow_var, orient="horizontal", length=320).pack(
            fill="x", pady=(4, 12))
        tk.Label(panel, text="Animation speed", bg=PANEL, fg="#D4E5F2").pack(anchor="w")
        speed_var = tk.DoubleVar(value=float(self.settings["animation_speed"]))
        ttk.Scale(panel, from_=0.5, to=2.0, variable=speed_var, orient="horizontal", length=320).pack(
            fill="x", pady=(4, 12))
        accent_var = tk.BooleanVar(value=bool(self.settings["automatic_accents"]))
        tk.Checkbutton(panel, text="Activity-specific eye colours", variable=accent_var,
                       bg=PANEL, fg="#D4E5F2", activebackground=PANEL,
                       activeforeground="#FFFFFF", selectcolor="#182330").pack(anchor="w", pady=(2, 12))
        sound_var = tk.BooleanVar(value=bool(self.settings["sound_enabled"]))
        tk.Checkbutton(panel, text="Enable robotic sound effects", variable=sound_var,
                       bg=PANEL, fg="#D4E5F2", activebackground=PANEL,
                       activeforeground="#FFFFFF", selectcolor="#182330").pack(anchor="w", pady=(0, 8))
        volume_var = tk.IntVar(value=int(self.settings["sound_volume"]))
        ttk.Scale(panel, from_=0, to=100, variable=volume_var, orient="horizontal", length=320).pack(
            fill="x", pady=(4, 16))

        def save_and_close() -> None:
            self.settings["glow"] = int(glow_var.get())
            self.settings["animation_speed"] = round(float(speed_var.get()), 2)
            self.settings["automatic_accents"] = accent_var.get()
            self.settings["sound_enabled"] = sound_var.get()
            self.settings["sound_volume"] = int(volume_var.get())
            self.sound.set_enabled(self.settings["sound_enabled"])
            self.sound.set_volume(self.settings["sound_volume"] / 100)
            save_settings(self.settings)
            window.destroy()

        tk.Button(panel, text="Save settings", command=save_and_close, bg="#12313A", fg="#D9FFFF",
                  activebackground="#1B4C58", activeforeground="#FFFFFF", relief="flat",
                  padx=16, pady=9).pack(anchor="e")

    def mainloop(self) -> None:
        """Compatibility helper for callers that want to run the face explicitly."""
        self.root.mainloop()


def main() -> None:
    DeboFace()


if __name__ == "__main__":
    main()
