"""Data of the dashboard pages on the combined study (frontend/public/data/combined/).

    python scripts/dashboard_combined.py

Every number those pages show is computed here from the result files, with the functions
of combined_analysis.py (frozen with the preregistration) and of combined_figures.py:

* ``study.json``: the protocol and the size of the final evaluation (the rigour banner);
* ``cells.json``: per situation, controller and measure, the mean and its 95 % interval
  (bootstrap over the training runs and the test seeds);
* ``tests.json``: every test of the frozen analysis (families hybrid, hybrid-sup,
  hybrid-ablation), with the means, the interval, the Holm p-value and the verdict;
* ``layers.json``: the ablation of the layers (COOP-FULL -> V1 -> H2 -> H3), no test;
* ``validation.json``: the ranking of the variants on the validation seeds 1000-1002,
  where the candidate was chosen (before any test seed);
* ``bilan.json``: the candidate against each reference (exploratory, without Holm);
* ``bigcity.json``: the stopped big-city attempts (docs/FAILURES.md, F-016), validation
  seed 1000 only, never evaluation results.

The pages only translate codes and format numbers; they write no number of their own.
"""

from __future__ import annotations

import json
import re
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import combined_analysis as ca  # noqa: E402
import combined_figures as cf  # noqa: E402

from cotraffic import config  # noqa: E402
from cotraffic.analysis.stats import crossed_bootstrap_ci  # noqa: E402
from cotraffic.paths import REPO_ROOT, RESULTS_DIR  # noqa: E402

OUT = REPO_ROOT / "frontend" / "public" / "data" / "combined"
FINAL = RESULTS_DIR / "combined"
VALIDATION = RESULTS_DIR / "exploration" / "combined"
BIGCITY = RESULTS_DIR / "bigcity"
PREREG = "2c0dd1d"  # docs/COMBINED_PREREGISTRATION.md, frozen; every final row carries it

# (dashboard code, method, parameter) of every controller of the final evaluation
CONTROLLERS = [
    ("hybrid_h2", "hybrid_h2", 4.0),
    ("mp", "mp", None),
    ("ev_rule_mp", "ev_rule_mp", None),
    ("coop_full", "coop_full", None),
    ("team_rules", "team_rules", None),  # our teammate's work (controllers/llm_team/PROVENANCE.md)
    ("ped_rule_mp", "ped_rule_mp", None),
    ("hybrid_h1", "hybrid_h1", 90.0),
    ("hybrid_h3", "hybrid_h3", 90.0),
    ("coop_full_evrule_switch", "coop_full_evrule_switch", None),
    ("coop_full_pedrule_switch", "coop_full_pedrule_switch", None),
]
METRICS = {
    "mean_travel_time": "travel",
    "mean_waiting_time": "waiting",
    "ev_delay": "ambulances",
    "ped_mean_waiting_time": "pedestrians",
}
VARIANTS = {label: code for (code, _), label in
            zip(ca.LABELS, ca.LABELS.values(), strict=True)}  # fmt: skip
VERDICTS = {
    "non inférieure (démontré)": "noninf",
    "vraie perte": "loss",
    "vraie perte (au-delà de −2 %)": "lossBeyond",
    "intervalle trop large pour conclure": "wide",
    "meilleure (démontré)": "best",
    "supériorité non démontrée": "notSup",
}


def write(name: str, data) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=1, ensure_ascii=False, allow_nan=False)
    (OUT / f"{name}.json").write_text(text + "\n", encoding="utf-8")
    print(OUT / f"{name}.json")


def split(case: str) -> dict:
    network, scenario, demand = case.split()
    return {"network": network, "scenario": scenario, "demand": demand}


def r(v, digits: int = 2):
    return None if v is None or not np.isfinite(v) else round(float(v), digits)


