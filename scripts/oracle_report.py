"""Report of phase B: the strategy oracle against the best fixed hybrid and the best of chance.

    python scripts/oracle_report.py --best hybrid_h2:2 [--seed 1000]
        # -> results/exploration/combined/oracle_s<seed>.md

Rule fixed before the run (docs/COMBINED_PREREGISTRATION.md, section 0): the full phase B
and phase C follow only if, in at least 4 of the 14 cells, the oracle beats the best fixed
hybrid of phase A by more than 3 % (travel time or waiting time) and beats, on the same
metric, the best of K = 3 random schedules (K = the modes the oracle tries in each window)
by more than 3 %. Everything is on COOP-FULL training run 1, the only one the quick oracle
uses. The oracle minimises, window by window, the waiting of the vehicles + 10 x the time
emergency vehicles spend stopped + the waiting of the pedestrians.

Also reported: the best of the three fixed modes of the cell (COOP-FULL with EV-RULE, EV-RULE-MP,
the hybrid), a stricter reference than the hybrid alone; the oracle's windows per mode; and
whether the final episode followed the planned trajectory.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hybrid_rank import md  # noqa: E402

from cotraffic.paths import RESULTS_DIR  # noqa: E402

OUT = RESULTS_DIR / "exploration" / "combined"
METRICS = {"mean_travel_time": "trajet", "mean_waiting_time": "attente"}
MARGIN = 3.0


def load(seed: int) -> pd.DataFrame:
    rows = [pd.read_csv(p).iloc[0].to_dict() for p in sorted((OUT / "raw").glob(f"*__s{seed}.csv"))]
    return pd.DataFrame(rows)


def pick(cell: pd.DataFrame, method: str, variant: str) -> pd.Series | None:
    sel = cell[(cell.method == method) & (cell.variant.astype(str) == variant)]
    return sel.iloc[0] if len(sel) else None


def gain(ref: float, value: float) -> float:
    return 100.0 * (ref - value) / ref  # positive = the oracle is better


def report(df: pd.DataFrame, best: str) -> tuple[list[dict], int]:
    method, param = best.split(":")
    prefix = "q" if method == "hybrid_h1" else "b"
    hybrid_variant = f"t1-{prefix}{float(param):g}"
    rows, passed = [], 0
    for (net, scen, dem), cell in df.groupby(["network", "scenario", "demand"]):
        oracle = pick(cell, "strategy_oracle", "t1")
        if oracle is None:
            continue
        hybrid = pick(cell, method, hybrid_variant)
        coop = pick(cell, "coop_full_evrule_switch", "t1")
        if coop is None:  # no emergency vehicle: identical by construction to COOP-FULL
            coop = pick(cell, "coop_full", "t1")
        evrule = pick(cell, "ev_rule_mp", "ev_rule_mp")
        placebo = cell[cell.method == "strategy_placebo"]
        line = {"cellule": f"{net} {scen} {dem}"}
        ok = False
        for m, name in METRICS.items():
            o = float(oracle[m])
            modes = (("coop", coop), ("mp", evrule), ("hybride", hybrid))
            fixed = {k: float(r[m]) for k, r in modes if r is not None}
            chance = float(placebo[m].min()) if len(placebo) else np.nan
            g_h = gain(fixed["hybride"], o) if "hybride" in fixed else np.nan
            g_r = gain(chance, o)
            g_c = gain(min(fixed.values()), o)
            line[f"{name} oracle (s)"] = round(o, 1)
            line[f"{name} gain vs hybride (%)"] = round(g_h, 2)
            line[f"{name} gain vs meilleur du hasard (%)"] = round(g_r, 2)
            line[f"{name} gain vs meilleur mode fixe (%)"] = round(g_c, 2)
            ok = ok or (g_h > MARGIN and g_r > MARGIN)
        line["critère"] = "oui" if ok else "non"
        line["fenêtres coop/mp/mix"] = " / ".join(
            f"{float(oracle.get(f'windows_{k}', 0)):.2f}" for k in ("coop", "mp", "mix")
        )
        line["rejeu = plan"] = bool(oracle.get("plan_matches_replay", False))
        line["retard ambulances oracle / hybride (s)"] = (
            f"{oracle['ev_delay']:.1f} / {hybrid['ev_delay']:.1f}"
            if pd.notna(oracle.get("ev_delay")) and hybrid is not None
            else "–"
        )
        passed += ok
        rows.append(line)
    return rows, passed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--best", required=True, help="best fixed hybrid: hybrid_h2:<beta>, ...")
    parser.add_argument("--seed", type=int, default=1000)
    args = parser.parse_args()
    rows, passed = report(load(args.seed), args.best)
    verdict = "continuer (phase B complète, puis C)" if passed >= 4 else "s'arrêter (phase D)"
    lines = [f"# Phase B rapide : oracle de stratégie, graine {args.seed}, modèle t1", "",
             __doc__.split("\n\n", 2)[1].strip(), "",
             f"Meilleur hybride fixe : `{args.best}`. Cases qui remplissent le critère : "
             f"**{passed} sur {len(rows)}** (seuil : 4). Décision fixée à l'avance : "
             f"**{verdict}**.", "", md(pd.DataFrame(rows))]  # fmt: skip
    path = OUT / f"oracle_s{args.seed}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    pd.DataFrame(rows).to_csv(OUT / f"oracle_s{args.seed}.csv", index=False)
    print(f"{passed} / {len(rows)} cells -> {verdict}\n{path}")


if __name__ == "__main__":
    main()
