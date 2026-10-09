"""Assistant: reading requests, looking up results, guarding the model's text.

No language model is needed: a fake Ollama server and fake model objects stand in for it,
including the ways it can fail.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from cotraffic.assistant import knowledge
from cotraffic.assistant.ask import Query, ask, complete, grounded, lookup, numbers_in, parse_rules
from cotraffic.assistant.llm import LLMUnavailableError, LocalLLM, validate
from cotraffic.assistant.scenario import DemoSpec, check, command, plan_demo
from cotraffic.assistant.scenario import parse_rules as parse_demo
from cotraffic.assistant.vocabulary import METHODS, find_all


def test_specific_names_win_over_general_ones():
    assert find_all("COOP-FULL contre MP", METHODS) == ["coop_full", "mp"]
    assert find_all("la préemption sur MP (EV-RULE-MP)", METHODS) == ["ev_rule_mp"]
    assert find_all("feux fixes ou actionnés", METHODS) == ["ft", "act"]


@pytest.mark.parametrize(
    ("question", "intent", "fields"),
    [
        (
            "Quel est le meilleur contrôleur à la pointe sur la grille ?",
            "best",
            {"network": "grid4x4", "demand": "peak"},
        ),
        (
            "Compare COOP et MP sur le quartier",
            "compare",
            {"network": "real_district", "methods": ["coop", "mp"]},
        ),
        (
            "Pourquoi COOP-FULL garde le vert au carrefour C1 à 10 min ?",
            "decision",
            {"junction": "C1", "time_s": 600.0, "methods": ["coop_full"]},
        ),
        ("Sur quoi COOP-FULL fonde ses décisions ?", "importance", {"methods": ["coop_full"]}),
        ("Explique F-014", "failure", {"failure_code": "F-014"}),
        ("Bonjour", "help", {}),
    ],
)
def test_keyword_reading(question, intent, fields):
    q, _ = parse_rules(question)
    assert q.intent == intent
    for name, value in fields.items():
        assert getattr(q, name) == value


def test_open_fields_take_the_reports_cells():
    q = complete(Query(intent="best", scenario="pedestrians"))
    assert (q.network, q.demand, q.metric) == ("grid4x4", "medium", "ped_mean_waiting_time")
    q = complete(Query(intent="best", scenario="emergency"))
    assert (q.demand, q.metric) == ("peak", "ev_delay")


def test_lookup_reads_the_result_files():
    finding = lookup(Query(intent="best", network="grid4x4", scenario="normal", demand="peak"))
    assert finding.found and finding.table.iloc[0]["méthode"] == "MP"
    assert "210,2" in finding.summary
    finding = lookup(
        Query(
            intent="compare",
            network="real_district",
            scenario="normal",
            demand="peak",
            methods=["coop"],
        )
    )
    assert "MP" in finding.summary and "Holm" in finding.summary
    missing = lookup(Query(intent="best", network="real_district", scenario="pedestrians"))
    assert not missing.found and "F-011" in missing.summary


def test_numbers_are_read_in_french_format():
    assert numbers_in("1 234,5 s et 12 véhicules") == [(1234.5, 1), (12.0, 0)]
    assert numbers_in("carrefour C1, F-014") == [(14.0, 0)]


def test_text_is_kept_only_when_its_numbers_come_from_the_facts():
    finding = knowledge.Finding(
        "MP 210,2 s", [knowledge.Fact("MP", 210.2, "s"), knowledge.Fact("IND", 217.5, "s")]
    )
    assert grounded("MP atteint 210,2 s, devant IND (217,5 s).", finding, "")
    assert grounded("MP atteint 210 s.", finding, "")  # rounded
    assert not grounded("MP atteint 198,4 s.", finding, "")  # invented
    assert grounded("Au carrefour C1 de la grille 4×4.", finding, "")


def test_schema_validation():
    schema = {
        "type": "object",
        "required": ["a"],
        "additionalProperties": False,
        "properties": {
            "a": {"type": "string", "enum": ["x", "y"]},
            "n": {"type": "integer", "minimum": 0},
        },
    }
    assert validate({"a": "x", "n": 3}, schema) == []
    assert validate({"a": "z"}, schema)
    assert validate({"n": 1}, schema)
    assert validate({"a": "x", "n": -1}, schema)
    assert validate({"a": "x", "b": 1}, schema)
    assert validate({"a": "x", "n": True}, schema)  # a boolean is not an integer


class FakeOllama(BaseHTTPRequestHandler):
    replies: list[str] = []
    requests: list[dict] = []

    def log_message(self, *args):  # keep the test output clean
        pass

    def _send(self, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._send({"models": [{"name": "qwen2.5:3b"}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeOllama.requests.append(body)
        self._send({"message": {"role": "assistant", "content": FakeOllama.replies.pop(0)}})


@pytest.fixture
def server():
    httpd = HTTPServer(("127.0.0.1", 0), FakeOllama)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    FakeOllama.replies, FakeOllama.requests = [], []
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def test_client_retries_with_the_reason_then_succeeds(server):
    llm = LocalLLM(url=server, model="qwen2.5:3b", timeout_s=5)
    assert llm.status()[0]
    schema = {"type": "object", "required": ["k"], "properties": {"k": {"enum": ["a", "b"]}}}
    FakeOllama.replies = ['{"k": "z"}', '{"k": "b"}']
    assert llm.chat_json([{"role": "user", "content": "?"}], schema) == {"k": "b"}
    second = FakeOllama.requests[1]
    assert second["format"] == schema and second["options"]["temperature"] == 0
    assert "Invalid answer" in second["messages"][-1]["content"]


def test_client_gives_up_on_bad_output_and_on_no_server(server):
    llm = LocalLLM(url=server, model="qwen2.5:3b", timeout_s=5)
    FakeOllama.replies = ["not json", "still not"]
    with pytest.raises(LLMUnavailableError):
        llm.chat_json([{"role": "user", "content": "?"}], {"type": "object"})
    down = LocalLLM(url="http://127.0.0.1:9", model="x", timeout_s=1)
    assert not down.status()[0]
    with pytest.raises(LLMUnavailableError):
        down.chat([{"role": "user", "content": "?"}])


class FakeModel:
    """Stands in for LocalLLM in ask() and plan_demo()."""

    def __init__(self, route=None, text="", fail=False):
        self.route, self.text, self.fail = route, text, fail

    def chat_json(self, messages, schema, attempts=2):
        if self.fail:
            raise LLMUnavailableError("down")
        problems = validate(self.route, schema)
        if problems:
            raise LLMUnavailableError("; ".join(problems))
        return self.route

    def chat(self, messages, schema=None, max_tokens=400):
        if self.fail:
            raise LLMUnavailableError("down")
        return self.text


ROUTE = {
    "intent": "best",
    "network": "grid4x4",
    "scenario": "normal",
    "demand": "peak",
    "metric": "mean_travel_time",
    "methods": [],
}


def test_answer_from_the_model_when_grounded():
    model = FakeModel(ROUTE, "À la pointe sur la grille, MP est le plus rapide avec 210,2 s.")
    reply = ask("Quel est le meilleur contrôleur à la pointe sur la grille ?", model)
    assert reply.written_by == "modèle local" and "210,2" in reply.text


def test_invented_number_falls_back_to_the_code_sentence():
    model = FakeModel(ROUTE, "MP est le plus rapide avec 180,0 s.")
    reply = ask("Quel est le meilleur contrôleur à la pointe sur la grille ?", model)
    assert reply.written_by == "code" and "210,2" in reply.text and "écarté" in reply.note


def test_model_down_still_answers():
    reply = ask("Quel est le meilleur contrôleur à la pointe sur la grille ?", FakeModel(fail=True))
    assert reply.read_by == "mots-clés" and "210,2" in reply.text


def test_model_reads_only_what_keywords_cannot():
    guess = dict(ROUTE, network="real_district", demand="low", scenario="emergency")
    reply = ask(
        "Dis-moi ce qui marche pour les véhicules prioritaires", FakeModel(guess, "x"), write=False
    )
    assert reply.read_by == "modèle local"
    # scenario read by the model; network and demand were not in the question: defaults
    assert (reply.query.scenario, reply.query.network, reply.query.demand) == (
        "emergency",
        "grid4x4",
        "peak",
    )


def test_bound_without_its_minus_sign_is_rejected():
    finding = knowledge.Finding(
        "COOP fait 3,9 % moins bien que MP. IC 95 % [−4,7 ; 15,8] %.",
        [
            knowledge.Fact("écart", 3.9, "%"),
            knowledge.Fact("borne basse", -4.7, "%", True),
            knowledge.Fact("borne haute", 15.8, "%", True),
        ],
    )
    assert grounded("COOP est 3,9 % plus lent ; intervalle de −4,7 à 15,8 %.", finding, "")
    assert not grounded("COOP est 3,9 % plus lent ; intervalle de 4,7 à 15,8 %.", finding, "")
    assert grounded("Voir F-014.", finding, "Explique F-014")


def test_numbers_in_words_are_checked_too():
    finding = lookup(
        Query(intent="best", network="grid4x4", scenario="sensor_noise", demand="peak")
    )
    assert grounded("IND est le meilleur des trois contrôleurs, avec 220,4 s.", finding, "")
    assert not grounded("IND est le meilleur des quatre contrôleurs.", finding, "")
    assert grounded("Sur la grille 4×4, IC 95 % : voir le tableau.", finding, "")


def test_explicit_words_override_the_models_reading():
    wrong = dict(ROUTE, network="grid8x8")
    reply = ask(
        "Meilleur contrôleur à la pointe sur le quartier ?", FakeModel(wrong, "x"), write=False
    )
    assert reply.query.network == "real_district"


def test_demo_request_with_accident_and_pedestrians():
    spec, _ = parse_demo(
        "MP contre COOP-FULL à Tunis avec un accident et des piétons, version courte"
    )
    notes = check(spec)
    assert (spec.left, spec.right, spec.network) == ("mp", "coop_full", "real_district_ped")
    assert (
        {"incident", "pedestrians"} <= set(spec.scenarios) and spec.follow_incident and spec.quick
    )
    assert notes and "real_district_ped" in notes[0]
    cmd = command(spec)
    assert "--follow-incident" in cmd and cmd[cmd.index("--net") + 1] == "real_district_ped"


def test_demo_request_is_made_runnable():
    spec = DemoSpec(left="coop_full", right="coop_full", network="grid8x8", scenarios=["buses"])
    check(spec)
    assert spec.left != spec.right
    spec = DemoSpec(right="coop_eco", network="real_district")
    notes = check(spec)
    assert spec.right == "coop_full" and any("coop_eco" in n for n in notes)


def test_demo_plan_asks_the_model_only_when_keywords_find_nothing():
    route = {
        "left": "ft",
        "right": "ind",
        "network": "grid4x4",
        "demand": "low",
        "scenarios": ["buses"],
        "follow_ev": False,
        "follow_incident": False,
        "quick": False,
    }
    plan = plan_demo("MP contre COOP à Tunis", FakeModel(route))
    assert plan.read_by == "mots-clés"
    assert (plan.spec.left, plan.spec.right, plan.spec.network) == ("mp", "coop", "real_district")
    plan = plan_demo("Fais-moi une belle démonstration", FakeModel(route))
    assert plan.read_by == "modèle local"
    assert (plan.spec.left, plan.spec.right, plan.spec.network) == ("ft", "ind", "grid4x4")
