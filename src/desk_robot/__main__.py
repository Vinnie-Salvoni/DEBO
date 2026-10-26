"""Run DEBO's voice-first animated desktop application."""


def main() -> None:
    from desk_robot.face import main as face_main

    face_main()


if __name__ == "__main__":
    main()