# ---------------------------------------------------------------- study
def study(df: pd.DataFrame, tests: pd.DataFrame) -> dict:
    protocol = config.load_protocol()
    commits = sorted(df.git_commit.astype(str).unique())
    ranks = [pd.read_csv(VALIDATION / f"rank_s{s}.csv") for s in (1000, 1001, 1002)]
    main = tests[tests.famille == "hybrid"]
    return {
        "source": f"results/combined/raw ({len(df)} rows), analysis_tests.csv, "
        "configs/protocol.yaml, results/exploration/combined/rank_s100*.csv",
        "prereg": PREREG,
        "commits": commits,
        "episodes": int(len(df)),
        "episodeMinutes": round(
            sum(protocol["evaluation"][k] for k in ("warmup_s", "measure_s", "cooldown_s")) / 60
        ),
        "testSeeds": sorted(int(s) for s in df.seed.unique()),
        "models": int(df.run.dropna().nunique()),
        "situations": int(df.groupby(["network", "scenario", "demand"]).ngroups),
        "tests": int(len(main)),
        "marginPct": ca.MARGIN,
        "alpha": ca.ALPHA,
        "bootstrapDraws": ca.N_BOOT,
        "validationSeeds": [1000, 1001, 1002],
        "variantsTried": int(max(len(t) for t in ranks)),
        "perturbations": perturbations(),
        "candidate": {
            "beta": ca.CANDIDATE[1],
            "decisionS": int(protocol["timing"]["delta_time"]),
            "evRangeM": int(protocol["baselines"]["ev_preemption_range_m"]),
            "minGreenS": int(protocol["timing"]["min_green"]),
            "maxRedS": int(protocol["timing"]["max_red"]),
        },
    }


def perturbations() -> dict:
    """The perturbations of the robustness cells and the generalisation network, read from
    their configs (the page describes them with these numbers)."""
    import combined_eval as ce

    noise = config.load("scenarios", "sensor_noise")["sensor_noise"]
    dropout = config.load("scenarios", "comm_dropout_30")["comm_dropout"]
    buses = config.load("scenarios", "buses")["buses"]

    def lights(network: str) -> int:
        grid = config.load("networks", network)["grid"]
        return int(grid["x"] * grid["y"])

    return {
        "sensorNoise": {
            "countStdVeh": float(noise["count_std_veh"]),
            "failedPct": round(100 * float(noise["failed_fraction"])),
        },
        "commDropout": {"lossPct": round(100 * float(dropout["p"])), "mode": dropout["mode"]},
        "buses": {"periodMin": round(float(buses["period_s"]) / 60)},
        "generalisation": {
            network: {"trainedOn": trained, "lights": lights(network),
                      "trainedLights": lights(trained)}
            for network, trained in ce.TRAINED_ON.items()
        },
    }  # fmt: skip


# ---------------------------------------------------------------- cells
def played(cell: pd.DataFrame, method: str, scenario: str) -> str | None:
    """None if the controller was played in the cell, else what it is by construction."""
    if (cell.method == method).any():
        return None
    same = ca.reduces_to(method, scenario)
    return same if same != method else "absent"


def cells(df: pd.DataFrame) -> list[dict]:
    out = []
    groups = {k: g for k, g in df.groupby(["network", "scenario", "demand"])}
    for case in cf.ORDER:
        key = tuple(case.split())
        cell = groups[key]
        scenario = key[1]
        metrics = ["mean_travel_time", "mean_waiting_time"]
        metrics += ["ev_delay"] if scenario == "emergency" else []
        metrics += ["ped_mean_waiting_time"] if scenario == "pedestrians" else []
        rows = []
        for code, method, param in CONTROLLERS:
            same = played(cell, method, scenario)
            if same == "absent":
                continue
            values = {}
            for metric in metrics:
                t = ca.table(cell, method, param, metric).to_numpy()
                if not t.size or np.isnan(t).all():
                    continue
                mean, lo, hi = crossed_bootstrap_ci(t)
                values[METRICS[metric]] = {"mean": r(mean), "low": r(lo), "high": r(hi),
                                           "n": int(np.isfinite(t).sum())}  # fmt: skip
            rows.append({"controller": code, "sameAs": same, "values": values})
        out.append({**split(case), "controllers": rows})
    return out


# ---------------------------------------------------------------- tests
def all_tests(tests: pd.DataFrame) -> list[dict]:
    sup = tests[tests.famille == "hybrid-sup"].set_index(["case", "métrique"])
    out = []
    for row in tests.to_dict("records"):
        verdict = VERDICTS[row["verdict"]]
        key = (row["case"], row["métrique"])
        item = {
            "family": row["famille"],
            "variant": VARIANTS[row["variante"]],
            **split(row["case"]),
            "metric": "travel" if row["métrique"] == "trajet" else "waiting",
            "reference": row["référence"],
            "referenceMean": r(row["moyenne référence"]),
            "variantMean": r(row["moyenne variante"]),
            "gain": r(row["gain (%)"]),
            "low": r(row["IC bas"]),
            "high": r(row["IC haut"]),
            "pHolm": r(row["p Holm"], 5),
            "cliff": r(row["Cliff"], 3),
            "n": row["n"],
            "verdict": verdict,
        }
        if row["famille"] == "hybrid":  # the verdict of the forest plot
            superior = VERDICTS[sup.loc[key, "verdict"]] == "best"
            item["pHolmSup"] = r(sup.loc[key, "p Holm"], 5)
            item["verdict"] = "best" if superior else verdict
        out.append(item)
    return out


