"""DEBO's expressive animated desktop face.

Launch from the project root with ``uv run python -m desk_robot.face``.
Tkinter is used for rendering; all Canvas operations remain on the UI thread.
"""

from __future__ import annotations

import logging
import math
import queue
import random
import tkinter as tk
from concurrent.futures import Future, ThreadPoolExecutor

from desk_robot.core.events import RobotEvent, RobotEventType
from desk_robot.face_geometry import (
    EXPRESSION_ALIASES,
    EXPRESSION_PRESETS,
    EXPRESSIONS,
    EyeShape,
    blend,
    interpolate_colour,
    morph_shape,
    smoothstep,
)
from desk_robot.face_settings import (
    DEFAULT_SETTINGS,  # noqa: F401
    load_settings,
    save_settings,
)
from desk_robot.robot import DeskRobot
from desk_robot.sound import SoundManager
from desk_robot.speech import SpeechSynthesizer
from desk_robot.voice import VoiceController, VoiceError

BG = "#05080D"
PANEL = "#0C131D"
TEXT = "#E8F5FF"
MUTED = "#8298AA"

COLOUR_TRANSITION_SECONDS = 0.34
GAZE_MIN_INTERVAL = 2.2
GAZE_MAX_INTERVAL = 4.0
FRAME_MS = 16

