"""Report of the guided COOP-FULL variants (A' bias, B' switch) on the validation seed.

    python scripts/combined_guides.py      # -> results/exploration/combined/guides.md

Emergency cells only (without an emergency vehicle a guided policy is COOP-FULL itself).
Every variant runs with the three COOP-FULL training runs; each run is paired with
COOP-FULL of the same run, and the same three emergency vehicles cross every episode of a
cell, so a variant has 3 paired waiting times and 9 paired vehicle delays per cell.

Reading rules, fixed before looking at the variants (validation seed, one demand draw):

* a delay difference of one vehicle counts only beyond 2 s;
* a cost to the other vehicles is "net" when the waiting time is worse in all three
  paired runs and worse by more than 1 % on average; "possible" when it is worse by more
  than 1 % on average with mixed signs; otherwise it is within the noise. The waiting time
  is that of all vehicles: the three emergency vehicles weigh less than 0.2 % of the mean.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from cotraffic.paths import RESULTS_DIR

OUT = RESULTS_DIR / "exploration" / "combined"
GUIDED = {
    "coop_full_team_bias": ("ses règles", "A′ biais"),
    "coop_full_team_switch": ("ses règles", "B′ commutation"),
    "coop_full_evrule_bias": ("EV-RULE", "A′ biais"),
    "coop_full_evrule_switch": ("EV-RULE", "B′ commutation"),
}
ORDER = [
    "coop_full_evrule_bias",
    "coop_full_evrule_switch",
    "coop_full_team_bias",
    "coop_full_team_switch",
]
REFERENCES = {"mp": "MP", "ev_rule_mp": "EV-RULE-MP", "team_rules": "TEAM-RULES"}
PROVENANCE = """\
Provenance des lignes :

* toutes les lignes lues sont dans `results/exploration/combined/raw/` ; les variantes guidées
  et COOP-FULL t2, t3 viennent de la relance au commit `4ca5f4b`, COOP-FULL t1 du lot 1 ;
* les 20 lignes du premier essai interrompu (commit `a11f878`) sont gardées à part dans
  `step4_first_try/` et ne servent qu'au contrôle de reproductibilité : identiques aux lignes
  de la relance sur toutes les métriques ;
* 96 lignes portent `4ca5f4b-dirty` : le seul fichier suivi modifié pendant leur calcul était
  `combined_summary.csv`, un fichier généré, réécrit à la fin de la première invocation ; le
  code (src, scripts, configs, tests) était exactement celui de `4ca5f4b`.