# ---------------------------------------------------------------- layers
LAYERS = [("coop_full", "coop_full", None),
          ("coop_full_evrule_switch", "coop_full_evrule_switch", None),
          ("hybrid_h2", "hybrid_h2", 4.0), ("hybrid_h3", "hybrid_h3", 90.0)]  # fmt: skip


def layers(df: pd.DataFrame) -> list[dict]:
    """The same means as the section "Ablation des couches" of analysis.md."""
    groups = {k: g for k, g in df.groupby(["network", "scenario", "demand"])}
    out = []
    for case in cf.ORDER:
        cell = groups[tuple(case.split())]
        line = {**split(case), "layers": []}
        for code, method, param in LAYERS:
            values = {}
            for metric in ("mean_travel_time", "mean_waiting_time"):
                base = float(np.nanmean(ca.table(cell, "coop_full", None, metric).to_numpy()))
                t = ca.table(cell, method, param, metric).to_numpy()
                v = float(np.nanmean(t)) if t.size else np.nan
                gain = r(100 * (base - v) / base, 1)
                values[METRICS[metric]] = {"mean": r(v, 1), "gainVsCoopFull": gain}
            line["layers"].append({"layer": code, "values": values})
        out.append(line)
    return out


# ---------------------------------------------------------------- validation
CODE_PATTERNS = [
    (r"^H3 : H2 β = 4, MP partout si file d'entrée > quantile (\d+) %", "hybrid_h3", "q"),
    (r"^H2 : COOP-FULL \+ biais MP β = (\d+)", "hybrid_h2", "beta"),
    (r"^H1 : COOP-FULL / MP selon la congestion, quantile (\d+) %", "hybrid_h1", "q"),
    (r"^COOP-FULL \+ EV-RULE \+ PED-RULE", "coop_full_pedrule_switch", None),
    (r"^COOP-FULL \+ EV-RULE \+ ses règles piétons", "coop_full_teamped_switch", None),
    (r"^V1 : COOP-FULL \+ EV-RULE", "coop_full_evrule_switch", None),
    (r"^COOP-FULL seul", "coop_full", None),
]


def variant_code(label: str) -> dict:
    for pattern, code, param in CODE_PATTERNS:
        m = re.match(pattern, label)
        if m:
            value = float(m.group(1)) if param else None
            return {"variant": code, "param": param, "value": value}
    raise ValueError(f"unknown variant: {label}")


def validation() -> dict:
    seeds = []
    for seed in (1000, 1001, 1002):
        t = pd.read_csv(VALIDATION / f"rank_s{seed}.csv")
        seeds.append({
            "seed": seed,
            "rows": [{**variant_code(row["variant"]), "rank": int(row["rank"]),
                      "label": row["variant"], "cells": int(row["cells"]),
                      "betterOrEqual": int(row["better_or_equal"]),
                      "uncertain": int(row["uncertain"]), "worse": int(row["worse"]),
                      "evDelay": r(row["ev_delay"]), "pedWait": r(row["ped_wait"])}
                     for row in t.to_dict("records")],
        })  # fmt: skip
    return {"source": "results/exploration/combined/rank_s1000.csv, rank_s1001.csv, "
            "rank_s1002.csv (rules: docs/COMBINED_PREREGISTRATION.md, section 0)",
            "seeds": seeds}  # fmt: skip


# ---------------------------------------------------------------- bilan
BILAN = {"meilleure": "better", "pas d'écart démontré": "same",
         "moins bonne, de moins de 2 %": "worseSmall",
         "moins bonne, de 2 % ou plus": "worseLarge"}  # fmt: skip
REF_CODES = {"MP": "mp", "EV-RULE-MP": "ev_rule_mp", "COOP-FULL": "coop_full",
             "TEAM-RULES": "team_rules", "PED-RULE-MP": "ped_rule_mp"}  # fmt: skip
CRITERIA = {"trajet": "travel", "attente": "waiting", "ambulances": "ambulances",
            "piétons": "pedestrians"}  # fmt: skip


