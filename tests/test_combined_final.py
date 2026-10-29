"""The final evaluation of the combined study: its plan and its analysis (no episode run)."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import combined_analysis as ca  # noqa: E402
import combined_final as cf  # noqa: E402

from cotraffic.paths import RESULTS_DIR  # noqa: E402
from cotraffic.seeds import TEST_SEEDS  # noqa: E402


def test_the_plan_is_the_preregistered_one():
    plain, llm = cf.tasks()
    assert len(plain) == 1260 and len(llm) == 5  # preregistration, section 10
    assert not [t for t in plain if t[0] == "hybrid_h3" and (t[1] == "grid8x8" or t[2] in (
        "sensor_noise", "comm_dropout_30", "buses"))]  # fmt: skip
    assert {t[4] for t in plain + llm} == {0, 1, 2, 3, 4} <= set(TEST_SEEDS)
    assert len({cf.ce.rid_of(t) for t in plain + llm}) == len(plain) + len(llm)
    assert cf.OUT == RESULTS_DIR / "combined" and "raw" not in cf.OUT.parts[-1:]
    emergency = {m for m, _, _ in cf.controllers("grid4x4", "emergency")}
    normal = {m for m, _, _ in cf.controllers("grid4x4", "normal")}
    pedestrians = {m for m, _, _ in cf.controllers("grid4x4", "pedestrians")}
    assert {"coop_full_evrule_switch", "ev_rule_mp", "team_rules"} <= emergency
    assert normal == {"hybrid_h2", "hybrid_h1", "hybrid_h3", "coop_full", "mp"}
    assert {"coop_full_pedrule_switch", "ped_rule_mp", "team_rules"} <= pedestrians
    assert all(t[0] == "hybrid_h2_llm" and t[1:4] == cf.LLM_CELL and t[5] == 1 for t in llm)


def test_gain_is_paired_by_training_run_against_coop_full():
    ref = pd.DataFrame([[100.0, 110.0], [120.0, 130.0], [90.0, 95.0]], index=[1, 2, 3])
    point, draws = ca.gain_draws(ref * 0.95, ref, np.random.default_rng(0))
    assert point == 5.0 and np.allclose(draws, 5.0)  # 5 % better on every pair: no spread
    one = pd.DataFrame([[100.0, 110.0]], index=[0])  # a baseline: one row
    point, draws = ca.gain_draws(ref, one, np.random.default_rng(0))
    assert round(point, 2) == round(100 * (105 - ref.to_numpy().mean()) / 105, 2)
    assert draws.size == ca.N_BOOT


def test_controllers_identical_by_construction_take_the_rows_they_reduce_to():
    assert ca.reduces_to("ev_rule_mp", "normal") == "mp"
    assert ca.reduces_to("team_rules", "incident") == "mp"
    assert ca.reduces_to("team_rules", "pedestrians") == "team_rules"
    assert ca.reduces_to("coop_full_pedrule_switch", "emergency") == "coop_full_evrule_switch"
    assert ca.reduces_to("coop_full_evrule_switch", "buses") == "coop_full"
