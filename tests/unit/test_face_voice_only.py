from pathlib import Path


def test_face_has_no_mouse_or_keyboard_action_widgets() -> None:
    face_path = Path(__file__).resolve().parents[2] / "src" / "desk_robot" / "face.py"
    source = face_path.read_text(encoding="utf-8")

    assert "tk.Button" not in source
    assert "tk.Checkbutton" not in source
    assert "ttk.Scale" not in source
    assert "colorchooser" not in source
    assert "def open_settings(" not in source
    assert "next_story_button" not in source
    assert "read_story_button" not in source


def test_voice_settings_remain_available_without_a_dialog() -> None:
    face_path = Path(__file__).resolve().parents[2] / "src" / "desk_robot" / "face.py"
    source = face_path.read_text(encoding="utf-8")

    assert "def _handle_settings_command(" in source
    assert 'text="SAY “HEY DEBO” TO TALK · SAY “HELP” FOR VOICE COMMANDS"' in source
