
from desk_robot.behaviour import BehaviourEngine


def test_behaviour_engine_reacts_to_intent_and_clamps_state() -> None:
    engine = BehaviourEngine()
    greeting = engine.observe("greeting")
    assert greeting.reaction == "greeting"
    assert greeting.interactions == 1

    for _ in range(200):
        snapshot = engine.observe("unknown")

    assert snapshot.interactions == 201
    assert 0.0 <= snapshot.curiosity <= 1.0
    assert 0.0 <= snapshot.energy <= 1.0
    assert 0.0 <= snapshot.familiarity <= 1.0


def test_behaviour_engine_varies_repeated_curiosity_reactions() -> None:
    engine = BehaviourEngine()
    reactions = [engine.observe("unknown").reaction for _ in range(4)]
    assert "focused" in reactions
