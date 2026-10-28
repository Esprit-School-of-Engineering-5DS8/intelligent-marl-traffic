"""Ranking of every variant tried, with the rules of docs/COMBINED_PREREGISTRATION.md (section 0,
fixed before the results of phase A), on one validation seed.

    python scripts/hybrid_rank.py [--seed 1000]   # -> results/exploration/combined/rank_s<seed>.md

In each cell (network, scenario, demand) and for each metric (mean travel time, mean waiting
time), a variant run with the three COOP-FULL training runs is compared with the best
reference (MP, EV-RULE-MP, COOP-FULL mean of its 3 runs, TEAM-RULES; PED-RULE-MP too in the
pedestrian scenario). Gap = (variant - best) / best, positive = worse:

* better or equal: mean gap over the 3 runs <= 1 %;
* worse: mean gap > 3 %, or every run worse by more than 1 %;
* uncertain: otherwise.

A cell is "better or equal" when both metrics are, "worse" when one of them is. Ranking: most
"better or equal" cells, then fewest "worse", then emergency-vehicle delay, then pedestrian
waiting time. A variant not run in a cell where it is identical by construction (no
emergency vehicle: the EV pre-emption guides nothing; no pedestrian: the pedestrian guides
guide nothing) takes the rows of the variant it reduces to, and the cell is marked "=".
"""

from __future__ import annotations

import argparse
import re
import sys

import numpy as np
import pandas as pd

from cotraffic.paths import RESULTS_DIR

OUT = RESULTS_DIR / "exploration" / "combined"
METRICS = ("mean_travel_time", "mean_waiting_time")
NO_PARAM = -1.0
BETTER, UNCERTAIN, WORSE = "≥", "?", "✗"
REFS = ("mp", "ev_rule_mp", "coop_full", "team_rules", "ped_rule_mp")
# a variant -> what it reduces to where its guide has nothing to do: (scenario test, method)
REDUCES = {
    "coop_full_evrule_switch": [(lambda s: s != "emergency", "coop_full")],
    "coop_full_tped_switch": [
        (lambda s: s == "emergency", "coop_full_evrule_switch"),
        (lambda s: s in ("normal", "incident"), "coop_full"),
    ],
    "coop_full_pedrule_switch": [
        (lambda s: s == "emergency", "coop_full_evrule_switch"),
        (lambda s: s in ("normal", "incident"), "coop_full"),
    ],
}
LABELS = {
    "coop_full": "COOP-FULL seul",
    "coop_full_evrule_switch": "V1 : COOP-FULL + EV-RULE (commutation)",
    "coop_full_tped_switch": "COOP-FULL + EV-RULE + ses règles piétons (commutation)",
    "coop_full_pedrule_switch": "COOP-FULL + EV-RULE + PED-RULE (commutation)",
    "hybrid_h1": "H1 : COOP-FULL / MP selon la congestion, quantile {p:g} %, + EV-RULE",
    "hybrid_h2": "H2 : COOP-FULL + biais MP β = {p:g}, + EV-RULE",
    "hybrid_h3": "H3 : H2 β = 4, MP partout si file d'entrée > quantile {p:g} %, + EV-RULE",
}


def load(seed: int) -> pd.DataFrame:
    rows = [pd.read_csv(p).iloc[0].to_dict() for p in sorted((OUT / "raw").glob(f"*__s{seed}.csv"))]
    df = pd.DataFrame(rows)
    tag = df.variant.astype(str)
    df["run"] = tag.str.extract(r"^t(\d+)", expand=False).astype(float)
    param = tag.str.extract(r"-[bq]([\d.]+)$", expand=False)
    df["param"] = pd.to_numeric(param, errors="coerce").fillna(NO_PARAM)  # NaN != NaN in sets
    return df


def cells(df: pd.DataFrame) -> list[tuple[str, str, str]]:
    return sorted({(r.network, r.scenario, r.demand) for r in df.itertuples()})


def variant_rows(df, cell, method, param) -> tuple[pd.DataFrame, bool]:
    """Rows of a variant in a cell, or of what it reduces to there (second value True)."""
    net, scen, dem = cell
    in_cell = df[(df.network == net) & (df.scenario == scen) & (df.demand == dem)]
    sel = in_cell[in_cell.method == method]
    if param != NO_PARAM:
        sel = sel[sel.param == param]
    if len(sel) == 3:
        return sel, False
    for applies, other in REDUCES.get(method, []):
        if applies(scen):
            rows, _ = variant_rows(df, cell, other, NO_PARAM)
            return rows, True
    return sel, False


