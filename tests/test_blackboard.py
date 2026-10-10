from agents.supervisor.blackboard import Blackboard, BlackboardMessage


def test_post_active_and_expiry():
    board = Blackboard()
    board.post(BlackboardMessage("incident", "operator", t=10.0, ttl_s=30.0,
                                 payload={"edge": "A1A0"}))
    assert len(board.active(10.0)) == 1
    assert len(board.active(39.9)) == 1
    assert board.active(40.0) == []


def test_of_kind_and_to_dict():
    board = Blackboard()
    board.post_message("ev_corridor", "emergency", 5.0, {"tls": ["A1"]}, ttl_s=60)
    board.post_message("incident", "operator", 5.0, {})
    corridors = board.of_kind("ev_corridor", 6.0)
    assert len(corridors) == 1
    record = corridors[0].to_dict()
    assert record["from"] == "emergency" and record["type"] == "ev_corridor"
    assert record["tls"] == ["A1"] and record["expires_at"] == 65.0


def test_clear():
    board = Blackboard()
    board.post_message("incident", "operator", 0.0)
    board.clear()
    assert board.active(1.0) == []