def bilan() -> dict:
    summary = pd.read_csv(FINAL / "bilan_references.csv")
    detail = pd.read_csv(FINAL / "bilan_detail.csv")
    return {
        "source": "results/combined/bilan_references.csv, bilan_detail.csv "
        "(scripts/combined_figures.py)",
        "references": [{"reference": REF_CODES[row["référence"]],
                        **{BILAN[k]: int(row[k]) for k in BILAN}, "criteria": int(row["critères"])}
                       for row in summary.to_dict("records")],
        "detail": [{"reference": REF_CODES[row["référence"]], **split(row["case"]),
                    "criterion": CRITERIA[row["critère"]], "gain": r(row["gain (%)"]),
                    "low": r(row["IC bas"]), "high": r(row["IC haut"]),
                    "verdict": BILAN[row["verdict (IC à 95 %)"]]}
                   for row in detail.to_dict("records")],
    }  # fmt: skip


# ---------------------------------------------------------------- big city (F-016)
def bigcity() -> dict:
    cities = []
    for name in ("barcelona", "paris"):
        lights = json.loads((BIGCITY / f"{name}_lights.json").read_text(encoding="utf-8"))
        cities.append({"network": name, "lights": lights["lights"], "driven": lights["driven"],
                       "drivenLightsPct": lights["driven_share_lights_pct"],
                       "drivenLanesPct": lights["driven_share_lanes_pct"],
                       "wideLights": lights["wide_lights"]})  # fmt: skip
    sweep = pd.read_csv(BIGCITY / "calibration" / "sweep.csv")
    method = sweep.run_id.str.extract(r"^(\w+?)(?:-x[\d.]+)?__", expand=False)
    return {
        "source": "results/bigcity/*_lights.json, results/bigcity/calibration/sweep.csv "
        "(scripts/bigcity.py; docs/FAILURES.md, F-016)",
        "status": "stopped",
        "seed": 1000,
        "cities": cities,
        "parisSweep": [{"controller": m, "vehPerH": int(row["veh_per_h"]),
                        "waiting": r(row["mean_waiting_time"], 1),
                        "travel": r(row["mean_travel_time"], 1),
                        "teleports": int(row["teleports_total"]),
                        "unfinished": int(row["unfinished"])}
                       for m, row in zip(method, sweep.to_dict("records"), strict=True)],
    }  # fmt: skip


# ---------------------------------------------------------------- the LLM in the loop
LLM_LOOP = RESULTS_DIR / "llm_loop"
LLM_METRICS = {"mean_travel_time": "travel", "mean_waiting_time": "waiting",
               "ev_delay": "ambulances"}  # fmt: skip


def _rows(folder: Path, pattern: str = "*.csv") -> pd.DataFrame:
    files = sorted(folder.glob(pattern))
    if not files:
        return pd.DataFrame()
    return pd.DataFrame([pd.read_csv(f).iloc[0].to_dict() for f in files])


def _paired(llm: pd.DataFrame, cand: pd.DataFrame, metric: str, rng) -> dict | None:
    """Gain of the LLM version over the candidate (percent, positive = better), paired on the
    same cell and seed, with a bootstrap interval over the pairs."""
    keys = ["network", "scenario", "demand", "seed"]
    m = llm[keys + [metric]].merge(cand[keys + [metric]], on=keys, suffixes=("_llm", "_cand"))
    m = m.dropna()
    if m.empty:
        return None
    a, b = m[f"{metric}_llm"].to_numpy(float), m[f"{metric}_cand"].to_numpy(float)
    draws = rng.integers(0, len(a), size=(ca.N_BOOT, len(a)))
    boot = 100 * (b[draws].mean(1) - a[draws].mean(1)) / b[draws].mean(1)
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return {"gain": r(100 * (b.mean() - a.mean()) / b.mean()), "low": r(lo), "high": r(hi),
            "pairs": int(len(a))}  # fmt: skip