def best_reference(in_cell: pd.DataFrame, metric: str) -> tuple[float, str]:
    values = {}
    for m in REFS:
        rows = in_cell[in_cell.method == m][metric].dropna()
        if len(rows):
            values[m] = float(rows.mean())  # COOP-FULL: mean of its 3 runs
    best = min(values, key=values.get)
    return values[best], best


def classify(gaps: list[float]) -> str:
    mean = float(np.mean(gaps))
    if mean <= 1.0:
        return BETTER
    if mean > 3.0 or all(g > 1.0 for g in gaps):
        return WORSE
    return UNCERTAIN


def rank(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    keys = sorted(
        {(r.method, r.param) for r in df.itertuples() if r.method in LABELS},
        key=lambda k: (list(LABELS).index(k[0]), k[1]),
    )
    summary, detail = [], []
    for method, param in keys:
        verdicts, ev, ped = [], [], []
        for cell in cells(df):
            net, scen, dem = cell
            in_cell = df[(df.network == net) & (df.scenario == scen) & (df.demand == dem)]
            rows, reduced = variant_rows(df, cell, method, param)
            if len(rows) != 3:
                verdicts.append(None)
                continue
            per_metric = {}
            for metric in METRICS:
                best, ref = best_reference(in_cell, metric)
                gaps = [100.0 * (v - best) / best for v in rows[metric]]
                per_metric[metric] = (classify(gaps), float(np.mean(gaps)), ref)
            marks = [v[0] for v in per_metric.values()]
            verdict = WORSE if WORSE in marks else BETTER if marks == [BETTER] * 2 else UNCERTAIN
            verdicts.append(verdict)
            if scen == "emergency":
                ev.append(float(rows.ev_delay.mean()))
            if scen == "pedestrians" and "ped_mean_waiting_time" in rows:
                ped.append(float(rows.ped_mean_waiting_time.mean()))
            detail.append(
                {
                    "variant": LABELS[method].format(p=param),
                    "cell": f"{net} {scen} {dem}",
                    "verdict": verdict + ("=" if reduced else ""),
                    **{f"{m}_gap_%": round(per_metric[m][1], 2) for m in METRICS},
                    **{f"{m}_ref": per_metric[m][2] for m in METRICS},
                    **{
                        f"share_{s}": rows.get(f"share_{s}", pd.Series([np.nan])).mean()
                        for s in ("coop", "mp", "mix", "ped", "ev")
                    },  # fmt: skip
                }
            )
        known = [v for v in verdicts if v is not None]
        summary.append(
            {
                "variant": LABELS[method].format(p=param),
                "cells": len(known),
                "better_or_equal": known.count(BETTER),
                "uncertain": known.count(UNCERTAIN),
                "worse": known.count(WORSE),
                "ev_delay": round(float(np.mean(ev)), 2) if ev else np.nan,
                "ped_wait": round(float(np.mean(ped)), 2) if ped else np.nan,
            }
        )
    table = pd.DataFrame(summary)
    table["_ev"] = table.ev_delay.fillna(np.inf)
    table["_ped"] = table.ped_wait.fillna(np.inf)
    table = table.sort_values(
        ["better_or_equal", "worse", "_ev", "_ped"], ascending=[False, True, True, True]
    ).drop(columns=["_ev", "_ped"])
    table.insert(0, "rank", range(1, len(table) + 1))
    return table, pd.DataFrame(detail)


def md(df: pd.DataFrame) -> str:
    """A pipe table (no dependency on tabulate)."""

    def cell(x) -> str:
        if isinstance(x, float):
            return "–" if np.isnan(x) else f"{x:g}"
        return str(x)

    head = "| " + " | ".join(df.columns) + " |"
    sep = "|" + "---|" * len(df.columns)
    body = ["| " + " | ".join(cell(x) for x in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join([head, sep, *body])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=1000)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # the labels hold β; Windows consoles are cp1252
    table, detail = rank(load(args.seed))
    out = OUT / f"rank_s{args.seed}"
    table.to_csv(f"{out}.csv", index=False)
    detail.to_csv(f"{out}_cells.csv", index=False)
    lines = [f"# Classement des variantes, graine {args.seed}", "",
             "Règles : docs/COMBINED_PREREGISTRATION.md, section 0 (commit 7bd689e). "
             f"{BETTER} meilleure ou égale, {UNCERTAIN} incertaine, {WORSE} pire ; « = » : "
             "identique par construction à la variante qu'elle devient dans cette case.", "",
             md(table), "", "## Détail par case", "",
             md(detail)]  # fmt: skip
    (OUT / f"rank_s{args.seed}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(table.to_string(index=False))
    print(re.sub(r"\.md$", "", str(out)) + ".md")


if __name__ == "__main__":
    main()
