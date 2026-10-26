from desk_robot.robot import DeskRobot


def main() -> None:
    robot = DeskRobot()

    print("=" * 42)
    print(f"  {robot.state.name.upper()} - DESK ROBOT")
    print("  Your little companion is online.")
    print("  Type 'help' for ideas or 'exit' to quit.")
    print("=" * 42)

    while True:
        try:
            message = input("\nYou > ")

            if message.strip().lower() in {"exit", "quit", "bye", "goodbye"}:
                print(f"\n{robot.state.name} > {robot.respond(message)}")
                break

            response = robot.respond(message)
            print(f"\n{robot.state.name} > {response}")

        except KeyboardInterrupt, EOFError:
            print(f"\n{robot.state.name} is going to sleep. Bye!")
            break


if __name__ == "__main__":
    main()