def llm_loop() -> dict | None:
    """The candidate with the LLM strategist (scripts/llm_loop.py), exploratory: against the
    candidate's own episodes (model t1), the strategy oracle and its placebo (validation)."""
    llm = _rows(LLM_LOOP / "raw")
    if llm.empty:
        return None
    rng = np.random.default_rng(0)
    explo = ca.load(VALIDATION / "raw")
    final = ca.load(FINAL / "raw")
    cand_v = explo[(explo.method == "hybrid_h2") & (explo.param == 4.0) & (explo.run == 1)]
    cand_t = final[(final.method == "hybrid_h2") & (final.param == 4.0) & (final.run == 1)]
    oracle = explo[explo.method == "strategy_oracle"]
    placebo = explo[explo.method == "strategy_placebo"]
    out: dict = {
        "source": "results/llm_loop/raw, calls (scripts/llm_loop.py); candidate t1: "
        "results/exploration/combined/raw (seed 1000), results/combined/raw (seeds 0-4); "
        "oracle and placebo: results/exploration/combined/raw (phase B)",
        "model": str(llm.llm_model.iloc[0]),
        "prompt": str(llm.prompt.iloc[0]),
        "windowS": float(llm.window_s.iloc[0]),
        "beta": float(llm.beta.iloc[0]),
        "episodes": int(len(llm)),
        "calls": int(llm.llm_calls.sum()),
        "validRate": r(float((llm.llm_valid_rate * llm.llm_calls).sum() / llm.llm_calls.sum()), 4),
        "latencyP50S": r(float(llm.llm_latency_p50_s.median())),
        "shares": {m: r(float(llm[f"llm_share_{m}"].mean()), 4)
                   for m in ("equilibre", "fluidite", "agent")},
        "validation": [],
        "test": [],
    }  # fmt: skip
    parts = (("validation", llm.seed >= 1000, cand_v), ("test", llm.seed < 1000, cand_t))
    for kind, sel, cand in parts:
        part = llm[sel]
        for (net, scen, dem), cell in part.groupby(["network", "scenario", "demand"]):
            c = cand[(cand.network == net) & (cand.scenario == scen) & (cand.demand == dem)]
            seeds = sorted(set(cell.seed) & set(c.seed))
            if not seeds:
                continue
            line = {**split(f"{net} {scen} {dem}"), "seeds": len(seeds),
                    "switches": r(float(cell.llm_mode_switches.mean()), 1),
                    "shares": {m: r(float(cell[f"llm_share_{m}"].mean()), 4)
                               for m in ("equilibre", "fluidite", "agent")}}  # fmt: skip
            for metric, name in LLM_METRICS.items():
                a = cell[cell.seed.isin(seeds)][metric].astype(float)
                b = c[c.seed.isin(seeds)][metric].astype(float)
                if a.isna().all():
                    continue
                entry = {"llm": r(a.mean()), "candidate": r(b.mean()),
                         "gain": r(100 * (b.mean() - a.mean()) / b.mean())}  # fmt: skip
                if kind == "validation":
                    o = oracle[(oracle.network == net) & (oracle.scenario == scen)
                               & (oracle.demand == dem)][metric]  # fmt: skip
                    pl = placebo[(placebo.network == net) & (placebo.scenario == scen)
                                 & (placebo.demand == dem)][metric]  # fmt: skip
                    entry["oracle"] = r(float(o.iloc[0])) if len(o) else None
                    entry["placeboBest"] = r(float(pl.min())) if len(pl) else None
                line[name] = entry
            out[kind].append(line)
    test = llm[llm.seed < 1000]
    out["testOverall"] = {name: _paired(test, cand_t, metric, rng)
                          for metric, name in LLM_METRICS.items()} if len(test) else {}  # fmt: skip
    # the episode where the model changed its mind most: its calls, one by one
    best = llm.sort_values(["llm_mode_switches", "seed"], ascending=[False, True]).iloc[0]
    calls = []
    log = LLM_LOOP / "calls" / f"{best.run_id}.jsonl"
    if log.is_file():
        for line in log.read_text(encoding="utf-8").splitlines():
            c = json.loads(line)
            halted = re.search(r"(\d+) halted", c["state"])
            backlog = re.search(r"enter the network: (\d+)", c["state"])
            calls.append({"time": c["time"], "appliesAt": r(c["applies_at"], 1),
                          "mode": c["mode"], "valid": bool(c["valid"]), "reason": c["reason"],
                          "latency": r(c["latency_s"], 1),
                          "halted": int(halted.group(1)) if halted else None,
                          "backlog": int(backlog.group(1)) if backlog else None})  # fmt: skip
    proto = config.load_protocol()["validation" if best.seed >= 1000 else "evaluation"]
    end = sum(float(proto[k]) for k in ("warmup_s", "measure_s", "cooldown_s"))
    out["timeline"] = {**split(f"{best.network} {best.scenario} {best.demand}"),
                       "seed": int(best.seed), "end": end, "calls": calls}  # fmt: skip
    # the earlier advisor (phase-level LLM bias), measured in the final evaluation
    adv = final[final.method == "hybrid_h2_llm"]
    if len(adv):
        base = cand_t[(cand_t.network == "grid4x4") & (cand_t.scenario == "emergency")
                      & (cand_t.demand == "peak")]  # fmt: skip
        out["advisor"] = {name: _paired(adv, base, metric, rng)
                          for metric, name in LLM_METRICS.items()}  # fmt: skip
    return out


