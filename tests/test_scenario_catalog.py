"""The options of the dashboard's "new scenario" form, and the API that checks a request."""

from __future__ import annotations

import pytest

from cotraffic import scenario_catalog as catalog
from cotraffic.controllers.registry import CANDIDATE, LLM_CANDIDATE
from cotraffic.paths import CHECKPOINTS_DIR

STUDY = ["act", "coop_full", "ev_rule_mp", "ft", "mp", "ped_rule_mp"]


def test_events_follow_the_network_configs():
    assert catalog.events("grid4x4") == list(catalog.EVENTS)
    assert catalog.pedestrians("grid8x8")
    # no sidewalks in the imports: no pedestrians (nor buses, nor incident location)
    assert catalog.events("paris") == ["emergency"]
    assert catalog.events("barcelona") == ["emergency"]
    # the district has sidewalks only in its _ped version
    assert "pedestrians" not in catalog.events("real_district")
    assert "pedestrians" in catalog.events("real_district_ped")


def test_candidate_and_llm_run_on_the_coop_full_model():
    for method in (CANDIDATE, LLM_CANDIDATE):
        assert (
            catalog.checkpoint(method, "grid8x8")
            == CHECKPOINTS_DIR / "coop_full" / "grid4x4" / "seed1.zip"
        )
        assert (
            catalog.checkpoint(method, "paris")
            == CHECKPOINTS_DIR / "coop_full" / "real_district" / "seed1.zip"
        )
    assert catalog.checkpoint("mp", "paris") is None


def test_big_cities_offer_the_controllers_of_their_demonstration():
    assert catalog.demand_scale("paris") < 1 and catalog.demand_scale("barcelona") < 1
    assert catalog.demand_scale("grid8x8") == 1
    offered = catalog.methods("paris", STUDY)
    assert set(offered) <= set(catalog.BIG_CITY_METHODS)
    assert "act" not in offered


@pytest.mark.skipif(not (CHECKPOINTS_DIR / "coop_full" / "grid4x4" / "seed1.zip").exists(),
                    reason="trained models not on disk")  # fmt: skip
def test_our_candidate_comes_first():
    offered = catalog.methods("grid4x4", STUDY)
    assert offered[:2] == [CANDIDATE, LLM_CANDIDATE]
    assert set(STUDY) <= set(offered)


def test_catalog_lists_every_network():
    c = catalog.catalog(STUDY)
    assert [n["network"] for n in c["networks"]] == list(catalog.NETWORKS)
    assert c["candidate"] == CANDIDATE and c["llm"] == LLM_CANDIDATE
    assert all(n["window"] > 0 for n in c["networks"])


@pytest.fixture
def api(monkeypatch):
    """create_run called directly (the queue is replaced: nothing is simulated)."""
    pytest.importorskip("fastapi")
    import api.main as main

    submitted: list[dict] = []
    monkeypatch.setattr(main.runs, "submit", lambda req: submitted.append(req) or {"id": "x"})
    monkeypatch.setattr(main, "known_methods", lambda: set(STUDY))
    monkeypatch.setattr(main, "ollama_up", lambda: True)

    def post(**changes) -> int:
        from fastapi import HTTPException
        from pydantic import ValidationError

        body = {"network": "grid4x4", "demand": "peak", "events": ["emergency", "pedestrians"],
                "seed": 3, "left": "mp", "right": "ft", **changes}  # fmt: skip
        try:
            main.create_run(main.ScenarioRequest(**body))
        except ValidationError:
            return 422
        except HTTPException as err:
            return err.status_code
        return 201

    return post, submitted


def test_api_accepts_the_new_networks(api):
    post, submitted = api
    assert post(network="grid8x8") == 201
    assert post(network="paris", events=["emergency"]) == 201
    assert [r["network"] for r in submitted] == ["grid8x8", "paris"]


def test_api_refuses_what_a_network_cannot_play(api):
    post, submitted = api
    assert post(network="paris") == 422  # pedestrians: no sidewalks in the import
    assert post(network="paris", events=[], left="act") == 422  # never run there
    assert post(network="atlantis") == 422
    assert submitted == []


def test_api_needs_ollama_for_the_llm(api, monkeypatch):
    post, _ = api
    import api.main as main

    if not catalog.available(LLM_CANDIDATE, "grid4x4"):
        pytest.skip("trained models not on disk")
    monkeypatch.setattr(main, "ollama_up", lambda: False)
    assert post(left=CANDIDATE, right=LLM_CANDIDATE) == 503
