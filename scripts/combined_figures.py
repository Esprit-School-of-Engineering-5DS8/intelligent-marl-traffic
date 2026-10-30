"""Figures and summary table of the final evaluation of the combined study (phase E).

    python scripts/combined_figures.py   # -> docs/report/figures/combined/, results/combined/

* ``fig_forest``: the 36 preregistered non-inferiority tests (family hybrid), one point and
  its 95 % interval per comparison, the -2 % margin, coloured by verdict;
* ``fig_compromis``: gap of each controller to the best one on five criteria (no controller
  is best on all of them);
* ``fig_ambulances``: delay of the emergency vehicles on grid4x4, medium and peak demand;
* ``bilan_references``: for each reference, on how many criteria the candidate is better,
  not different, or worse (95 % paired intervals; exploratory, without Holm), each line of
  ``bilan_detail.csv`` naming the preregistered test of the same comparison when there is one.

Everything is read from results/combined/ (raw rows and analysis_tests.csv); the gains and
intervals are computed with the functions of combined_analysis.py, frozen with the
preregistration. Each figure has its table next to it (CSV) for a reader who cannot use it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import combined_analysis as ca  # noqa: E402
from hybrid_rank import md  # noqa: E402

from cotraffic.analysis.stats import crossed_bootstrap_ci  # noqa: E402
from cotraffic.paths import REPO_ROOT, RESULTS_DIR  # noqa: E402

OUT = RESULTS_DIR / "combined"
FIG = REPO_ROOT / "docs" / "report" / "figures" / "combined"
# reference palette of the figures (light surface)
INK, INK2, MUTED, GRID, AXIS, SURFACE = (
    "#0b0b0b",
    "#52514e",
    "#898781",
    "#e1e0d9",
    "#c3c2b7",
    "#fcfcfb",
)
BLUE, GOOD, CRITICAL, NEUTRAL = "#2a78d6", "#0ca30c", "#d03b3b", "#c3c2b7"
RAMP = ["#f4f8fd", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95"]

SCEN = {
    "normal": "normal",
    "emergency": "urgences",
    "incident": "incident",
    "pedestrians": "piétons",
    "sensor_noise": "capteurs bruités",
    "comm_dropout_30": "pertes de messages 30 %",
    "buses": "bus",
}
DEM = {"medium": "moyenne", "peak": "pointe"}
CANDIDATE = ("hybrid_h2", 4.0, "Candidate H2 β = 4")
CONTROLLERS = [
    CANDIDATE,
    ("mp", None, "MP"),
    ("ev_rule_mp", None, "EV-RULE-MP"),
    ("coop_full", None, "COOP-FULL"),
    ("team_rules", None, "TEAM-RULES"),
]
VERDICTS = {  # label, colour, marker, filled
    "best": ("Prouvée meilleure", GOOD, "o", True),
    "noninf": ("Prouvée non inférieure", BLUE, "D", True),
    "loss": ("Vraie perte", CRITICAL, "X", True),
    "wide": ("Trop large pour conclure", MUTED, "o", False),
}


def style() -> None:
    plt.rcParams.update(
        {
            "font.family": "Segoe UI",
            "font.size": 9,
            "text.color": INK,
            "axes.edgecolor": AXIS,
            "axes.labelcolor": INK2,
            "axes.linewidth": 0.8,
            "xtick.color": MUTED,
            "ytick.color": INK2,
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
        }
    )


def save(fig, name: str) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "svg"):
        fig.savefig(FIG / f"{name}.{ext}", dpi=200, bbox_inches="tight")
    plt.close(fig)


def label(case: str) -> str:
    net, scen, dem = case.split()
    return f"{net} · {SCEN[scen]} · {DEM[dem]}"


ORDER = [f"{n} {s} {d}" for n, s, d in [
    *[("grid4x4", s, d) for s in ("normal", "emergency", "incident", "pedestrians")
      for d in ("medium", "peak")],
    *[("real_district", s, d) for s in ("normal", "emergency", "incident")
      for d in ("medium", "peak")],
    ("grid4x4", "sensor_noise", "peak"), ("grid4x4", "comm_dropout_30", "peak"),
    ("grid4x4", "buses", "medium"), ("grid8x8", "normal", "peak"),
]]  # fmt: skip
GROUPS = [(0, 8, "grid4x4, cases principales"), (8, 14, "real_district"),
          (14, 17, "robustesse (grid4x4)"), (17, 18, "généralisation")]  # fmt: skip


# ---------------------------------------------------------------- a. forest plot
def forest(tests: pd.DataFrame) -> pd.DataFrame:
    main = tests[tests.famille == "hybrid"].set_index(["case", "métrique"])
    sup = tests[tests.famille == "hybrid-sup"].set_index(["case", "métrique"])

    def kind(key) -> str:
        if sup.loc[key, "verdict"] == "meilleure (démontré)":
            return "best"
        v = main.loc[key, "verdict"]
        return (
            "noninf"
            if v.startswith("non inférieure")
            else "loss"
            if v.startswith("vraie")
            else "wide"
        )

    rows = []
    for case in ORDER:
        for metric in ("trajet", "attente"):
            r, k = main.loc[(case, metric)], kind((case, metric))
            rows.append({"case": case, "métrique": metric, "référence": r["référence"],
                         "gain (%)": r["gain (%)"], "IC bas": r["IC bas"], "IC haut": r["IC haut"],
                         "p Holm (non-infériorité)": r["p Holm"],
                         "p Holm (supériorité)": sup.loc[(case, metric), "p Holm"],
                         "verdict": VERDICTS[k][0], "_kind": k})  # fmt: skip
    table = pd.DataFrame(rows)
    lim = 20.0
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 7.4), sharey=True)
    y = {case: i for i, case in enumerate(ORDER)}
    for ax, metric, title in zip(axes, ("trajet", "attente"), ("Temps de trajet", "Attente"),
                                 strict=True):  # fmt: skip
        part = table[table["métrique"] == metric]
        for start, _, _ in GROUPS[1:]:
            ax.axhline(start - 0.5, color=GRID, lw=0.8)
        ax.axvline(0, color=AXIS, lw=1)
        ax.axvline(-ca.MARGIN, color=CRITICAL, lw=1)
        for r in part.to_dict("records"):
            yy = y[r["case"]]
            _, colour, marker, filled = VERDICTS[r["_kind"]]
            low, high, point = r["IC bas"], r["IC haut"], r["gain (%)"]
            ax.plot([max(low, -lim), min(high, lim)], [yy, yy], color=colour, lw=1.6,
                    solid_capstyle="round")  # fmt: skip
            for bound, edge, sign in ((low, -lim, -1), (high, lim, 1)):
                if sign * bound > lim:  # interval cut at the edge: arrow and true bound
                    ax.annotate(
                        "",
                        xy=(edge, yy),
                        xytext=(edge - sign * 1.2, yy),
                        arrowprops={"arrowstyle": "->", "color": colour, "lw": 1.2},
                    )
                    ax.text(edge - sign * 1.5, yy - 0.32, f"{bound:+.0f}", color=INK2,
                            fontsize=7, ha="left" if sign < 0 else "right")  # fmt: skip
            ax.scatter([point], [yy], s=42, marker=marker, zorder=3, linewidths=1.4,
                       facecolors=colour if filled else SURFACE, edgecolors=colour)  # fmt: skip
            ax.text(lim + 0.6, yy, r["référence"].upper().replace("_", "-"), color=MUTED,
                    fontsize=7, va="center")  # fmt: skip
        ax.set_xlim(-lim, lim)
        ax.set_title(title, color=INK, fontsize=11, loc="left", pad=8)
        ax.grid(axis="x", color=GRID, lw=0.6)
        ax.set_axisbelow(True)
        ax.tick_params(axis="y", length=0)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.text(-ca.MARGIN, -1.05, "marge −2 %", color=CRITICAL, fontsize=7.5, ha="right")
        ax.set_xlabel("gain sur la meilleure référence (%), positif = mieux")
    axes[0].set_yticks(range(len(ORDER)), [label(c) for c in ORDER])
    axes[0].set_ylim(len(ORDER) - 0.5, -1.4)
    for start, _, name in GROUPS:
        axes[0].text(-0.62, start - 0.42, name, transform=axes[0].get_yaxis_transform(),
                     color=MUTED, fontsize=7.5, ha="left")  # fmt: skip
    counts = table["_kind"].value_counts()
    handles = [
        plt.Line2D([], [], color=c, marker=m, lw=1.6, markersize=7,
                   markerfacecolor=c if f else SURFACE, label=f"{n} ({counts.get(k, 0)})")
        for k, (n, c, m, f) in VERDICTS.items()
    ]  # fmt: skip
    fig.legend(handles=handles, loc="upper center", ncol=4, frameon=False,
               bbox_to_anchor=(0.55, 1.0))  # fmt: skip
    fig.suptitle("Candidate contre la meilleure référence de chaque case : 36 tests de "
                 "non-infériorité (Holm), graines de test 0 à 4", x=0.02, ha="left",
                 y=1.045, fontsize=12, color=INK)  # fmt: skip
    fig.text(0.02, -0.02, "Trait : intervalle de confiance à 95 % (bootstrap croisé modèles x "
             "graines). Flèche : intervalle coupé, borne indiquée. À droite : la référence de la "
             "comparaison.", color=MUTED, fontsize=7.5)  # fmt: skip
    save(fig, "fig_forest")
    return table.drop(columns="_kind")


# ---------------------------------------------------------------- b. trade-off matrix
def cell_mean(cell: pd.DataFrame, method: str, param, metric: str) -> float:
    t = ca.table(cell, method, param, metric)
    return float(np.nanmean(t.to_numpy())) if t.size else np.nan


def criteria(df: pd.DataFrame) -> pd.DataFrame:
    """Mean gap (%) of each controller to the best of the five, per criterion."""
    cells = {k: g for k, g in df.groupby(["network", "scenario", "demand"])}
    main = [k for k in cells if k[0] != "grid8x8" and k[1] in SCEN and k[1] not in (
        "sensor_noise", "comm_dropout_30", "buses")]  # fmt: skip
    spec = {
        "Trajet (14 cases)": [(k, "mean_travel_time") for k in main],
        "Attente (14 cases)": [(k, "mean_waiting_time") for k in main],
        "Ambulances (4 cases)": [(k, "ev_delay") for k in main if k[1] == "emergency"],
        "Piétons (2 cases)": [(k, "ped_mean_waiting_time") for k in main if k[1] == "pedestrians"],
        "Capteurs bruités": [(("grid4x4", "sensor_noise", "peak"), m)
                             for m in ("mean_travel_time", "mean_waiting_time")],
    }  # fmt: skip
    out = {}
    for crit, items in spec.items():
        gaps = {name: [] for _, _, name in CONTROLLERS}
        for key, metric in items:
            values = {n: cell_mean(cells[key], m, p, metric) for m, p, n in CONTROLLERS}
            best = min(values.values())
            for n, v in values.items():
                gaps[n].append(100 * (v - best) / best)
        out[crit] = {n: float(np.mean(g)) for n, g in gaps.items()}
    return pd.DataFrame(out)


def compromis(df: pd.DataFrame) -> pd.DataFrame:
    gaps = criteria(df)
    fig, ax = plt.subplots(figsize=(10.6, 3.6))
    cap = 30.0
    for i, name in enumerate(gaps.index):
        for j, crit in enumerate(gaps.columns):
            v = gaps.loc[name, crit]
            step = int(min(v, cap) / cap * (len(RAMP) - 1) + 0.5)
            ax.add_patch(plt.Rectangle((j + 0.03, i + 0.05), 0.94, 0.9, color=RAMP[step], lw=0))
            best = v == gaps[crit].min()  # the best of the five on this criterion
            ink = "#ffffff" if step >= 4 else INK
            weight = "bold" if best else "normal"
            ax.text(j + 0.5, i + 0.42, f"+{v:.1f} %".replace(".", ","), ha="center",
                    va="center", fontsize=9.5, color=ink, fontweight=weight)  # fmt: skip
            if best:
                ax.text(j + 0.5, i + 0.74, "le meilleur", ha="center", va="center",
                        fontsize=7, color=ink)  # fmt: skip
    worst = gaps.max(axis=1)  # the compromise: how far each controller falls on its worst one
    x0 = len(gaps.columns) + 0.25
    for i, name in enumerate(gaps.index):
        v = worst[name]
        best = v == worst.min()
        ax.add_patch(plt.Rectangle((x0 + 0.03, i + 0.05), 0.94, 0.9, fill=False,
                                   ec=INK if best else AXIS, lw=1.6 if best else 0.8))  # fmt: skip
        ax.text(x0 + 0.5, i + 0.42, f"+{v:.1f} %".replace(".", ","), ha="center", va="center",
                fontsize=9.5, color=INK, fontweight="bold" if best else "normal")  # fmt: skip
        if best:
            ax.text(x0 + 0.5, i + 0.74, "le plus petit", ha="center", va="center", fontsize=7)
    ax.set_xlim(0, x0 + 1)
    ax.set_ylim(len(gaps.index), 0)
    ax.set_xticks([*(np.arange(len(gaps.columns)) + 0.5), x0 + 0.5],
                  [*gaps.columns, "Pire écart\n(compromis)"])  # fmt: skip
    ax.set_yticks(np.arange(len(gaps.index)) + 0.5, gaps.index)
    ax.xaxis.tick_top()
    ax.tick_params(length=0)
    for lab in ax.get_yticklabels():
        if lab.get_text().startswith("Candidate"):
            lab.set_fontweight("bold")
            lab.set_color(INK)
    for side in ax.spines.values():
        side.set_visible(False)
    fig.suptitle("Aucun contrôleur n'est le meilleur partout : écart moyen au meilleur des "
                 "cinq, par critère (plus petit = mieux)", x=0.02, ha="left", y=1.04,
                 fontsize=12)  # fmt: skip
    fig.text(0.02, -0.06, "Graines de test 0 à 4. Écart moyen, sur les cases du critère, entre le "
             "contrôleur et le meilleur des cinq dans chaque case (plus clair = plus proche du "
             "meilleur). Capteurs bruités : moyenne des écarts\nde trajet et d'attente. Pire "
             "écart : le plus grand des cinq écarts du contrôleur. Hors urgences, EV-RULE-MP est "
             "MP ; hors urgences et piétons, TEAM-RULES est MP (mêmes épisodes par "
             "construction).", color=MUTED, fontsize=7.5)  # fmt: skip
    save(fig, "fig_compromis")
    return gaps.assign(**{"pire écart": worst}).round(2)


# ---------------------------------------------------------------- c. emergency vehicles
def ambulances(df: pd.DataFrame) -> pd.DataFrame:
    order = [("mp", None, "MP"), ("coop_full", None, "COOP-FULL"), ("team_rules", None,
             "TEAM-RULES"), ("ev_rule_mp", None, "EV-RULE-MP"), CANDIDATE]  # fmt: skip
    rows = []
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.2), sharey=True)
    for ax, dem in zip(axes, ("medium", "peak"), strict=True):
        cell = df[(df.network == "grid4x4") & (df.scenario == "emergency") & (df.demand == dem)]
        for i, (m, p, name) in enumerate(order):
            mean, lo, hi = crossed_bootstrap_ci(ca.table(cell, m, p, "ev_delay").to_numpy())
            colour = BLUE if m == "hybrid_h2" else NEUTRAL
            ax.barh(i, mean, height=0.56, color=colour, lw=0)
            ax.plot([lo, hi], [i, i], color=INK2, lw=1)
            ax.text(hi + 2, i, f"{mean:.0f} s", va="center", fontsize=9,
                    color=INK, fontweight="bold" if m == "hybrid_h2" else "normal")  # fmt: skip
            rows.append({"demande": DEM[dem], "contrôleur": name,
                         "retard moyen (s)": round(mean, 1), "IC bas": round(lo, 1),
                         "IC haut": round(hi, 1)})  # fmt: skip
        title = "Demande moyenne" if dem == "medium" else "Heure de pointe"
        ax.set_title(title, loc="left", fontsize=11, color=INK)
        ax.grid(axis="x", color=GRID, lw=0.6)
        ax.set_axisbelow(True)
        ax.tick_params(axis="y", length=0)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.set_xlabel("retard moyen des ambulances (s)")
    axes[0].set_yticks(range(len(order)), [n for _, _, n in order])
    axes[0].invert_yaxis()
    axes[1].set_xlim(0, 130)
    axes[0].set_xlim(0, 130)
    fig.suptitle("grid4x4, scénario urgences : retard des ambulances (graines de test 0 à 4)",
                 x=0.02, ha="left", y=1.06, fontsize=12)  # fmt: skip
    fig.text(0.02, -0.1, "Barre : moyenne des épisodes (retard moyen des 3 à 5 ambulances de "
             "chaque épisode). Trait : IC à 95 % (bootstrap sur les modèles et les graines).",
             color=MUTED, fontsize=7.5)  # fmt: skip
    save(fig, "fig_ambulances")
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 2. summary table
def bilan(df: pd.DataFrame, tests: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    main = tests[tests.famille == "hybrid"].set_index(["case", "métrique"])
    refs = [("mp", "MP"), ("ev_rule_mp", "EV-RULE-MP"), ("coop_full", "COOP-FULL"),
            ("team_rules", "TEAM-RULES"), ("ped_rule_mp", "PED-RULE-MP")]  # fmt: skip
    names = {"mean_travel_time": "trajet", "mean_waiting_time": "attente",
             "ev_delay": "ambulances", "ped_mean_waiting_time": "piétons"}  # fmt: skip
    detail = []
    for (net, scen, dem), cell in df.groupby(["network", "scenario", "demand"]):
        case = f"{net} {scen} {dem}"
        metrics = ["mean_travel_time", "mean_waiting_time"]
        metrics += ["ev_delay"] if scen == "emergency" else []
        metrics += ["ped_mean_waiting_time"] if scen == "pedestrians" else []
        for ref, ref_name in refs:
            if ref == "ped_rule_mp" and scen != "pedestrians":
                continue
            for metric in metrics:
                cand_t = ca.table(cell, "hybrid_h2", 4.0, metric)
                ref_t = ca.table(cell, ref, None, metric)
                point, draws = ca.gain_draws(cand_t, ref_t, np.random.default_rng(0))
                lo, hi = np.percentile(draws, [2.5, 97.5])
                if lo > 0:
                    verdict = "meilleure"
                elif hi < 0:  # split by the size of the mean gap: within the margin or not
                    small = point > -ca.MARGIN
                    verdict = f"moins bonne, de {'moins de 2 %' if small else '2 % ou plus'}"
                else:
                    verdict = "pas d'écart démontré"
                key = (case, names[metric])
                prereg = ""
                if key in main.index and main.loc[key, "référence"] == ref:
                    prereg = f"famille hybrid : {main.loc[key, 'verdict']}"
                detail.append({"référence": ref_name, "case": case, "critère": names[metric],
                               "gain (%)": round(point, 2), "IC bas": round(float(lo), 2),
                               "IC haut": round(float(hi), 2), "verdict (IC à 95 %)": verdict,
                               "test pré-enregistré": prereg})  # fmt: skip
    detail = pd.DataFrame(detail)
    summary = (
        detail.groupby("référence")["verdict (IC à 95 %)"].value_counts().unstack(fill_value=0)
        .reindex([n for _, n in refs]).reindex(
            columns=["meilleure", "pas d'écart démontré", "moins bonne, de moins de 2 %",
                     "moins bonne, de 2 % ou plus"], fill_value=0)
    )  # fmt: skip
    summary["critères"] = summary.sum(axis=1)
    return summary.reset_index(), detail


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    style()
    df = ca.load(OUT / "raw")
    tests = pd.read_csv(OUT / "analysis_tests.csv")
    f = forest(tests)
    g = compromis(df)
    a = ambulances(df)
    s, d = bilan(df, tests)
    f.to_csv(FIG / "fig_forest.csv", index=False)
    g.to_csv(FIG / "fig_compromis.csv")
    a.to_csv(FIG / "fig_ambulances.csv", index=False)
    d.to_csv(OUT / "bilan_detail.csv", index=False)
    lines = [
        "# Bilan de la candidate contre chaque référence", "",
        "Graines de test 0 à 4. Un critère = une case et une mesure (trajet, attente ; "
        "ambulances dans les cases urgences, piétons dans les cases piétons). « Meilleure » : "
        "l'intervalle de confiance à 95 % du gain est au-dessus de 0 ; « moins bonne » : il est "
        "en dessous (de moins de 2 % ou de 2 % ou plus, selon l'écart moyen) ; sinon « pas "
        "d'écart démontré ». **Exploratoire** : ce tableau compare à "
        "chaque référence, sans correction de Holm ; les tests qui font foi sont ceux de "
        "`analysis.md` (famille « hybrid », contre la meilleure référence de chaque case). "
        "Chaque critère est détaillé dans `bilan_detail.csv`, avec le test pré-enregistré de la "
        "même comparaison quand il y en a un.", "",
        md(s), "",
    ]  # fmt: skip
    (OUT / "bilan_references.md").write_text("\n".join(lines), encoding="utf-8")
    s.to_csv(OUT / "bilan_references.csv", index=False)
    print(s.to_string(index=False))
    print(g.to_string())
    print(a.to_string(index=False))


if __name__ == "__main__":
    main()