# ---------------------------------------------------------------- large cities (demo)
CITY_METRICS = {"mean_travel_time": "travel", "mean_waiting_time": "waiting",
                "teleports_total": "teleports", "unfinished": "unfinished",
                "ev_delay": "ambulances"}  # fmt: skip


def city_map(network: str) -> dict:
    """The street network as polylines (metres, rounded) and its lights, for a small map."""
    import sumolib

    net = sumolib.net.readNet(str(REPO_ROOT / "sumo_files" / network / f"{network}.net.xml"))
    xmin, ymin, xmax, ymax = net.getBoundary()
    edges = [[round(c, 0) for xy in e.getShape() for c in (xy[0] - xmin, xy[1] - ymin)]
             for e in net.getEdges() if not e.isSpecial()]  # fmt: skip
    table = pd.read_csv(BIGCITY / f"{network}_lights.csv")
    driven = dict(zip(table.light.astype(str), table.driven, strict=True))
    lights = []
    for tls in net.getTrafficLights():
        ends = [c[0].getEdge().getToNode().getCoord() for c in tls.getConnections()]
        if ends:
            x = sum(e[0] for e in ends) / len(ends) - xmin
            y = sum(e[1] for e in ends) / len(ends) - ymin
            lights.append({"x": round(x), "y": round(y),
                           "driven": bool(driven.get(tls.getID(), False))})  # fmt: skip
    return {"width": round(xmax - xmin), "height": round(ymax - ymin), "edges": edges,
            "lights": lights}  # fmt: skip


def cities() -> dict | None:
    """Every controller on Paris and Barcelona at a demand the networks can carry
    (scripts/bigcity.py demo): exploratory, never part of the preregistered results."""
    rows = _rows(BIGCITY / "demo" / "raw")
    if rows.empty:
        return None
    lights = {c["network"]: c for c in bigcity()["cities"]}
    out = []
    for network, part in rows.groupby("network"):
        results = []
        for (method, scenario), cell in part.groupby(["method", "scenario"]):
            line = {"controller": method, "scenario": scenario, "n": int(len(cell))}
            for metric, name in CITY_METRICS.items():
                v = cell[metric].astype(float) if metric in cell else pd.Series(dtype=float)
                line[name] = r(float(v.mean())) if v.notna().any() else None
            results.append(line)
        llm = part[part.method == "hybrid_h2_llmstrat"]
        shares = ({m: r(float(llm[f"llm_share_{m}"].mean()), 4)
                   for m in ("equilibre", "fluidite", "agent")} if len(llm) else None)  # fmt: skip
        out.append({**lights[network], "scale": float(part.demand_scale.iloc[0]),
                    "seeds": sorted(int(x) for x in part.seed.unique()),
                    "vehPerH": r(float(part.vehicles.mean() / 1.0), 0),
                    "results": results, "llmShares": shares, "map": city_map(network)})  # fmt: skip
    return {"source": "results/bigcity/demo/raw (scripts/bigcity.py demo), "
            "sumo_files/<city>/<city>.net.xml, results/bigcity/*_lights.csv",
            "cities": out}  # fmt: skip


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    warnings.filterwarnings("ignore", category=RuntimeWarning)  # means of empty tables
    every = ca.load(FINAL / "raw")
    df = every[every.method != "hybrid_h2_llm"]  # the LLM variant has its own page
    tests = pd.read_csv(FINAL / "analysis_tests.csv")
    src = "results/combined/raw (preregistration 2c0dd1d, test seeds 0-4)"
    write("study", study(every, tests))
    write("cells", {"source": src, "cells": cells(df)})
    frozen = "results/combined/analysis_tests.csv (scripts/combined_analysis.py, frozen)"
    write("tests", {"source": frozen, "tests": all_tests(tests)})
    write("layers", {"source": src, "cells": layers(df)})
    write("validation", validation())
    write("bilan", bilan())
    write("bigcity", bigcity())
    loop = llm_loop()
    if loop is not None:
        write("llm_loop", loop)
    big = cities()
    if big is not None:
        write("cities", big)


if __name__ == "__main__":
    main()
