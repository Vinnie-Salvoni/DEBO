from desk_robot.robot import DeskRobot


def test_robot_greets_user() -> None:
    robot = DeskRobot()

    response = robot.respond("hello")

    assert "Debo" in response
    assert "Hey!" in response


def test_robot_remembers_its_name() -> None:
    robot = DeskRobot(name="Pip")

    response = robot.respond("what is your name?")

    assert "Pip" in response


def test_robot_handles_empty_input() -> None:
    robot = DeskRobot()

    response = robot.respond("   ")

    assert "listening" in response.lower()
    assert robot.state.turns == 0


def test_robot_counts_nonempty_interactions() -> None:
    robot = DeskRobot()

    robot.respond("hello")
    robot.respond("how are you?")
    robot.respond("something unexpected")

    assert robot.state.turns == 3


def test_robot_handles_unknown_messages() -> None:
    robot = DeskRobot()

    response = robot.respond("I saw a strange bird today")

    assert "Tell me more" in response