class DeboFace:
    """Tkinter UI with a responsive background worker and morphable eye geometry."""
    logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(threadName)s %(name)s: %(message)s",
        )
    def __init__(self) -> None:
        self.settings = load_settings()
        self._robot_events: queue.Queue[RobotEvent] = queue.Queue()
        self.robot = DeskRobot(event_sink=self._queue_robot_event)
        self.sound = SoundManager(
            enabled=self.settings["sound_enabled"],
            volume=self.settings["sound_volume"] / 100,
        )
        self.voice = VoiceController()
        self.speech = SpeechSynthesizer(
            enabled=self.settings["speech_enabled"],
            volume=self.settings["speech_volume"] / 100,
            rate=self.settings["speech_rate"],
        )
        self.speech_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="debo-speech")
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="debo-brain")
        self.results: queue.Queue[tuple[str, str, int]] = queue.Queue()

        self.state = "idle"
        self.time = 0.0
        self.busy = False
        self.closed = False
        self.response = "Hey! I'm DEBO. What's on your mind?"
        self.idle_callback: str | None = None
        self._request_id = 0
        self._active_future: Future[str] | None = None
        self._follow_up_after_speech = False
        self._expression_started = 0.0
        self._expression_from = EXPRESSIONS["idle"]
        self._expression_to = EXPRESSIONS["idle"]
        self._expression_duration = 0.32
        self._happy_until = 0.0
        self._idle_since = 0.0
        self._sleeping = False
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
        self._ticker_items: list[str] = []
        self._ticker_index = 0
        self._ticker_hold_until = 0.0
        self._ticker_item = self.ticker_canvas.create_text(
            0, 15, text="", anchor="w", fill="#C8E8F4",
            font=("Segoe UI", 10, "bold"),
        )
        self._ticker_x = 0.0
        self._ticker_speed = 2.0
        self.info_panel.pack(fill="x", padx=24, pady=(4, 8))
        self.info_panel.pack_forget()
        response_panel = tk.Frame(self.root, bg=PANEL, padx=18, pady=14)
        response_panel.pack(fill="x", padx=24, pady=(4, 14))
        self.response_label = tk.Label(
            response_panel, text=self.response, bg=PANEL, fg="#C9D9E5",
            font=("Segoe UI", 11), wraplength=720, justify="center",
        )
        self.response_label.pack(fill="x")

        self.listen_hint = tk.Label(
            self.root,
            text="SAY “HEY DEBO” TO TALK · SAY “HELP” FOR VOICE COMMANDS",
            bg=BG, fg=MUTED, font=("Segoe UI", 9, "bold"),
        )
        self.listen_hint.pack(fill="x", padx=24, pady=(0, 18))

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
        self.speech.close()
        self.speech_executor.shutdown(wait=False, cancel_futures=True)
        self.executor.shutdown(wait=False, cancel_futures=True)
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _set_expression(self, state: str, duration: float = 0.16) -> None:
        """Begin a single cancellable morph from the currently displayed geometry."""
        target = EXPRESSIONS.get(state, EXPRESSIONS["idle"])
        self._set_expression_shapes(target, duration)

    def show_expression(self, name: str, duration: float = 0.15) -> bool:
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
        self._expression_duration = max(0.075, duration)

    def set_state(self, state: str) -> None:
        if state == self.state:
            return
        self._set_expression(state, 0.18 if state in {"happy", "thinking"} else 0.12)
        self.state = state
        if state == "idle":
            self._idle_since = self.time
        else:
            self._sleeping = False
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

    def _speak_text(self, text: str) -> None:
        """Speak away from Tk's UI thread and temporarily mute DEBO's own microphone."""
        if self.closed:
            return
        self.results.put(("speech_start", "", -1))
        try:
            self.voice.pause()
            self.speech.speak(text)
        except Exception:
            logging.getLogger(__name__).exception("DEBO speech playback failed")
        finally:
            self.voice.resume()
            if not self.closed:
                self.results.put(("speech_done", "", -1))

    def _handle_settings_command(self, message: str) -> str | None:
        """Apply common spoken preference commands without opening a settings dialog."""
        import re

        text = " ".join(message.lower().strip().split())
        colors = {
            "cyan": "#00D9D0", "teal": "#00BFAE", "blue": "#329BFF",
            "light blue": "#70C8FF", "purple": "#B58CFF", "pink": "#FF80C8",
            "magenta": "#FF4FD8", "green": "#52E39A", "lime": "#B7F34A",
            "red": "#FF5B68", "orange": "#FF9B54", "yellow": "#FFD166",
            "white": "#F2F7FF", "gold": "#FFC857",
        }
        colour_match = re.search(
            r"(?:change|set|make) (?:(?:my|the) )?(?:eye colour|eye color|eyes|eye) (?:to )?(.+)$",
            text,
        )
        if colour_match:
            requested = colour_match.group(1).strip(" .!?")
            if requested in colors:
                self.settings["eye_color"] = colors[requested]
                save_settings(self.settings)
                self.show_expression("happy", 0.10)
                return f"Eye colour changed to {requested}."
            if re.fullmatch(r"#[0-9a-f]{6}", requested):
                self.settings["eye_color"] = requested
                save_settings(self.settings)
                return "Eye colour updated."
            return "Try a colour like blue, teal, purple, pink, green, red, orange, or white."

        if "eye glow" in text or "glow intensity" in text:
            if "low" in text:
                glow = 20
            elif "medium" in text or "normal" in text:
                glow = 55
            elif "high" in text or "bright" in text:
                glow = 85
            else:
                match = re.search(r"([0-9]{1,3})", text)
                if not match:
                    return "Say eye glow low, medium, high, or a percentage from zero to one hundred."
                glow = int(match.group(1))
            self.settings["glow"] = max(0, min(100, glow))
            save_settings(self.settings)
            return f"Eye glow set to {self.settings['glow']} percent."
        if "automatic accents" in text or "activity colours" in text or "activity colors" in text:
            if any(word in text for word in ("off", "disable", "stop")):
                enabled = False
            elif any(word in text for word in ("on", "enable", "start")):
                enabled = True
            else:
                return "Say automatic accents on or automatic accents off."
            self.settings["automatic_accents"] = enabled
            save_settings(self.settings)
            return f"Activity-specific eye colours {'enabled' if enabled else 'disabled'}."
        if "speech rate" in text or "speaking speed" in text:
            match = re.search(r"([0-9]{2,3})", text)
            if not match:
                return "Say speech rate followed by a number from 120 to 230."
            rate = max(120, min(230, int(match.group(1))))
            self.settings["speech_rate"] = rate
            self.speech.set_rate(rate)
            save_settings(self.settings)
            return f"Speech rate set to {rate} words per minute."
        if any(phrase in text for phrase in ("turn sound off", "turn sounds off", "disable sound", "mute sound effects")):
            self.settings["sound_enabled"] = False
            self.sound.set_enabled(False)
            save_settings(self.settings)
            return "Sound effects are off."
        if any(phrase in text for phrase in ("turn sound on", "turn sounds on", "enable sound", "unmute sound effects")):
            self.settings["sound_enabled"] = True
            self.sound.set_enabled(True)
            save_settings(self.settings)
            return "Sound effects are on."
        if any(phrase in text for phrase in ("turn speech off", "turn talking off", "disable speech", "stop talking")):
            self.settings["speech_enabled"] = False
            self.speech.set_enabled(False)
            save_settings(self.settings)
            return "Speech is off. I'll keep responding on screen."
        if any(phrase in text for phrase in ("turn speech on", "turn talking on", "enable speech", "start talking")):
            self.settings["speech_enabled"] = True
            self.speech.set_enabled(True)
            save_settings(self.settings)
            return "Speech is on."
        if "animation speed" in text or "animations faster" in text or "animations slower" in text:
            if "fast" in text or "faster" in text:
                speed = 2.0
            elif "slow" in text or "slower" in text:
                speed = 0.65
            elif "normal" in text:
                speed = 1.0
            else:
                match = re.search(r"(?:to\s+)?([0-9]+(?:\.[0-9]+)?)", text)
                if not match:
                    return "Say animation speed fast, normal, slow, or a number from 0.5 to 2."
                speed = float(match.group(1))
            self.settings["animation_speed"] = max(0.5, min(2.0, speed))
            save_settings(self.settings)
            return f"Animation speed set to {self.settings['animation_speed']:.1f}."
        if "speech volume" in text or "voice volume" in text or "speaking volume" in text:
            match = re.search(r"([0-9]{1,3})", text)
            if not match:
                return "Say speech volume followed by a percentage from zero to one hundred."
            volume = max(0, min(100, int(match.group(1))))
            self.settings["speech_volume"] = volume
            self.speech.set_volume(volume / 100)
            save_settings(self.settings)
            return f"Speech volume set to {volume} percent."
        if "sound volume" in text or "sound effects volume" in text:
            match = re.search(r"([0-9]{1,3})", text)
            if not match:
                return "Say sound volume followed by a percentage from zero to one hundred."
            volume = max(0, min(100, int(match.group(1))))
            self.settings["sound_volume"] = volume
            self.sound.set_volume(volume / 100)
            save_settings(self.settings)
            return f"Sound effects volume set to {volume} percent."
        if text in {"settings", "open settings", "show settings", "change settings"}:
            return "Try eye colour blue, eye glow high, animation speed fast, automatic accents off, speech rate 170, or speech volume 70."
        return None

    def _finish_settings_command(self, response: str) -> None:
        if self._active_future is not None:
            self._active_future.cancel()
        self._request_id += 1
        self.response = response
        self.response_label.configure(text=response)
        self.busy = False
        self.hide_information()
        self.set_state("happy")
        self._happy_until = self.time + 0.75
        if self.settings.get("speech_enabled", True):
            self.speech_executor.submit(self._speak_text, response)
        self.sound.play("success")

    def submit_message(self, message: str) -> None:
        """Process a recognised voice transcript without any text-entry UI."""
        message = str(message).strip()
        if not message or self.closed:
            return
        settings_response = self._handle_settings_command(message)
        if settings_response is not None:
            self._finish_settings_command(settings_response)
            return
        if self._active_future is not None:
            self._active_future.cancel()
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
        elif any(word in lowered for word in ("news", "headlines", "latest stories", "what's happening", "what is happening", "next story", "another story", "next headline", "full story", "read the story", "read this story", "read article")):
            self.show_information_loading("news")
        else:
            self.hide_information()
        future = self.executor.submit(self.robot.respond, message)
        self._active_future = future
        future.add_done_callback(
            lambda result, rid=request_id: self._collect_result(result, rid)
        )

    def _queue_robot_event(self, event: RobotEvent) -> None:
        """Receive brain events from worker threads without touching Tkinter."""
        self._robot_events.put(event)

    def _poll_robot_events(self) -> None:
        """Apply semantic brain events on the Tkinter thread."""
        while True:
            try:
                event = self._robot_events.get_nowait()
            except queue.Empty:
                return

            if self.closed:
                continue
            if event.type in {
                RobotEventType.WEATHER_LOOKUP_STARTED,
                RobotEventType.NEWS_LOOKUP_STARTED,
            }:
                if self.busy:
                    self.show_expression("curious", 0.18)
            elif event.type in {
                RobotEventType.WEATHER_LOOKUP_FAILED,
                RobotEventType.NEWS_LOOKUP_FAILED,
            } and self.busy:
                self.show_expression("concerned", 0.18)

    def _collect_result(self, future: Future[str], request_id: int) -> None:
        """Worker callback: queue results only; never call Tk from this thread."""
        try:
            self.results.put(("ok", str(future.result()), request_id))
        except Exception as error:  # noqa: BLE001
            self.results.put(("error", str(error), request_id))

    def _poll_results(self) -> None:
        self._poll_robot_events()
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
                    self.show_expression("listening", 0.10)
                    self.response_label.configure(text="I'm listening — go ahead!")
                    self.sound.play("curious")
                continue

            if kind == "followup_listening":
                if not self.busy:
                    self.status.configure(text="LISTENING FOR YOUR ANSWER", fg=self.current_accent())
                    self.set_state("listening")
                continue

            if kind == "standby":
                if not self.busy and self.state == "listening":
                    self.return_to_idle()
                    self.status.configure(text="WAITING FOR HEY DEBO", fg=self.current_accent())
                continue

            if kind == "voice_error":
                self.response = result
                self.response_label.configure(text=result)
                if not self.busy:
                    self.set_state("error")
                    self.idle_callback = self.root.after(3500, self.return_to_idle)
                continue

            if kind == "speech_start":
                self.set_state("speaking")
                self.show_expression("speaking", 0.09)
                continue

            if kind == "speech_done":
                if self._follow_up_after_speech:
                    self._follow_up_after_speech = False
                    self.voice.listen_for_follow_up()
                    self.status.configure(text="LISTENING FOR YOUR ANSWER", fg=self.current_accent())
                    self.set_state("listening")
                    self.show_expression("listening", 0.12)
                    self.response_label.configure(text="Go ahead — I'm listening.")
                elif not self.busy:
                    self.set_state("happy")
                    self._happy_until = self.time + 0.55
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
                story_text = getattr(self.robot, "last_story_text", None)
                speech_text = story_text if story_text else result
                if getattr(self.robot, "pending_intent", None):
                    if self.settings.get("speech_enabled", True) and speech_text:
                        self._follow_up_after_speech = True
                    else:
                        self.voice.listen_for_follow_up()
                        self.status.configure(text="LISTENING FOR YOUR ANSWER", fg=self.current_accent())
                        self.set_state("listening")
                if self.settings.get("speech_enabled", True) and speech_text:
                    self.speech_executor.submit(self._speak_text, speech_text)
            elif getattr(self.robot, "last_intent", "") in {"weather", "news", "next_news", "full_story"}:
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
        self.ticker_canvas.itemconfigure(self._ticker_item, text="")
        self._ticker_text = ""
        self._ticker_items = []

    def show_information_loading(self, kind: str) -> None:
        self.show_expression("curious", 0.24)
        self.info_panel.pack(fill="x", padx=24, pady=(4, 8))
        self.info_title.configure(text=f"{kind.upper()}  /  CONNECTING")
        self.info_main.configure(text="One moment — I'm checking the latest information.")
        self.info_meta.configure(text="Live data · Network requests run in the background")
        self._set_ticker(f"DEBO IS FETCHING {kind.upper()}…")

    def _set_ticker(self, text: str) -> None:
        items = [part.strip() for part in str(text).splitlines() if part.strip()]
        if len(items) == 1 and "     •     " in items[0]:
            items = [part.strip() for part in items[0].split("     •     ") if part.strip()]
        self._ticker_items = items or [""]
        self._ticker_index = 0
        self._ticker_hold_until = 0.0
        self._ticker_text = self._ticker_items[0]
        self._ticker_x = float(self.ticker_canvas.winfo_width() or 700)
        self.ticker_canvas.itemconfigure(self._ticker_item, text=self._ticker_text)
        self.ticker_canvas.coords(self._ticker_item, self._ticker_x, 15)

    def _animate_ticker(self) -> None:
        if not self._ticker_text or not self.info_panel.winfo_ismapped():
            return
        if self.time < self._ticker_hold_until:
            return
        self._ticker_x -= self._ticker_speed
        bounds = self.ticker_canvas.bbox(self._ticker_item)
        if bounds and bounds[2] < 0:
            self._ticker_index = (self._ticker_index + 1) % len(self._ticker_items)
            self._ticker_text = self._ticker_items[self._ticker_index]
            self._ticker_hold_until = self.time + 0.28
            self._ticker_x = float(self.ticker_canvas.winfo_width() or 700)
            self.ticker_canvas.itemconfigure(self._ticker_item, text=self._ticker_text)
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
        published = first.published_at.strftime("%d %b · %H:%M UTC") if first.published_at else "publication time unavailable"
        self.info_meta.configure(text=f"{first.source or report.provider}  ·  {published}  ·  Retrieved {report.fetched_at.strftime('%H:%M UTC')}")
        self._set_ticker("\n".join(f"{index}. {article.title} — {article.source}" for index, article in enumerate(articles, start=1)))

    def _present_latest_information(self) -> None:
        weather = getattr(self.robot, "last_weather_report", None)
        news = getattr(self.robot, "last_news_report", None)
        if weather is not None:
            self.present_weather(weather)
        elif news is not None:
            self.present_news(news)
        elif getattr(self.robot, "last_intent", "") in {"weather", "news", "next_news", "full_story"}:
            intent = self.robot.last_intent
            self.info_panel.pack(fill="x", padx=24, pady=(4, 8))
            if intent == "weather" and "which location" in self.response.lower():
                self.info_title.configure(text="WEATHER  /  LOCATION NEEDED")
                self.info_main.configure(text="Tell me a city or town, for example: “weather in London”.")
                self.info_meta.configure(text="I'll fetch live conditions and today's high/low.")
                self._set_ticker("WEATHER  •  CHOOSE A LOCATION")
            else:
                self.info_title.configure(text=f"{intent.replace('_', ' ').upper()}  /  UNAVAILABLE")
                self.info_main.configure(text="I couldn't retrieve that information just now.")
                self.info_meta.configure(text="Check your connection and try again. DEBO is still listening.")
                self._set_ticker("LIVE INFORMATION UNAVAILABLE  •  PLEASE TRY AGAIN")

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
        if (
            self.state not in {"thinking", "happy", "error"}
            and self.blink_started is None
            and self.time >= self.next_blink
        ):
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
        if self.state == "speaking":
            # A tiny, irregular eye-height pulse makes speech feel physically embodied.
            pulse = 0.022 * math.sin(self.time * 17.0) + 0.008 * math.sin(self.time * 7.3)
            shapes = tuple(
                EyeShape(**{
                    **shape.__dict__,
                    "height": max(0.035, shape.height * (1.0 + pulse)),
                    "y": shape.y + pulse * 0.35,
                })
                for shape in shapes
            )
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
        if self.state == "idle" and not self._sleeping and self.time - self._idle_since >= 90.0:
            self.show_expression("sleeping", 0.55)
            self._sleeping = True
        self.draw_face()
        self._animate_ticker()
        self.root.after(FRAME_MS, self.animate)

    def mainloop(self) -> None:
        """Compatibility helper for callers that want to run the face explicitly."""
        self.root.mainloop()

def main() -> None:
    DeboFace()

if __name__ == "__main__":
    main()
