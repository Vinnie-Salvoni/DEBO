"""DEBO's animated desktop face.

Run with:
    uv run python -m desk_robot.face
"""

from __future__ import annotations

import json
import math
import random
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, ttk

from desk_robot.robot import DeskRobot


SETTINGS_PATH = Path.home() / ".debo_face_settings.json"
BACKGROUND = "#05080D"

DEFAULT_SETTINGS = {
    "eye_color": "#00D9D0",
    "accent_color": "#4D9DFF",
    "glow": 55,
    "animation_speed": 1.0,
    "automatic_accents": True,
}


def load_settings() -> dict:
    settings = DEFAULT_SETTINGS.copy()
    try:
        saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        if isinstance(saved, dict):
            settings.update(
                {key: value for key, value in saved.items() if key in settings}
            )
    except OSError, json.JSONDecodeError:
        pass
    return settings


def save_settings(settings: dict) -> None:
    try:
        SETTINGS_PATH.write_text(
            json.dumps(settings, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def blend(color: str, background: str, amount: float) -> str:
    """Blend two hex colours. Amount 0 returns background; 1 returns color."""
    amount = max(0.0, min(1.0, amount))
    color = color.lstrip("#")
    background = background.lstrip("#")

    channels = [
        round(
            int(background[i : i + 2], 16) * (1 - amount)
            + int(color[i : i + 2], 16) * amount
        )
        for i in (0, 2, 4)
    ]
    return "#" + "".join(f"{channel:02x}" for channel in channels)


class DeboFace:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("DEBO — Desktop Face")
        self.root.geometry("760x520")
        self.root.minsize(560, 420)
        self.root.configure(bg=BACKGROUND)

        self.robot = DeskRobot()
        self.settings = load_settings()

        self.state = "idle"
        self.time = 0.0
        self.next_blink = random.uniform(2.0, 4.0)
        self.blink_started: float | None = None
        self.blink_duration = 0.22
        self.blink_amount = 0.0
        self.busy = False
        self.response = ""

        self.canvas = tk.Canvas(
            self.root,
            bg=BACKGROUND,
            highlightthickness=0,
        )
        self.canvas.pack(fill="both", expand=True, padx=12, pady=(12, 4))

        controls = tk.Frame(self.root, bg=BACKGROUND)
        controls.pack(fill="x", padx=16, pady=(4, 16))

        self.entry = tk.Entry(
            controls,
            font=("Segoe UI", 12),
            bg="#111923",
            fg="#E8F5FF",
            insertbackground="#E8F5FF",
            relief="flat",
            highlightthickness=1,
            highlightbackground="#263444",
        )
        self.entry.pack(side="left", fill="x", expand=True, ipady=10)
        self.entry.bind("<Return>", self.submit_message)

        self.send_button = tk.Button(
            controls,
            text="Send",
            command=self.submit_message,
            font=("Segoe UI", 10, "bold"),
            bg="#12313A",
            fg="#D9FFFF",
            activebackground="#1B4C58",
            activeforeground="#FFFFFF",
            relief="flat",
            padx=16,
            pady=8,
        )
        self.send_button.pack(side="left", padx=(8, 0))

        tk.Button(
            controls,
            text="⚙ Settings",
            command=self.open_settings,
            font=("Segoe UI", 10),
            bg="#111923",
            fg="#D4E5F2",
            activebackground="#263444",
            activeforeground="#FFFFFF",
            relief="flat",
            padx=12,
            pady=8,
        ).pack(side="left", padx=(8, 0))

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.entry.focus_set()
        self.animate()
        self.root.mainloop()

    def close(self) -> None:
        save_settings(self.settings)
        self.root.destroy()

    def set_state(self, state: str) -> None:
        self.state = state

    def submit_message(self, _event=None) -> None:
        message = self.entry.get().strip()
        if not message or self.busy:
            return

        self.entry.delete(0, "end")
        self.busy = True
        self.entry.configure(state="disabled")
        self.send_button.configure(state="disabled")
        self.set_state("thinking")

        # Give the face time to show its thinking expression.
        self.root.after(250, lambda: self.get_response(message))

    def get_response(self, message: str) -> None:
        try:
            self.response = self.robot.respond(message)
            self.set_state("speaking")
        except Exception as error:
            self.response = f"I ran into a problem: {error}"
            self.set_state("error")

        self.busy = False
        self.entry.configure(state="normal")
        self.send_button.configure(state="normal")
        self.entry.focus_set()

        self.root.after(4500, self.return_to_idle)

    def return_to_idle(self) -> None:
        if not self.busy and self.state in {"speaking", "error"}:
            self.set_state("idle")

    def current_accent(self) -> str:
        if self.settings["automatic_accents"]:
            if self.state == "thinking":
                return "#A78BFA"
            if self.state == "listening":
                return "#4DA3FF"
            if self.state == "error":
                return "#FF7B83"
        return str(self.settings["accent_color"])

    def rounded_rectangle(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        radius: float,
        color: str,
        tag: str = "face",
    ) -> None:
        """Draw a filled rectangle with genuinely rounded corners."""
        radius = max(1.0, min(radius, width / 2, height / 2))
        points = []

        # Sample each corner's quarter-circle.
        corners = [
            (x + radius, y + radius, 180),
            (x + width - radius, y + radius, 270),
            (x + width - radius, y + height - radius, 0),
            (x + radius, y + height - radius, 90),
        ]

        for cx, cy, start_angle in corners:
            for step in range(9):
                angle = math.radians(start_angle + step * 90 / 8)
                points.extend(
                    (
                        cx + radius * math.cos(angle),
                        cy + radius * math.sin(angle),
                    )
                )

        self.canvas.create_polygon(
            points,
            fill=color,
            outline="",
            smooth=True,
            splinesteps=20,
            tags=tag,
        )

    def update_blink(self, speed: float) -> None:
        if self.blink_started is None and self.time >= self.next_blink:
            self.blink_started = self.time

        if self.blink_started is not None:
            elapsed = self.time - self.blink_started
            progress = elapsed / max(0.08, self.blink_duration / speed)

            if progress >= 1:
                self.blink_started = None
                self.blink_amount = 0.0
                self.next_blink = self.time + random.uniform(2.0, 4.5) / speed
            else:
                # Smooth close and open.
                self.blink_amount = math.sin(progress * math.pi) ** 2

    def draw_face(self) -> None:
        self.canvas.delete("face")

        width = max(self.canvas.winfo_width(), 1)
        height = max(self.canvas.winfo_height(), 1)
        center_x = width / 2
        center_y = height * 0.43
        scale = min(width / 650, height / 370)

        speed = max(0.5, min(2.0, float(self.settings["animation_speed"])))
        glow = max(0, min(100, int(self.settings["glow"]))) / 100
        eye_color = str(self.settings["eye_color"])
        accent = self.current_accent()

        self.update_blink(speed)

        eye_width = 112 * scale
        eye_height = 100 * scale
        gap = 40 * scale
        eye_height *= max(0.035, 1 - self.blink_amount * 0.965)

        offset_x = 0.0
        offset_y = 0.0

        # Expressions are communicated entirely through the eyes.
        if self.state == "listening":
            eye_width *= 1.04
            eye_height *= 1.05
        elif self.state == "thinking":
            offset_x = 7 * scale * math.sin(self.time * 2.2 * speed)
            offset_y = 3 * scale * math.sin(self.time * 3 * speed)
            eye_height *= 0.91 + 0.05 * math.sin(self.time * 3 * speed)
        elif self.state == "speaking":
            eye_height *= 0.96 + 0.04 * math.sin(self.time * 4 * speed)
        elif self.state == "happy":
            eye_height *= 0.82
            eye_width *= 1.04
        elif self.state == "error":
            offset_y = 3 * scale * math.sin(self.time * 7 * speed)

        left_x = center_x - gap / 2 - eye_width + offset_x
        right_x = center_x + gap / 2 + offset_x
        eye_y = center_y - eye_height / 2 + offset_y
        radius = min(eye_width, eye_height) * 0.28

        active_color = (
            accent if self.state in {"thinking", "listening", "error"} else eye_color
        )

        # Several soft layers simulate an LED glow without external libraries.
        layer_count = 1 + round(glow * 5)
        for layer in range(layer_count, 0, -1):
            spread = layer * (1.5 + glow * 2.5) * scale
            layer_color = blend(active_color, BACKGROUND, 0.12 + glow * 0.12 / layer)

            for x in (left_x, right_x):
                self.rounded_rectangle(
                    x - spread,
                    eye_y - spread,
                    eye_width + spread * 2,
                    eye_height + spread * 2,
                    radius + spread / 2,
                    layer_color,
                )

        eye_fill = blend(active_color, BACKGROUND, 0.76 + glow * 0.18)

        for x in (left_x, right_x):
            self.rounded_rectangle(
                x,
                eye_y,
                eye_width,
                eye_height,
                radius,
                eye_fill,
            )

        # Keep the face free of a mouth, nose, labels and decorative features.
        if self.response:
            self.canvas.create_text(
                center_x,
                height * 0.77,
                text=self.response,
                fill="#B6C9D9",
                font=("Segoe UI", max(9, int(11 * scale))),
                width=max(200, width - 80),
                justify="center",
                tags=("face",),
            )

    def animate(self) -> None:
        self.time += 0.016 * float(self.settings["animation_speed"])
        self.draw_face()
        self.root.after(16, self.animate)

    def open_settings(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("DEBO — Appearance")
        window.configure(bg="#0C121A")
        window.resizable(False, False)
        window.transient(self.root)
        window.grab_set()

        panel = tk.Frame(window, bg="#0C121A", padx=20, pady=18)
        panel.pack(fill="both", expand=True)

        tk.Label(
            panel,
            text="Face appearance",
            bg="#0C121A",
            fg="#E8F5FF",
            font=("Segoe UI", 15, "bold"),
        ).pack(anchor="w", pady=(0, 14))

        color_row = tk.Frame(panel, bg="#0C121A")
        color_row.pack(fill="x")

        tk.Label(
            color_row,
            text="Eye colour",
            bg="#0C121A",
            fg="#D4E5F2",
        ).pack(side="left")

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
            color_row,
            text="Choose colour",
            command=choose_color,
            bg=self.settings["eye_color"],
            fg="#061015",
            relief="flat",
            padx=12,
        )
        color_button.pack(side="right")

        tk.Label(
            panel,
            text="Glow intensity",
            bg="#0C121A",
            fg="#D4E5F2",
        ).pack(anchor="w", pady=(16, 0))

        glow_var = tk.IntVar(value=int(self.settings["glow"]))
        ttk.Scale(
            panel,
            from_=0,
            to=100,
            variable=glow_var,
            orient="horizontal",
            length=300,
        ).pack(fill="x", pady=(4, 12))

        tk.Label(
            panel,
            text="Animation speed",
            bg="#0C121A",
            fg="#D4E5F2",
        ).pack(anchor="w")

        speed_var = tk.DoubleVar(value=float(self.settings["animation_speed"]))
        ttk.Scale(
            panel,
            from_=0.5,
            to=2.0,
            variable=speed_var,
            orient="horizontal",
            length=300,
        ).pack(fill="x", pady=(4, 12))

        automatic_var = tk.BooleanVar(value=bool(self.settings["automatic_accents"]))
        tk.Checkbutton(
            panel,
            text="Use activity-specific accent colours",
            variable=automatic_var,
            bg="#0C121A",
            fg="#D4E5F2",
            activebackground="#0C121A",
            activeforeground="#FFFFFF",
            selectcolor="#182330",
        ).pack(anchor="w", pady=(2, 16))

        def save_and_close() -> None:
            self.settings["glow"] = int(glow_var.get())
            self.settings["animation_speed"] = round(speed_var.get(), 2)
            self.settings["automatic_accents"] = automatic_var.get()
            save_settings(self.settings)
            window.destroy()

        tk.Button(
            panel,
            text="Save settings",
            command=save_and_close,
            bg="#12313A",
            fg="#D9FFFF",
            activebackground="#1B4C58",
            activeforeground="#FFFFFF",
            relief="flat",
            padx=14,
            pady=8,
        ).pack(anchor="e")


def main() -> None:
    DeboFace()


if __name__ == "__main__":
    main()
