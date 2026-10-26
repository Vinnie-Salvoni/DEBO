"""DEBO's expressive animated desktop face.

Launch from the project root:
    uv run python -m desk_robot.face
"""

from __future__ import annotations

import json
import math
import queue
import random
import tkinter as tk
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from tkinter import colorchooser, ttk

from desk_robot.robot import DeskRobot
from desk_robot.sound import SoundManager

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


def load_settings() -> dict:
    """Load saved settings, validating values and falling back safely."""
    settings = DEFAULT_SETTINGS.copy()
    try:
        saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        if isinstance(saved, dict):
            settings.update({key: value for key, value in saved.items() if key in settings})
    except (OSError, json.JSONDecodeError):
        pass

    # Keep malformed settings from breaking the animation or Tk widgets.
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


class DeboFace:
    """Tkinter UI with a responsive background worker for DEBO's brain."""

    def __init__(self) -> None:
        self.settings = load_settings()
        self.robot = DeskRobot()
        self.sound = SoundManager(
            enabled=self.settings["sound_enabled"],
            volume=self.settings["sound_volume"] / 100,
        )
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="debo-brain")
        self.results: queue.Queue[tuple[str, str]] = queue.Queue()

        self.state = "idle"
        self.time = 0.0
        self.busy = False
        self.closed = False
        self.response = "Hey! I'm DEBO. What's on your mind?"
        self.idle_callback: str | None = None

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
        self.root.geometry("820x650")
        self.root.minsize(600, 500)
        self.root.configure(bg=BG)

        self._build_interface()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.entry.focus_set()
        self.sound.play("startup")
        self.animate()
        self.root.mainloop()

    def _build_interface(self) -> None:
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=24, pady=(18, 8))

        tk.Label(
            header, text="D E B O", bg=BG, fg=TEXT,
            font=("Segoe UI", 13, "bold"),
        ).pack(side="left")

        self.status = tk.Label(
            header, text="READY WHEN YOU ARE", bg=BG, fg=MUTED,
            font=("Segoe UI", 8, "bold"),
        )
        self.status.pack(side="right")

        self.canvas = tk.Canvas(self.root, bg=BG, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True, padx=12, pady=4)

        response_panel = tk.Frame(self.root, bg=PANEL, padx=18, pady=14)
        response_panel.pack(fill="x", padx=24, pady=(4, 14))
        self.response_label = tk.Label(
            response_panel, text=self.response, bg=PANEL, fg="#C9D9E5",
            font=("Segoe UI", 11), wraplength=720, justify="center",
        )
        self.response_label.pack(fill="x")

        controls = tk.Frame(self.root, bg=BG)
        controls.pack(fill="x", padx=24, pady=(0, 18))

        self.entry = tk.Entry(
            controls, font=("Segoe UI", 12), bg="#111923", fg=TEXT,
            insertbackground=TEXT, relief="flat", bd=0, highlightthickness=1,
            highlightbackground="#263444", highlightcolor="#00D9D0",
        )
        self.entry.pack(side="left", fill="x", expand=True, ipady=12)
        self.entry.bind("<Return>", self.submit_message)

        self.send_button = tk.Button(
            controls, text="Send  ↗", command=self.submit_message,
            font=("Segoe UI", 10, "bold"), bg="#12313A", fg="#D9FFFF",
            activebackground="#1B4C58", activeforeground="#FFFFFF",
            relief="flat", bd=0, padx=18, pady=10, cursor="hand2",
        )
        self.send_button.pack(side="left", padx=(8, 0))

        tk.Button(
            controls, text="⚙", command=self.open_settings,
            font=("Segoe UI", 13), bg="#111923", fg="#D4E5F2",
            activebackground="#263444", activeforeground="#FFFFFF",
            relief="flat", bd=0, padx=13, pady=7, cursor="hand2",
        ).pack(side="left", padx=(8, 0))

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self.idle_callback is not None:
            try:
                self.root.after_cancel(self.idle_callback)
            except tk.TclError:
                pass
        save_settings(self.settings)
        try:
            self.sound.close()
        except (AttributeError, RuntimeError):
            pass
        self.executor.shutdown(wait=False, cancel_futures=True)
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def set_state(self, state: str) -> None:
        self.state = state
        labels = {
            "idle": "READY WHEN YOU ARE",
            "listening": "I'M LISTENING",
            "thinking": "THINKING...",
            "speaking": "RESPONSE READY",
            "happy": "HAPPY TO HELP",
            "error": "OOPS!",
        }
        self.status.configure(text=labels.get(state, "READY WHEN YOU ARE"))
        self.status.configure(fg=self.current_accent())

    def submit_message(self, _event=None) -> None:
        message = self.entry.get().strip()
        if not message or self.busy or self.closed:
            return

        self.entry.delete(0, "end")
        self.busy = True
        self.response = ""
        self.response_label.configure(text="Let me think about that...")
        self.entry.configure(state="disabled")
        self.send_button.configure(state="disabled")
        self._cancel_idle_callback()
        self.set_state("thinking")
        self.sound.play("send")
        # Avoid immediately replacing the send sound with the thinking sound.
        self.root.after(180, lambda: self.sound.play("thinking") if not self.closed else None)

        future = self.executor.submit(self.robot.respond, message)
        future.add_done_callback(self._collect_result)

    def _collect_result(self, future: Future[str]) -> None:
        """Worker callback: queue results only; never call Tk from this thread."""
        try:
            self.results.put(("ok", str(future.result())))
        except Exception as error:  # noqa: BLE001
            self.results.put(("error", str(error)))

    def _poll_results(self) -> None:
        try:
            kind, result = self.results.get_nowait()
        except queue.Empty:
            return

        self.response = result
        self.response_label.configure(text=result)
        self.busy = False
        self.entry.configure(state="normal")
        self.send_button.configure(state="normal")
        self.entry.focus_set()

        if kind == "error":
            self.set_state("error")
            self.sound.play("error")
        else:
            self.set_state("speaking")
            self.sound.play("success")

        self._cancel_idle_callback()
        self.idle_callback = self.root.after(5000, self.return_to_idle)

    def _cancel_idle_callback(self) -> None:
        if self.idle_callback is not None:
            try:
                self.root.after_cancel(self.idle_callback)
            except tk.TclError:
                pass
            self.idle_callback = None

    def return_to_idle(self) -> None:
        self.idle_callback = None
        if not self.busy and self.state in {"speaking", "error", "happy"}:
            self.set_state("idle")

    def current_accent(self) -> str:
        if self.settings["automatic_accents"]:
            colours = {
                "thinking": "#B49AFF",
                "listening": "#65B8FF",
                "error": "#FF7D8A",
                "happy": "#FFD166",
                "speaking": "#68E5CE",
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

        eye_progress = max(0.0, min(1.0, (self.time - self._colour_started) / duration))
        accent_progress = max(0.0, min(1.0, (self.time - self._accent_started) / duration))
        # Smoothstep easing makes both ends of the transition gentle.
        eye_progress = eye_progress * eye_progress * (3 - 2 * eye_progress)
        accent_progress = accent_progress * accent_progress * (3 - 2 * accent_progress)

        self.display_eye_color = interpolate_colour(
            self._colour_from_eye, self._colour_target_eye, eye_progress
        )
        self.display_accent_color = interpolate_colour(
            self._colour_from_accent, self._colour_target_accent, accent_progress
        )

    def rounded_rectangle(
        self, x: float, y: float, width: float, height: float,
        radius: float, color: str,
    ) -> None:
        if width <= 0 or height <= 0:
            return
        radius = max(1.0, min(radius, width / 2, height / 2))
        points: list[float] = []
        corners = [
            (x + radius, y + radius, 180),
            (x + width - radius, y + radius, 270),
            (x + width - radius, y + height - radius, 0),
            (x + radius, y + height - radius, 90),
        ]
        for cx, cy, start in corners:
            for step in range(9):
                angle = math.radians(start + step * 90 / 8)
                points.extend((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        self.canvas.create_polygon(
            points, fill=color, outline="", smooth=True, splinesteps=20, tags="face"
        )

    def _update_blink(self, speed: float) -> None:
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
        # Pick a new direction regularly; keep the eyes gently alive while thinking.
        if self.time >= self.next_gaze_change and self.time >= self.gaze_pause_until:
            self.next_gaze_change = self.time + random.uniform(
                GAZE_MIN_INTERVAL, GAZE_MAX_INTERVAL
            ) / speed
            if self.state == "thinking":
                choices = [(-1, -0.4), (1, -0.4), (-1, 0.2), (1, 0.2), (0, -0.6)]
            elif self.state == "speaking":
                choices = [(-1, 0), (1, 0), (0, -0.3), (0, 0.3)]
            else:
                choices = [
                    (-1, -1), (0, -1), (1, -1),
                    (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1), (0, 0),
                ]
            gx, gy = random.choice(choices)
            self.target_x = gx * 15.0
            self.target_y = gy * 9.0

        # Smooth movement without snapping back to centre when DEBO changes state.
        smoothing = min(0.11, 0.065 * speed)
        self.look_x += (self.target_x - self.look_x) * smoothing
        self.look_y += (self.target_y - self.look_y) * smoothing

    def draw_face(self) -> None:
        self.canvas.delete("face")
        width = max(self.canvas.winfo_width(), 1)
        height = max(self.canvas.winfo_height(), 1)
        center_x = width / 2
        center_y = height * 0.48
        scale = min(width / 700, height / 390)
        speed = max(0.5, min(2.0, float(self.settings["animation_speed"])))
        glow = max(0, min(100, int(self.settings["glow"]))) / 100

        self._update_blink(speed)
        self._update_gaze(speed)
        self._update_colours()

        eye_width = 128 * scale
        eye_height = 112 * scale
        gap = 44 * scale
        offset_x = self.look_x * scale
        offset_y = self.look_y * scale
        pulse = math.sin(self.time * 2.0 * speed)
        width_factor = 1.0
        height_factor = 1.0

        if self.state == "idle":
            height_factor = 0.98 + 0.025 * pulse
            offset_y += math.sin(self.time * 1.1 * speed) * 2.0 * scale
        elif self.state == "listening":
            width_factor = 1.07
            height_factor = 1.08 + 0.035 * math.sin(self.time * 3.2 * speed)
        elif self.state == "thinking":
            offset_x += math.sin(self.time * 2.7 * speed) * 5.0 * scale
            offset_y += math.sin(self.time * 3.5 * speed) * 2.0 * scale
            height_factor = 0.87 + 0.045 * math.sin(self.time * 4.0 * speed)
        elif self.state == "speaking":
            height_factor = 0.96 + 0.07 * math.sin(self.time * 5.0 * speed)
            width_factor = 1.0 + 0.025 * math.sin(self.time * 3.0 * speed)
        elif self.state == "happy":
            width_factor = 1.08
            height_factor = 0.78 + 0.025 * pulse
        elif self.state == "error":
            height_factor = 0.82 + 0.04 * math.sin(self.time * 8.0 * speed)
            offset_y += math.sin(self.time * 8.0 * speed) * 3.5 * scale

        eye_width *= width_factor
        eye_height *= height_factor
        eye_height *= max(0.035, 1 - self.blink_amount * 0.965)

        left_x = center_x - gap / 2 - eye_width + offset_x
        right_x = center_x + gap / 2 + offset_x
        eye_y = center_y - eye_height / 2 + offset_y
        radius = min(eye_width, eye_height) * 0.28

        eye_color = self.display_eye_color
        accent = self.display_accent_color
        active_color = accent if self.state in {"thinking", "listening", "error", "happy"} else eye_color

        # Layered dim shapes create a soft LED glow.
        for layer in range(1 + round(glow * 5), 0, -1):
            spread = layer * (1.5 + glow * 2.5) * scale
            glow_color = blend(active_color, BG, 0.10 + glow * 0.12 / layer)
            for x in (left_x, right_x):
                self.rounded_rectangle(
                    x - spread, eye_y - spread, eye_width + spread * 2,
                    eye_height + spread * 2, radius + spread / 2, glow_color,
                )

        fill = blend(active_color, BG, 0.76 + glow * 0.18)
        for index, x in enumerate((left_x, right_x)):
            little_bob = math.sin(self.time * 1.7 * speed + index * 0.45) * 0.6 * scale
            self.rounded_rectangle(
                x, eye_y + little_bob, eye_width, eye_height, radius, fill
            )

    def animate(self) -> None:
        if self.closed:
            return
        self.time += 0.016 * max(0.5, min(2.0, float(self.settings["animation_speed"])))
        self._poll_results()
        self.draw_face()
        self.root.after(16, self.animate)

    def open_settings(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("DEBO — Settings")
        window.configure(bg=PANEL)
        window.resizable(False, False)
        window.transient(self.root)
        window.grab_set()

        panel = tk.Frame(window, bg=PANEL, padx=22, pady=20)
        panel.pack(fill="both", expand=True)
        tk.Label(
            panel, text="DEBO settings", bg=PANEL, fg=TEXT,
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w", pady=(0, 16))

        color_row = tk.Frame(panel, bg=PANEL)
        color_row.pack(fill="x")
        tk.Label(color_row, text="Eye colour", bg=PANEL, fg="#D4E5F2").pack(side="left")

        def choose_color() -> None:
            chosen = colorchooser.askcolor(
                color=self.settings["eye_color"],
                title="Choose DEBO's eye colour",
                parent=window,
            )[1]
            if chosen:
                self.settings["eye_color"] = chosen
                color_button.configure(bg=chosen)

        color_button = tk.Button(
            color_row, text="Choose colour", command=choose_color,
            bg=self.settings["eye_color"], fg="#061015", relief="flat", padx=12,
        )
        color_button.pack(side="right")

        tk.Label(panel, text="Glow intensity", bg=PANEL, fg="#D4E5F2").pack(
            anchor="w", pady=(16, 0)
        )
        glow_var = tk.IntVar(value=int(self.settings["glow"]))
        ttk.Scale(
            panel, from_=0, to=100, variable=glow_var,
            orient="horizontal", length=320,
        ).pack(fill="x", pady=(4, 12))

        tk.Label(panel, text="Animation speed", bg=PANEL, fg="#D4E5F2").pack(anchor="w")
        speed_var = tk.DoubleVar(value=float(self.settings["animation_speed"]))
        ttk.Scale(
            panel, from_=0.5, to=2.0, variable=speed_var,
            orient="horizontal", length=320,
        ).pack(fill="x", pady=(4, 12))

        accent_var = tk.BooleanVar(value=bool(self.settings["automatic_accents"]))
        tk.Checkbutton(
            panel, text="Activity-specific eye colours", variable=accent_var,
            bg=PANEL, fg="#D4E5F2", activebackground=PANEL,
            activeforeground="#FFFFFF", selectcolor="#182330",
        ).pack(anchor="w", pady=(2, 12))

        sound_var = tk.BooleanVar(value=bool(self.settings["sound_enabled"]))
        tk.Checkbutton(
            panel, text="Enable robotic sound effects", variable=sound_var,
            bg=PANEL, fg="#D4E5F2", activebackground=PANEL,
            activeforeground="#FFFFFF", selectcolor="#182330",
        ).pack(anchor="w", pady=(0, 8))

        tk.Label(panel, text="Sound volume", bg=PANEL, fg="#D4E5F2").pack(anchor="w")
        volume_var = tk.IntVar(value=int(self.settings["sound_volume"]))
        ttk.Scale(
            panel, from_=0, to=100, variable=volume_var,
            orient="horizontal", length=320,
        ).pack(fill="x", pady=(4, 16))

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

        tk.Button(
            panel, text="Save settings", command=save_and_close,
            bg="#12313A", fg="#D9FFFF", activebackground="#1B4C58",
            activeforeground="#FFFFFF", relief="flat", padx=16, pady=9,
        ).pack(anchor="e")

    def mainloop(self) -> None:
        """Compatibility helper for callers that want to run the face explicitly."""
        self.root.mainloop()


def main() -> None:
    DeboFace()


if __name__ == "__main__":
    main()