"""
DELTA_S, COST_PCT = 2.0, 1.0


def load() -> pd.DataFrame:
    rows = [pd.read_csv(p).iloc[0].to_dict() for p in sorted((OUT / "raw").glob("*.csv"))]
    df = pd.DataFrame(rows)
    df = df[df.scenario == "emergency"].copy()
    df["run"] = df.variant.str.extract(r"^t(\d+)", expand=False).astype(float)
    df["beta"] = pd.to_numeric(df.get("beta"), errors="coerce")
    n, k = df.vehicles.astype(float), df.ev_count.astype(float)
    df["others_travel_time"] = (n * df.mean_travel_time - k * df.ev_travel_time) / (n - k)
    return df


def delays(text) -> dict[str, float]:
    if not isinstance(text, str):
        return {}
    return {e.split(":")[0]: float(e.split(":")[1]) for e in text.split()}


def fmt(x: float, nd: int = 1, sign: bool = False) -> str:
    if pd.isna(x):
        return "–"
    return (f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}").replace(".", ",")


def variants(df: pd.DataFrame) -> list[dict]:
    out = []
    for (net, dem), cell in df.groupby(["network", "demand"]):
        coop = {int(r.run): r for r in cell[cell.method == "coop_full"].itertuples()}
        ref = {m: cell[cell.method == m].iloc[0] for m in REFERENCES if (cell.method == m).any()}
        keys = cell[cell.method.isin(GUIDED)][["method", "beta"]].drop_duplicates()
        keys = sorted(  # EV-RULE then the teammate's rules; bias by beta, then switch
            keys.itertuples(index=False, name=None),
            key=lambda k: (ORDER.index(k[0]), k[1] if pd.notna(k[1]) else np.inf),
        )
        for key in [("coop_full", np.nan), *keys]:
            method, beta = key
            sel = cell[(cell.method == method) & ((cell.beta == beta) | pd.isna(beta))]
            if method == "coop_full":
                sel = cell[cell.method == "coop_full"]
            runs = {int(r.run): r for r in sel.itertuples()}
            if not runs or not set(runs) <= set(coop):
                continue
            ev_pairs, wait_pairs, other_pairs, each = [], [], [], []
            for k, r in sorted(runs.items()):
                mine, base = delays(r.ev_delays), delays(coop[k].ev_delays)
                ev_pairs += [mine[v] - base[v] for v in mine if v in base]
                each.append("/".join(fmt(mine[v], 0) for v in sorted(mine)))
                w0 = float(coop[k].mean_waiting_time)
                wait_pairs.append(100 * (float(r.mean_waiting_time) - w0) / w0)
                o0 = float(coop[k].others_travel_time)
                other_pairs.append(100 * (float(r.others_travel_time) - o0) / o0)
            ev = np.array(ev_pairs)
            worse = sum(w > 0 for w in wait_pairs)
            mean_cost = float(np.mean(wait_pairs))
            if mean_cost > COST_PCT and worse == len(wait_pairs):
                cost = "net"
            elif mean_cost > COST_PCT:
                cost = "possible"
            else:
                cost = "bruit"
            name, mode = GUIDED.get(method, ("–", "COOP-FULL seul"))
            out.append(
                {
                    "network": net,
                    "demand": dem,
                    "guide": name,
                    "mode": mode,
                    "beta": beta,
                    "runs": len(runs),
                    "ev_mean": float(
                        np.mean(
                            [
                                delays(r.ev_delays)[v]
                                for r in runs.values()
                                for v in delays(r.ev_delays)
                            ]
                        )
                    ),  # fmt: skip
                    "ev_each": " · ".join(each),
                    "ev_better": int((ev < -DELTA_S).sum()),
                    "ev_worse": int((ev > DELTA_S).sum()),
                    "ev_pairs": len(ev),
                    "wait": float(np.mean([r.mean_waiting_time for r in runs.values()])),
                    "wait_pairs": wait_pairs,
                    "wait_cost": cost,
                    "others": float(np.mean([r.others_travel_time for r in runs.values()])),
                    "others_pct": float(np.mean(other_pairs)),
                    "guided": float(
                        np.mean([getattr(r, "guided_decisions", 0) or 0 for r in runs.values()])
                    ),  # fmt: skip
                    "changed": float(
                        np.mean([getattr(r, "changed_decisions", 0) or 0 for r in runs.values()])
                    ),  # fmt: skip
                    "refs": {m: float(r.ev_delay) for m, r in ref.items()},
                    "ref_wait": {m: float(r.mean_waiting_time) for m, r in ref.items()},
                }
            )
    return out


def label(v: dict) -> str:
    beta = f", β = {v['beta']:g}" if pd.notna(v["beta"]) else ""
    return f"{v['mode']}{beta}, {v['guide']}" if v["guide"] != "–" else v["mode"]


def report(rows: list[dict]) -> list[str]:
    lines = ["# Étape 4 : COOP-FULL guidé pendant les urgences (graine 1000)", "",
             __doc__.split("Reading rules", 1)[1].split("\n", 1)[1].strip(), "",
             PROVENANCE]  # fmt: skip
    for (net, dem), group in pd.DataFrame(rows).groupby(["network", "demand"], sort=False):
        refs = group.iloc[0]["refs"]
        ref_txt = ", ".join(f"{REFERENCES[m]} {fmt(x)} s" for m, x in refs.items())
        lines += [f"## {net}, urgences, demande {dem}", "",
                  f"Références (modèle unique) : {ref_txt}.", "",
                  "| Variante | Retard moyen (s) | Retard de chaque ambulance, run 1 · 2 · 3 (s) "
                  "| Ambulances mieux / pire (sur 9) | Attente (s) "
                  "| Attente, écart apparié par run (%) "
                  "| Coût voitures | Trajet des autres (s, écart %) | Décisions guidées "
                  "| Décisions changées |",
                  "|---|---:|---|---:|---:|---|---|---:|---:|---:|"]  # fmt: skip
        for v in group.to_dict("records"):
            pairs = " / ".join(fmt(p, 1, True) for p in v["wait_pairs"])
            better = f"{v['ev_better']} / {v['ev_worse']}" if v["guide"] != "–" else "–"
            cost = v["wait_cost"] if v["guide"] != "–" else "–"
            lines.append(
                f"| {label(v)} | {fmt(v['ev_mean'])} | {v['ev_each']} | {better} "
                f"| {fmt(v['wait'])} | {pairs if v['guide'] != '–' else '–'} | {cost} "
                f"| {fmt(v['others'])} ({fmt(v['others_pct'], 1, True)}) "
                f"| {fmt(v['guided'], 0)} | {fmt(v['changed'], 0)} |"
            )
        lines.append("")
    return lines


def main() -> None:
    rows = variants(load())
    (OUT / "guides.md").write_text("\n".join(report(rows)) + "\n", encoding="utf-8")
    pd.DataFrame(rows).drop(columns=["refs", "ref_wait"]).to_csv(OUT / "guides.csv", index=False)
    print(OUT / "guides.md")


if __name__ == "__main__":
    main()
