"""DEBO desktop companion package."""


def main() -> None:
    """Launch the animated, voice-first desktop application."""
    from desk_robot.face import main as face_main

    face_main()
