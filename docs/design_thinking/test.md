# 5. Test - how we test the ideas

## Simulation experiments (the evidence in the report)

| Item | Protocol |
|---|---|
| Episode | 15 min warm-up (not measured) + 60 min measured + 15 min cool-down without new demand |
| Conditions | demand low / medium / peak / rush-hour profile; scenarios normal, incident, emergency, pedestrians, buses; sensor noise and communication dropout (robustness) |
| Networks | grid4x4 (training and evaluation), real district (training and evaluation), grid8x8 (evaluation only, zero-shot) |
| Methods | fixed-time (Webster), actuated, Max-Pressure, emergency preemption rule on actuated control and on Max-Pressure, IND, COOP, COOP-ECO, COOP-FULL |
| Seeds | 5 evaluation seeds per cell, never used for training or checkpoint selection |
| Statistics | mean and bootstrap 95% CI (training runs and test seeds resampled for learned variants); paired differences on the same test seed; Mann-Whitney U vs the best baseline with Holm correction over a fixed confirmatory family; Cliff's delta |
| Failures counted | teleported vehicles, vehicles that never finished, shield interventions |

Research questions RQ1-RQ6 are listed in `docs/report_outline.md` and answered in
`docs/report/08_results.md`; every figure and table is produced by `make figures` /
`make tables` from the files in `results/`.

## TEAM - tests with people

| Date | Who | What we showed (demo video, dashboard) | Feedback | Change made |
|---|---|---|---|---|
| | | | | |

Suggested questions after the side-by-side demo (`make demo`):

1. Which of the two intersections would you rather drive through? Why?
2. Is the emergency-vehicle behaviour acceptable for the other drivers?
3. What would you need to see before trusting this on a real street?
