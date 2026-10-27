"""Markdown tables of the combined study (validation seed), from combined_summary.csv.

    python scripts/combined_tables.py      # -> results/exploration/combined/tables.md

Per network: travel time and waiting time of every method in every cell, with the gain
against Max-Pressure and against COOP-FULL (positive = better); then, in the emergency
cells, each emergency vehicle's delay and the travel time of the other vehicles.
"""

from __future__ import annotations

import pandas as pd

from cotraffic.paths import RESULTS_DIR

OUT = RESULTS_DIR / "exploration" / "combined"
NAMES = {
    "ft": "FT",
    "mp": "MP",
    "ev_rule_mp": "EV-RULE-MP",
    "coop_full": "COOP-FULL",
    "coop_full_llm": "COOP-FULL + conseiller",
    "team_rules": "TEAM-RULES",
    "team_qwen": "TEAM-QWEN",
}
CELLS = [(s, d) for s in ("normal", "emergency", "incident") for d in ("medium", "peak")]
LABEL = {"normal": "normal", "emergency": "urgences", "incident": "incident",
         "medium": "moy.", "peak": "pointe"}  # fmt: skip
METRICS = {
    "mean_travel_time": "Temps de trajet moyen (s)",
    "mean_waiting_time": "Attente moyenne (s)",
}


def num(x: float, sign: bool = False) -> str:
    if pd.isna(x):
        return "–"
    return (f"{x:+.1f}" if sign else f"{x:.1f}").replace(".", ",")


def tables(t: pd.DataFrame) -> list[str]:
    t = t[(t.method.isin(NAMES)) & (t.train_run <= 1)]
    out = []
    for net in ("grid4x4", "real_district"):
        for metric, title in METRICS.items():
            out += [f"\n### {net} : {title}", "",
                    "Entre parenthèses : gain contre MP / contre COOP-FULL, en %.", "",
                    "| Méthode | " + " | ".join(f"{LABEL[s]} {LABEL[d]}" for s, d in CELLS) + " |",
                    "|---|" + "---:|" * len(CELLS)]  # fmt: skip
            for m, name in NAMES.items():
                cells = []
                for s, d in CELLS:
                    r = t[
                        (t.network == net) & (t.scenario == s) & (t.demand == d) & (t.method == m)
                    ]
                    if r.empty:
                        cells.append("–")
                        continue
                    r = r.iloc[0]
                    gm = r.get(f"gain_{metric}_vs_mp_%")
                    gc = r.get(f"gain_{metric}_vs_coop_full_%")
                    cells.append(f"{num(r[metric])} ({num(gm, True)} / {num(gc, True)})")
                if any(c != "–" for c in cells):
                    out.append(f"| {name} | " + " | ".join(cells) + " |")
        out += [f"\n### {net} : urgences, retard de chaque ambulance", "",
                "| Cellule | Méthode | Ambulances | Retard moyen (s) | Retard de chacune (s) "
                "| Trajet des autres véhicules (s) |",
                "|---|---|---:|---:|---|---:|"]  # fmt: skip
        for d in ("medium", "peak"):
            for m, name in NAMES.items():
                r = t[(t.network == net) & (t.scenario == "emergency") & (t.demand == d)
                      & (t.method == m)]  # fmt: skip
                if r.empty:
                    continue
                r = r.iloc[0]
                each = r.get("ev_delays")
                each = (", ".join(e.split(":")[1].replace(".", ",") for e in each.split())
                        if isinstance(each, str) else "non enregistré")  # fmt: skip
                count = "–" if pd.isna(r.get("ev_count")) else f"{r['ev_count']:.0f}"
                out.append(f"| {LABEL[d]} | {name} | {count} | {num(r['ev_delay'])} | {each} "
                           f"| {num(r['others_travel_time'])} |")  # fmt: skip
    return out


def main() -> None:
    t = pd.read_csv(OUT / "combined_summary.csv")
    lines = ["# Étude combinée : graine de validation 1000", "",
             "Généré par scripts/combined_tables.py à partir de combined_summary.csv."]  # fmt: skip
    (OUT / "tables.md").write_text("\n".join(lines + tables(t)) + "\n", encoding="utf-8")
    print(OUT / "tables.md")


if __name__ == "__main__":
    main()
