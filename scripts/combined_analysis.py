"""Analysis of the final evaluation of the combined study (preregistration, sections 8, 9).

    python scripts/combined_analysis.py [--raw results/combined/raw] [--out results/combined]

Gain = (reference - controller) / reference in percent, positive = better, on the mean
travel time and the mean waiting time. In each cell and for each metric the reference is
the best of MP, EV-RULE-MP, COOP-FULL, TEAM-RULES (and PED-RULE-MP with pedestrians) on the
test seeds. Pairing: by test seed, and also by training run when the reference is COOP-FULL
(the hybrids are built on the same three models). Two-way bootstrap (training runs and test
seeds resampled, 10 000 draws, seed 0), 95 % percentile interval; one-sided p of
non-inferiority = (1 + draws with gain <= -2 %) / (1 + draws), of superiority the same with 0.

Families (Holm within each, one-sided alpha 0.025):

* ``hybrid``: the candidate, non-inferiority, every cell and both metrics;
* ``hybrid-sup``: the candidate, superiority, the same comparisons;
* ``hybrid-ablation``: the other final variants, non-inferiority.

A variant is tested only in the cells where it differs by construction from the others (V1:
emergencies; PED-RULE: pedestrians). Also written: Mann-Whitney and Cliff's delta on the
episodes (variant against reference: negative = the variant lower, so better), the ablation
of the layers
(COOP-FULL, V1, H2, H3) and the LLM variant against the candidate (model t1, paired seeds).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hybrid_rank import md  # noqa: E402

from cotraffic.analysis.stats import (  # noqa: E402
    cliffs_delta,
    cliffs_magnitude,
    holm,
    mann_whitney_p,
)
from cotraffic.paths import RESULTS_DIR  # noqa: E402

METRICS = {"mean_travel_time": "trajet", "mean_waiting_time": "attente"}
MARGIN, ALPHA, N_BOOT = 2.0, 0.025, 10_000
REFS = ("mp", "ev_rule_mp", "coop_full", "team_rules", "ped_rule_mp")  # team_rules: teammate's work
CANDIDATE = ("hybrid_h2", 4.0)
OTHERS = [
    ("hybrid_h1", 90.0),
    ("hybrid_h3", 90.0),
    ("coop_full_pedrule_switch", None),
    ("coop_full_evrule_switch", None),
]
LABELS = {
    ("hybrid_h2", 4.0): "H2 β = 4 (candidate)",
    ("hybrid_h1", 90.0): "H1 q90",
    ("hybrid_h3", 90.0): "H3 q90",
    ("coop_full_pedrule_switch", None): "COOP-FULL + EV-RULE + PED-RULE",
    ("coop_full_evrule_switch", None): "V1 : COOP-FULL + EV-RULE",
}


def load(raw: Path) -> pd.DataFrame:
    df = pd.DataFrame([pd.read_csv(p).iloc[0].to_dict() for p in sorted(raw.glob("*.csv"))])
    tag = df.variant.astype(str)
    df["run"] = pd.to_numeric(tag.str.extract(r"^t(\d+)", expand=False), errors="coerce")
    df["param"] = pd.to_numeric(tag.str.extract(r"-[bq]([\d.]+)$", expand=False), errors="coerce")
    return df


def reduces_to(method: str, scenario: str) -> str:
    """What a controller is, by construction, in a cell where it was not played."""
    if method == "ev_rule_mp" and scenario != "emergency":
        return "mp"
    if method == "team_rules" and scenario not in ("emergency", "pedestrians"):
        return "mp"
    if method == "coop_full_evrule_switch" and scenario != "emergency":
        return "coop_full"
    if method == "coop_full_pedrule_switch" and scenario != "pedestrians":
        return "coop_full_evrule_switch" if scenario == "emergency" else "coop_full"
    return method


def table(cell: pd.DataFrame, method: str, param: float | None, metric: str) -> pd.DataFrame:
    """(training run x test seed) values of a controller in a cell; one row for a baseline."""
    scenario = cell.scenario.iloc[0]
    while True:
        sel = cell[cell.method == method]
        if param is not None:
            sel = sel[sel.param == param]
        if len(sel) or reduces_to(method, scenario) == method:
            break
        method, param = reduces_to(method, scenario), None
    runs = sel.run.fillna(0).astype(int)
    return sel.assign(run=runs).pivot_table(index="run", columns="seed", values=metric)


def gain_draws(cand: pd.DataFrame, ref: pd.DataFrame, rng) -> tuple[float, np.ndarray]:
    """Gain of ``cand`` over ``ref`` (percent, positive = better) and its bootstrap draws."""
    seeds = [s for s in cand.columns if s in ref.columns]
    paired_runs = len(ref) > 1  # COOP-FULL: the same models as the hybrids
    if paired_runs:
        runs = [r for r in cand.index if r in ref.index]
        cand, ref = cand.loc[runs, seeds], ref.loc[runs, seeds]
    else:
        cand, ref = cand[seeds], ref[seeds]
    c, r = cand.to_numpy(float), ref.to_numpy(float)
    if np.isnan(c).any() or np.isnan(r).any():
        raise ValueError("incomplete table: every training run and test seed must be there")
    rows = rng.multinomial(c.shape[0], np.full(c.shape[0], 1 / c.shape[0]), size=N_BOOT)
    cols = rng.multinomial(c.shape[1], np.full(c.shape[1], 1 / c.shape[1]), size=N_BOOT)
    norm = rows.sum(1) * cols.sum(1)
    cand_b = np.einsum("bi,ij,bj->b", rows, c, cols) / norm
    if paired_runs:
        ref_b = np.einsum("bi,ij,bj->b", rows, r, cols) / norm
    else:
        ref_b = cols @ r[0] / cols.sum(1)
    point = 100 * (r.mean() - c.mean()) / r.mean()
    return float(point), 100 * (ref_b - cand_b) / ref_b


def compare(df: pd.DataFrame, variants, family: str) -> list[dict]:
    rows = []
    for (net, scen, dem), cell in df.groupby(["network", "scenario", "demand"]):
        for metric, name in METRICS.items():
            means = {}
            for m in REFS:
                t = table(cell, m, None, metric)
                if t.size and not (m == "ped_rule_mp" and scen != "pedestrians"):
                    means[m] = float(np.nanmean(t.to_numpy()))
            ref = min(means, key=means.get)
            ref_t = table(cell, ref, None, metric)
            for method, param in variants:
                if reduces_to(method, scen) != method:
                    continue  # identical to another controller here: not a test of its own
                cand_t = table(cell, method, param, metric)
                if not cand_t.size:
                    continue
                rng = np.random.default_rng(0)
                point, draws = gain_draws(cand_t, ref_t, rng)
                lo, hi = np.percentile(draws, [2.5, 97.5])
                threshold = 0.0 if family == "hybrid-sup" else -MARGIN
                a, b = cand_t.to_numpy().ravel(), ref_t.to_numpy().ravel()
                rows.append(
                    {
                        "famille": family,
                        "variante": LABELS[(method, param)],
                        "case": f"{net} {scen} {dem}",
                        "métrique": name,
                        "référence": ref,
                        "moyenne référence": round(means[ref], 2),
                        "moyenne variante": round(float(a.mean()), 2),
                        "gain (%)": round(point, 2),
                        "IC bas": round(float(lo), 2),
                        "IC haut": round(float(hi), 2),
                        "p": (1 + int((draws <= threshold).sum())) / (1 + N_BOOT),
                        "p Mann-Whitney": mann_whitney_p(a, b),
                        "Cliff": round(cliffs_delta(a, b), 3),
                        "effet": cliffs_magnitude(cliffs_delta(a, b)),
                        "n": f"{cand_t.shape[0]}x{cand_t.shape[1]}",
                    }
                )
    return rows


def with_holm(rows: list[dict]) -> pd.DataFrame:
    out = pd.DataFrame(rows)
    out["p Holm"] = holm(out["p"].tolist())
    sup = out["famille"].eq("hybrid-sup")
    shown = out["p Holm"] < ALPHA
    # a failed non-inferiority: a true loss when the whole interval is below 0, else an
    # interval too wide to conclude (preregistration, section 9)
    loss = out["IC haut"] < 0
    beyond = out["IC haut"] < -MARGIN
    failed = np.where(
        loss,
        np.where(beyond, f"vraie perte (au-delà de −{MARGIN:g} %)", "vraie perte"),
        "intervalle trop large pour conclure",
    )
    out["verdict"] = np.where(
        sup,
        np.where(shown, "meilleure (démontré)", "supériorité non démontrée"),
        np.where(shown, "non inférieure (démontré)", failed),
    )
    return out


def one_sentence(main: pd.DataFrame, sup: pd.DataFrame) -> str:
    """What the final evaluation allows us to state, and what it does not."""
    shown = main.verdict == "non inférieure (démontré)"
    lost = main[main.verdict.str.startswith("vraie perte")]
    wide = int((main.verdict == "intervalle trop large pour conclure").sum())
    better = sup[sup.verdict == "meilleure (démontré)"]

    def where(d: pd.DataFrame) -> str:
        return ", ".join(f"{c} ({m})" for c, m in zip(d["case"], d["métrique"], strict=True))

    return (
        f"On peut affirmer que la candidate n'est pas moins bonne que la meilleure référence, "
        f"à {MARGIN:g} % près, dans {int(shown.sum())} comparaisons sur {len(main)}, et "
        f"qu'elle est meilleure dans {len(better)}" + (f" ({where(better)})" if len(better) else "")
        + f" ; on ne peut pas l'affirmer dans les {len(main) - int(shown.sum())} autres : "
        + (f"{len(lost)} vraie perte" if len(lost) == 1 else f"{len(lost)} vraies pertes")
        + (f" ({where(lost)})" if len(lost) else "")
        + f" et {wide} "
        + ("intervalle trop large" if wide == 1 else "intervalles trop larges")
        + " pour conclure."
    )  # fmt: skip


def ablation(df: pd.DataFrame) -> pd.DataFrame:
    """Mean of each layer per cell, and its gain over COOP-FULL (no test)."""
    layers = [
        ("COOP-FULL", "coop_full", None),
        ("+ préemption (V1)", "coop_full_evrule_switch", None),
        ("+ biais MP (H2 β = 4)", "hybrid_h2", 4.0),
        ("+ bascule sur saturation (H3)", "hybrid_h3", 90.0),
    ]
    rows = []
    for (net, scen, dem), cell in df.groupby(["network", "scenario", "demand"]):
        line = {"case": f"{net} {scen} {dem}"}
        for metric, name in METRICS.items():
            base = float(np.nanmean(table(cell, "coop_full", None, metric).to_numpy()))
            for label, m, p in layers:
                v = float(np.nanmean(table(cell, m, p, metric).to_numpy()))
                line[f"{name} {label}"] = (
                    round(v, 1)
                    if m == "coop_full"
                    else (f"{v:.1f} ({100 * (base - v) / base:+.1f} %)")
                )
        rows.append(line)
    return pd.DataFrame(rows)


def llm_variant(df: pd.DataFrame) -> pd.DataFrame:
    cell = df[(df.network == "grid4x4") & (df.scenario == "emergency") & (df.demand == "peak")]
    llm = cell[(cell.method == "hybrid_h2_llm") & (cell.param == 4.0)].set_index("seed")
    base = cell[(cell.method == "hybrid_h2") & (cell.param == 4.0) & (cell.run == 1)]
    base = base.set_index("seed")
    seeds = sorted(set(llm.index) & set(base.index))
    if not seeds:
        return pd.DataFrame()
    rows = []
    rng = np.random.default_rng(0)
    for metric in list(METRICS) + ["ev_delay"]:
        c, r = llm.loc[seeds, metric].to_numpy(float), base.loc[seeds, metric].to_numpy(float)
        cols = rng.multinomial(len(seeds), np.full(len(seeds), 1 / len(seeds)), size=N_BOOT)
        draws = 100 * (cols @ r - cols @ c) / (cols @ r)
        lo, hi = np.percentile(draws, [2.5, 97.5])
        rows.append(
            {
                "métrique": metric,
                "candidate seule": round(float(r.mean()), 2),
                "candidate + LLM": round(float(c.mean()), 2),
                "gain (%)": round(100 * (r.mean() - c.mean()) / r.mean(), 2),
                "IC bas": round(float(lo), 2),
                "IC haut": round(float(hi), 2),
                "graines": len(seeds),
            }
        )
    keys = [k for k in llm.columns if k.startswith("llm_") and llm[k].dtype != object]
    meta = {k: round(float(llm.loc[seeds, k].mean()), 3) for k in keys}
    return pd.DataFrame(rows).assign(**{"métriques LLM (moyenne)": str(meta)})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raw", type=Path, default=RESULTS_DIR / "combined" / "raw")
    parser.add_argument("--out", type=Path, default=RESULTS_DIR / "combined")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    df = load(args.raw)
    main_rows = with_holm(compare(df, [CANDIDATE], "hybrid"))
    sup = with_holm(compare(df, [CANDIDATE], "hybrid-sup"))
    abl = with_holm(compare(df, OTHERS, "hybrid-ablation"))
    tests = pd.concat([main_rows, sup, abl], ignore_index=True)
    args.out.mkdir(parents=True, exist_ok=True)
    tests.to_csv(args.out / "analysis_tests.csv", index=False)
    layers, llm = ablation(df), llm_variant(df)
    shown = int((main_rows.verdict == "non inférieure (démontré)").sum())
    claim = "oui" if shown == len(main_rows) else "non"
    lines = [
        "# Évaluation finale de l'étude combinée", "",
        f"**En une phrase.** {one_sentence(main_rows, sup)}", "",
        f"Non-infériorité de la candidate démontrée dans {shown} comparaisons sur "
        f"{len(main_rows)} (Holm, α = {ALPHA} unilatéral, marge −{MARGIN:g} %). "
        f"« Jamais moins bonne que la meilleure référence » : **{claim}**. Supériorité "
        f"démontrée : {int((sup.verdict == 'meilleure (démontré)').sum())} sur {len(sup)}.",
        "", "## Famille « hybrid » (principale)", "", md(main_rows),
        "", "## Famille « hybrid-sup »", "", md(sup),
        "", "## Famille « hybrid-ablation »", "", md(abl),
        "", "## Ablation des couches (sans test)", "", md(layers),
    ]  # fmt: skip
    if not llm.empty:
        lines += ["", "## Variante LLM (secondaire, sans test de Holm)", "", md(llm)]
    (args.out / "analysis.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:3]))
    print(args.out / "analysis.md")


if __name__ == "__main__":
    main()
