# Classement des variantes, graine 1000

Règles : docs/COMBINED_PREREGISTRATION.md, section 0 (commit 7bd689e). ≥ meilleure ou égale, ? incertaine, ✗ pire ; « = » : identique par construction à la variante qu'elle devient dans cette case.

| rank | variant | cells | better_or_equal | uncertain | worse | ev_delay | ped_wait |
|---|---|---|---|---|---|---|---|
| 1 | H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | 14 | 7 | 2 | 5 | 30.83 | 13.76 |
| 2 | H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | 14 | 7 | 2 | 5 | 30.9 | 13.76 |
| 3 | H2 : COOP-FULL + biais MP β = 4, + EV-RULE | 14 | 7 | 2 | 5 | 31.11 | 13.76 |
| 4 | H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | 14 | 7 | 2 | 5 | 32.04 | 13.76 |
| 5 | H2 : COOP-FULL + biais MP β = 8, + EV-RULE | 14 | 6 | 3 | 5 | 32.92 | 14.91 |
| 6 | H2 : COOP-FULL + biais MP β = 2, + EV-RULE | 14 | 6 | 1 | 7 | 32.7 | 12.51 |
| 7 | COOP-FULL + EV-RULE + PED-RULE (commutation) | 14 | 5 | 0 | 9 | 29.13 | 11.61 |
| 8 | V1 : COOP-FULL + EV-RULE (commutation) | 14 | 4 | 1 | 9 | 29.13 | 11.64 |
| 9 | COOP-FULL + EV-RULE + ses règles piétons (commutation) | 14 | 4 | 1 | 9 | 29.13 | 11.96 |
| 10 | H1 : COOP-FULL / MP selon la congestion, quantile 90 %, + EV-RULE | 14 | 4 | 1 | 9 | 32.26 | 12.77 |
| 11 | H2 : COOP-FULL + biais MP β = 1, + EV-RULE | 14 | 4 | 1 | 9 | 32.78 | 11.23 |
| 12 | COOP-FULL seul | 14 | 4 | 1 | 9 | 40.17 | 11.64 |
| 13 | H1 : COOP-FULL / MP selon la congestion, quantile 50 %, + EV-RULE | 14 | 3 | 3 | 8 | 31.28 | 15 |
| 14 | H1 : COOP-FULL / MP selon la congestion, quantile 75 %, + EV-RULE | 14 | 3 | 1 | 10 | 30.93 | 12.99 |
| 15 | H1 : COOP-FULL / MP selon la congestion, quantile 95 %, + EV-RULE | 14 | 3 | 1 | 10 | 31.63 | 12.91 |

## Détail par case

| variant | cell | verdict | mean_travel_time_gap_% | mean_waiting_time_gap_% | mean_travel_time_ref | mean_waiting_time_ref | share_coop | share_mp | share_mix | share_ped | share_ev |
|---|---|---|---|---|---|---|---|---|---|---|---|
| COOP-FULL seul | grid4x4 emergency medium | ✗ | 1.9 | 0 | ev_rule_mp | coop_full | – | – | – | – | – |
| COOP-FULL seul | grid4x4 emergency peak | ✗ | 1.58 | -0 | ev_rule_mp | coop_full | – | – | – | – | – |
| COOP-FULL seul | grid4x4 incident medium | ✗ | 3.34 | 5.05 | mp | mp | – | – | – | – | – |
| COOP-FULL seul | grid4x4 incident peak | ✗ | 2.62 | 1.23 | mp | mp | – | – | – | – | – |
| COOP-FULL seul | grid4x4 normal medium | ✗ | 2.19 | 0.21 | mp | mp | – | – | – | – | – |
| COOP-FULL seul | grid4x4 normal peak | ≥ | 0.36 | 0 | mp | coop_full | – | – | – | – | – |
| COOP-FULL seul | grid4x4 pedestrians medium | ✗ | 2.95 | 2.44 | mp | mp | – | – | – | – | – |
| COOP-FULL seul | grid4x4 pedestrians peak | ? | 1.14 | 0 | mp | coop_full | – | – | – | – | – |
| COOP-FULL seul | real_district emergency medium | ≥ | 0.16 | -0 | mp | coop_full | – | – | – | – | – |
| COOP-FULL seul | real_district emergency peak | ✗ | 5.32 | 18.42 | mp | mp | – | – | – | – | – |
| COOP-FULL seul | real_district incident medium | ≥ | 0.54 | -0 | mp | coop_full | – | – | – | – | – |
| COOP-FULL seul | real_district incident peak | ✗ | 10.98 | 33.37 | mp | mp | – | – | – | – | – |
| COOP-FULL seul | real_district normal medium | ≥ | -0 | -0 | coop_full | coop_full | – | – | – | – | – |
| COOP-FULL seul | real_district normal peak | ✗ | 2.97 | 8.06 | mp | mp | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | grid4x4 emergency medium | ✗ | 2.06 | 0.55 | ev_rule_mp | coop_full | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | grid4x4 emergency peak | ✗ | 1.9 | 1.09 | ev_rule_mp | coop_full | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | grid4x4 incident medium | ✗= | 3.34 | 5.05 | mp | mp | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | grid4x4 incident peak | ✗= | 2.62 | 1.23 | mp | mp | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | grid4x4 normal medium | ✗= | 2.19 | 0.21 | mp | mp | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | grid4x4 normal peak | ≥= | 0.36 | 0 | mp | coop_full | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | grid4x4 pedestrians medium | ✗= | 2.95 | 2.44 | mp | mp | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | grid4x4 pedestrians peak | ?= | 1.14 | 0 | mp | coop_full | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | real_district emergency medium | ≥ | 0.09 | -0.5 | mp | coop_full | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | real_district emergency peak | ✗ | 4.69 | 15.63 | mp | mp | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | real_district incident medium | ≥= | 0.54 | -0 | mp | coop_full | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | real_district incident peak | ✗= | 10.98 | 33.37 | mp | mp | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | real_district normal medium | ≥= | -0 | -0 | coop_full | coop_full | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | real_district normal peak | ✗= | 2.97 | 8.06 | mp | mp | – | – | – | – | – |
| COOP-FULL + EV-RULE + ses règles piétons (commutation) | grid4x4 emergency medium | ✗= | 2.06 | 0.55 | ev_rule_mp | coop_full | – | – | – | – | – |
| COOP-FULL + EV-RULE + ses règles piétons (commutation) | grid4x4 emergency peak | ✗= | 1.9 | 1.09 | ev_rule_mp | coop_full | – | – | – | – | – |
| COOP-FULL + EV-RULE + ses règles piétons (commutation) | grid4x4 incident medium | ✗= | 3.34 | 5.05 | mp | mp | – | – | – | – | – |
| COOP-FULL + EV-RULE + ses règles piétons (commutation) | grid4x4 incident peak | ✗= | 2.62 | 1.23 | mp | mp | – | – | – | – | – |
| COOP-FULL + EV-RULE + ses règles piétons (commutation) | grid4x4 normal medium | ✗= | 2.19 | 0.21 | mp | mp | – | – | – | – | – |
| COOP-FULL + EV-RULE + ses règles piétons (commutation) | grid4x4 normal peak | ≥= | 0.36 | 0 | mp | coop_full | – | – | – | – | – |
| COOP-FULL + EV-RULE + ses règles piétons (commutation) | grid4x4 pedestrians medium | ✗ | 2.7 | 2.47 | mp | mp | 0.9845 | 0 | 0 | 0.0155 | 0 |
| COOP-FULL + EV-RULE + ses règles piétons (commutation) | grid4x4 pedestrians peak | ? | 1.29 | -0.47 | mp | coop_full | 0.9766 | 0 | 0 | 0.0234 | 0 |
| COOP-FULL + EV-RULE + ses règles piétons (commutation) | real_district emergency medium | ≥= | 0.09 | -0.5 | mp | coop_full | – | – | – | – | – |
| COOP-FULL + EV-RULE + ses règles piétons (commutation) | real_district emergency peak | ✗= | 4.69 | 15.63 | mp | mp | – | – | – | – | – |
| COOP-FULL + EV-RULE + ses règles piétons (commutation) | real_district incident medium | ≥= | 0.54 | -0 | mp | coop_full | – | – | – | – | – |
| COOP-FULL + EV-RULE + ses règles piétons (commutation) | real_district incident peak | ✗= | 10.98 | 33.37 | mp | mp | – | – | – | – | – |
| COOP-FULL + EV-RULE + ses règles piétons (commutation) | real_district normal medium | ≥= | -0 | -0 | coop_full | coop_full | – | – | – | – | – |
| COOP-FULL + EV-RULE + ses règles piétons (commutation) | real_district normal peak | ✗= | 2.97 | 8.06 | mp | mp | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | grid4x4 emergency medium | ✗= | 2.06 | 0.55 | ev_rule_mp | coop_full | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | grid4x4 emergency peak | ✗= | 1.9 | 1.09 | ev_rule_mp | coop_full | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | grid4x4 incident medium | ✗= | 3.34 | 5.05 | mp | mp | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | grid4x4 incident peak | ✗= | 2.62 | 1.23 | mp | mp | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | grid4x4 normal medium | ✗= | 2.19 | 0.21 | mp | mp | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | grid4x4 normal peak | ≥= | 0.36 | 0 | mp | coop_full | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | grid4x4 pedestrians medium | ✗ | 3.27 | 3.71 | mp | mp | 0.998533 | 0 | 0 | 0.00146667 | 0 |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | grid4x4 pedestrians peak | ≥ | 0.85 | -1.52 | mp | coop_full | 0.997633 | 0 | 0 | 0.00236667 | 0 |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | real_district emergency medium | ≥= | 0.09 | -0.5 | mp | coop_full | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | real_district emergency peak | ✗= | 4.69 | 15.63 | mp | mp | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | real_district incident medium | ≥= | 0.54 | -0 | mp | coop_full | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | real_district incident peak | ✗= | 10.98 | 33.37 | mp | mp | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | real_district normal medium | ≥= | -0 | -0 | coop_full | coop_full | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | real_district normal peak | ✗= | 2.97 | 8.06 | mp | mp | – | – | – | – | – |
| H1 : COOP-FULL / MP selon la congestion, quantile 50 %, + EV-RULE | grid4x4 emergency medium | ✗ | 2.09 | 1.43 | ev_rule_mp | coop_full | 0.9346 | 0.0596667 | 0 | 0 | 0.00576667 |
| H1 : COOP-FULL / MP selon la congestion, quantile 50 %, + EV-RULE | grid4x4 emergency peak | ? | 0.44 | 1.56 | ev_rule_mp | coop_full | 0.175933 | 0.817933 | 0 | 0 | 0.00616667 |
| H1 : COOP-FULL / MP selon la congestion, quantile 50 %, + EV-RULE | grid4x4 incident medium | ✗ | 3.22 | 4.96 | mp | mp | 0.965267 | 0.0347333 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 50 %, + EV-RULE | grid4x4 incident peak | ≥ | -1.1 | -2.88 | mp | mp | 0.175933 | 0.824067 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 50 %, + EV-RULE | grid4x4 normal medium | ✗ | 2.07 | 0.07 | mp | mp | 0.972233 | 0.0277667 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 50 %, + EV-RULE | grid4x4 normal peak | ? | -0.65 | 2.02 | mp | coop_full | 0.175933 | 0.824067 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 50 %, + EV-RULE | grid4x4 pedestrians medium | ✗ | 1.96 | 0.96 | mp | mp | 0.8935 | 0.1065 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 50 %, + EV-RULE | grid4x4 pedestrians peak | ✗ | 16.63 | 41.97 | mp | coop_full | 0.131933 | 0.868067 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 50 %, + EV-RULE | real_district emergency medium | ? | -0.2 | 2.09 | mp | coop_full | 0.617967 | 0.379467 | 0 | 0 | 0.00256667 |
| H1 : COOP-FULL / MP selon la congestion, quantile 50 %, + EV-RULE | real_district emergency peak | ✗ | 8.49 | 33.56 | mp | mp | 0.3328 | 0.664367 | 0 | 0 | 0.0028 |
| H1 : COOP-FULL / MP selon la congestion, quantile 50 %, + EV-RULE | real_district incident medium | ≥ | -0.15 | -3.25 | mp | coop_full | 0.656067 | 0.343933 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 50 %, + EV-RULE | real_district incident peak | ✗ | 9.48 | 35.07 | mp | mp | 0.338633 | 0.661367 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 50 %, + EV-RULE | real_district normal medium | ≥ | -0.64 | 0.85 | coop_full | coop_full | 0.624333 | 0.375667 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 50 %, + EV-RULE | real_district normal peak | ✗ | 8.84 | 34.97 | mp | mp | 0.306867 | 0.693133 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 75 %, + EV-RULE | grid4x4 emergency medium | ✗ | 2.06 | 0.55 | ev_rule_mp | coop_full | 0.9944 | 0 | 0 | 0 | 0.0056 |
| H1 : COOP-FULL / MP selon la congestion, quantile 75 %, + EV-RULE | grid4x4 emergency peak | ✗ | 1.61 | 3.2 | ev_rule_mp | coop_full | 0.613567 | 0.380167 | 0 | 0 | 0.00626667 |
| H1 : COOP-FULL / MP selon la congestion, quantile 75 %, + EV-RULE | grid4x4 incident medium | ✗ | 3.34 | 5.05 | mp | mp | 1 | 0 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 75 %, + EV-RULE | grid4x4 incident peak | ? | 1.5 | 1.68 | mp | mp | 0.6088 | 0.3912 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 75 %, + EV-RULE | grid4x4 normal medium | ✗ | 2.19 | 0.21 | mp | mp | 1 | 0 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 75 %, + EV-RULE | grid4x4 normal peak | ✗ | 0.66 | 3.51 | mp | coop_full | 0.629633 | 0.370367 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 75 %, + EV-RULE | grid4x4 pedestrians medium | ✗ | 2.95 | 2.44 | mp | mp | 1 | 0 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 75 %, + EV-RULE | grid4x4 pedestrians peak | ✗ | 3.28 | 6.91 | mp | coop_full | 0.384233 | 0.615767 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 75 %, + EV-RULE | real_district emergency medium | ≥ | -0.26 | -1.79 | mp | coop_full | 0.807067 | 0.1901 | 0 | 0 | 0.0028 |
| H1 : COOP-FULL / MP selon la congestion, quantile 75 %, + EV-RULE | real_district emergency peak | ✗ | 7.61 | 24.87 | mp | mp | 0.649 | 0.347767 | 0 | 0 | 0.00316667 |
| H1 : COOP-FULL / MP selon la congestion, quantile 75 %, + EV-RULE | real_district incident medium | ≥ | -0.09 | -3.64 | mp | coop_full | 0.7619 | 0.2381 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 75 %, + EV-RULE | real_district incident peak | ✗ | 3.91 | 4.59 | mp | mp | 0.608433 | 0.391567 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 75 %, + EV-RULE | real_district normal medium | ≥ | -0.66 | -3.84 | coop_full | coop_full | 0.804233 | 0.195767 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 75 %, + EV-RULE | real_district normal peak | ✗ | 11.69 | 48.66 | mp | mp | 0.619067 | 0.380933 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 90 %, + EV-RULE | grid4x4 emergency medium | ✗ | 2.06 | 0.55 | ev_rule_mp | coop_full | 0.9944 | 0 | 0 | 0 | 0.0056 |
| H1 : COOP-FULL / MP selon la congestion, quantile 90 %, + EV-RULE | grid4x4 emergency peak | ? | 1.56 | 1.82 | ev_rule_mp | coop_full | 0.828767 | 0.164733 | 0 | 0 | 0.00646667 |
| H1 : COOP-FULL / MP selon la congestion, quantile 90 %, + EV-RULE | grid4x4 incident medium | ✗ | 3.34 | 5.05 | mp | mp | 1 | 0 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 90 %, + EV-RULE | grid4x4 incident peak | ✗ | 1.79 | 0.92 | mp | mp | 0.8495 | 0.1505 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 90 %, + EV-RULE | grid4x4 normal medium | ✗ | 2.19 | 0.21 | mp | mp | 1 | 0 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 90 %, + EV-RULE | grid4x4 normal peak | ≥ | -0.43 | -0.78 | mp | coop_full | 0.8565 | 0.1435 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 90 %, + EV-RULE | grid4x4 pedestrians medium | ✗ | 2.95 | 2.44 | mp | mp | 1 | 0 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 90 %, + EV-RULE | grid4x4 pedestrians peak | ✗ | 5.19 | 11.48 | mp | coop_full | 0.5185 | 0.4815 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 90 %, + EV-RULE | real_district emergency medium | ≥ | -0.07 | -1.58 | mp | coop_full | 0.971333 | 0.0262667 | 0 | 0 | 0.0024 |
| H1 : COOP-FULL / MP selon la congestion, quantile 90 %, + EV-RULE | real_district emergency peak | ✗ | 10.84 | 40.66 | mp | mp | 0.817567 | 0.178567 | 0 | 0 | 0.00386667 |
| H1 : COOP-FULL / MP selon la congestion, quantile 90 %, + EV-RULE | real_district incident medium | ≥ | 0.47 | -1.81 | mp | coop_full | 0.962967 | 0.0370333 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 90 %, + EV-RULE | real_district incident peak | ✗ | 9.5 | 27.79 | mp | mp | 0.8677 | 0.1323 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 90 %, + EV-RULE | real_district normal medium | ≥ | -0.04 | -0.13 | coop_full | coop_full | 0.973533 | 0.0264667 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 90 %, + EV-RULE | real_district normal peak | ✗ | 12.8 | 49.88 | mp | mp | 0.820133 | 0.179867 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 95 %, + EV-RULE | grid4x4 emergency medium | ✗ | 2.06 | 0.55 | ev_rule_mp | coop_full | 0.9944 | 0 | 0 | 0 | 0.0056 |
| H1 : COOP-FULL / MP selon la congestion, quantile 95 %, + EV-RULE | grid4x4 emergency peak | ✗ | 2.39 | 3.08 | ev_rule_mp | coop_full | 0.909267 | 0.0845 | 0 | 0 | 0.0062 |
| H1 : COOP-FULL / MP selon la congestion, quantile 95 %, + EV-RULE | grid4x4 incident medium | ✗ | 3.34 | 5.05 | mp | mp | 1 | 0 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 95 %, + EV-RULE | grid4x4 incident peak | ✗ | 2.72 | 2.57 | mp | mp | 0.8935 | 0.1065 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 95 %, + EV-RULE | grid4x4 normal medium | ✗ | 2.19 | 0.21 | mp | mp | 1 | 0 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 95 %, + EV-RULE | grid4x4 normal peak | ? | 1.14 | 2.99 | mp | coop_full | 0.893533 | 0.106467 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 95 %, + EV-RULE | grid4x4 pedestrians medium | ✗ | 2.95 | 2.44 | mp | mp | 1 | 0 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 95 %, + EV-RULE | grid4x4 pedestrians peak | ✗ | 10.76 | 20.29 | mp | coop_full | 0.608767 | 0.391233 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 95 %, + EV-RULE | real_district emergency medium | ≥ | 0.01 | -0.95 | mp | coop_full | 0.992067 | 0.0052 | 0 | 0 | 0.00273333 |
| H1 : COOP-FULL / MP selon la congestion, quantile 95 %, + EV-RULE | real_district emergency peak | ✗ | 12.16 | 49.85 | mp | mp | 0.928133 | 0.0679333 | 0 | 0 | 0.00393333 |
| H1 : COOP-FULL / MP selon la congestion, quantile 95 %, + EV-RULE | real_district incident medium | ≥ | 0.3 | -2.72 | mp | coop_full | 0.9947 | 0.0053 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 95 %, + EV-RULE | real_district incident peak | ✗ | 10.3 | 28.01 | mp | mp | 0.915333 | 0.0846667 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 95 %, + EV-RULE | real_district normal medium | ≥ | 0.05 | 0.83 | coop_full | coop_full | 0.9947 | 0.0053 | 0 | 0 | 0 |
| H1 : COOP-FULL / MP selon la congestion, quantile 95 %, + EV-RULE | real_district normal peak | ✗ | 10.16 | 39.1 | mp | mp | 0.910067 | 0.0899333 | 0 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 1, + EV-RULE | grid4x4 emergency medium | ✗ | 1.35 | -0.89 | ev_rule_mp | coop_full | 0 | 0 | 0.994433 | 0 | 0.00556667 |
| H2 : COOP-FULL + biais MP β = 1, + EV-RULE | grid4x4 emergency peak | ✗ | 3.48 | 4.59 | ev_rule_mp | coop_full | 0 | 0 | 0.992967 | 0 | 0.00703333 |
| H2 : COOP-FULL + biais MP β = 1, + EV-RULE | grid4x4 incident medium | ✗ | 2.62 | 2.56 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 1, + EV-RULE | grid4x4 incident peak | ? | 1.8 | -0.17 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 1, + EV-RULE | grid4x4 normal medium | ✗ | 1.8 | -0.06 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 1, + EV-RULE | grid4x4 normal peak | ✗ | 2.1 | 4.3 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 1, + EV-RULE | grid4x4 pedestrians medium | ✗ | 2.29 | 0.17 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 1, + EV-RULE | grid4x4 pedestrians peak | ≥ | 0.18 | -2.45 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 1, + EV-RULE | real_district emergency medium | ≥ | -0.13 | -2.85 | mp | coop_full | 0 | 0 | 0.997333 | 0 | 0.00266667 |
| H2 : COOP-FULL + biais MP β = 1, + EV-RULE | real_district emergency peak | ✗ | 8.56 | 33.45 | mp | mp | 0 | 0 | 0.9966 | 0 | 0.0034 |
| H2 : COOP-FULL + biais MP β = 1, + EV-RULE | real_district incident medium | ≥ | 0.15 | -5.1 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 1, + EV-RULE | real_district incident peak | ✗ | 9.49 | 27.23 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 1, + EV-RULE | real_district normal medium | ≥ | -0.19 | -1.89 | coop_full | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 1, + EV-RULE | real_district normal peak | ✗ | 7.64 | 27.96 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | grid4x4 emergency medium | ✗ | 1.77 | 0.71 | ev_rule_mp | coop_full | 0 | 0 | 0.994267 | 0 | 0.00573333 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | grid4x4 emergency peak | ≥ | 0.98 | -0.58 | ev_rule_mp | coop_full | 0 | 0 | 0.9936 | 0 | 0.0064 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | grid4x4 incident medium | ✗ | 2.08 | 1.68 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | grid4x4 incident peak | ? | 2 | 0.46 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | grid4x4 normal medium | ✗ | 1.88 | 0.48 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | grid4x4 normal peak | ≥ | -0.38 | -1.51 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | grid4x4 pedestrians medium | ✗ | 1.59 | -1.28 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | grid4x4 pedestrians peak | ≥ | -0.3 | -2.44 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | real_district emergency medium | ≥ | -0.23 | -3.24 | mp | coop_full | 0 | 0 | 0.997267 | 0 | 0.00273333 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | real_district emergency peak | ✗ | 8.36 | 33.34 | mp | mp | 0 | 0 | 0.996033 | 0 | 0.00396667 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | real_district incident medium | ≥ | -0.25 | -7.93 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | real_district incident peak | ✗ | 4.61 | 6.35 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | real_district normal medium | ≥ | -0.58 | -3.82 | coop_full | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | real_district normal peak | ✗ | 6.31 | 24.23 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | grid4x4 emergency medium | ≥ | 0.8 | -1.42 | ev_rule_mp | coop_full | 0 | 0 | 0.9944 | 0 | 0.0056 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | grid4x4 emergency peak | ≥ | 0.36 | -0.91 | ev_rule_mp | coop_full | 0 | 0 | 0.9939 | 0 | 0.00616667 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | grid4x4 incident medium | ? | 1.48 | 0.43 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | grid4x4 incident peak | ≥ | -0.2 | -3.76 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | grid4x4 normal medium | ? | 1.07 | -1.32 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | grid4x4 normal peak | ≥ | -1.17 | -1.89 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | grid4x4 pedestrians medium | ≥ | 0.91 | -2.1 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | grid4x4 pedestrians peak | ✗ | 13.8 | 23.24 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | real_district emergency medium | ✗ | -0.11 | 4.07 | mp | coop_full | 0 | 0 | 0.997267 | 0 | 0.00273333 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | real_district emergency peak | ✗ | 8.16 | 33.89 | mp | mp | 0 | 0 | 0.996467 | 0 | 0.00353333 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | real_district incident medium | ≥ | -0.7 | -5.83 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | real_district incident peak | ✗ | 5.68 | 16.01 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | real_district normal medium | ≥ | -0.64 | -0.69 | coop_full | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | real_district normal peak | ✗ | 7.85 | 30.64 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | grid4x4 emergency medium | ≥ | -0.25 | -1.82 | ev_rule_mp | coop_full | 0 | 0 | 0.9945 | 0 | 0.0055 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | grid4x4 emergency peak | ≥ | 0.29 | 0.51 | ev_rule_mp | coop_full | 0 | 0 | 0.993967 | 0 | 0.00606667 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | grid4x4 incident medium | ≥ | 0.46 | 0.25 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | grid4x4 incident peak | ≥ | -0.59 | -1.93 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | grid4x4 normal medium | ≥ | -0.09 | -2.41 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | grid4x4 normal peak | ? | -0.65 | 1.21 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | grid4x4 pedestrians medium | ≥ | 0.48 | 0.14 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | grid4x4 pedestrians peak | ? | 0.56 | 1.76 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | real_district emergency medium | ✗ | 0.16 | 11.93 | mp | coop_full | 0 | 0 | 0.9978 | 0 | 0.0022 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | real_district emergency peak | ✗ | 5.38 | 25.64 | mp | mp | 0 | 0 | 0.9965 | 0 | 0.0035 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | real_district incident medium | ? | -0.11 | 2.97 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | real_district incident peak | ✗ | 12.33 | 43.12 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | real_district normal medium | ✗ | -0.14 | 10.52 | coop_full | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | real_district normal peak | ✗ | 6.5 | 30.58 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | grid4x4 emergency medium | ≥ | 0.8 | -1.42 | ev_rule_mp | coop_full | 0 | 0 | 0.9944 | 0 | 0.0056 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | grid4x4 emergency peak | ≥ | 0.36 | -0.91 | ev_rule_mp | coop_full | 0 | 0 | 0.9939 | 0 | 0.00616667 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | grid4x4 incident medium | ? | 1.48 | 0.43 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | grid4x4 incident peak | ≥ | -0.2 | -3.76 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | grid4x4 normal medium | ? | 1.07 | -1.32 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | grid4x4 normal peak | ≥ | -1.17 | -1.89 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | grid4x4 pedestrians medium | ≥ | 0.91 | -2.1 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | grid4x4 pedestrians peak | ✗ | 13.8 | 23.24 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | real_district emergency medium | ✗ | -0.11 | 4.07 | mp | coop_full | 0 | 0 | 0.997267 | 0 | 0.00273333 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | real_district emergency peak | ✗ | 13.03 | 58.63 | mp | mp | 0 | 0.478667 | 0.517633 | 0 | 0.0037 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | real_district incident medium | ≥ | -0.7 | -5.83 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | real_district incident peak | ✗ | 8.18 | 26.01 | mp | mp | 0 | 0.296267 | 0.703733 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | real_district normal medium | ≥ | -0.64 | -0.69 | coop_full | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | real_district normal peak | ✗ | 10.71 | 44.75 | mp | mp | 0 | 0.481467 | 0.518533 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | grid4x4 emergency medium | ≥ | 0.8 | -1.42 | ev_rule_mp | coop_full | 0 | 0 | 0.9944 | 0 | 0.0056 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | grid4x4 emergency peak | ≥ | 0.36 | -0.91 | ev_rule_mp | coop_full | 0 | 0 | 0.9939 | 0 | 0.00616667 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | grid4x4 incident medium | ? | 1.48 | 0.43 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | grid4x4 incident peak | ≥ | -0.2 | -3.76 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | grid4x4 normal medium | ? | 1.07 | -1.32 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | grid4x4 normal peak | ≥ | -1.17 | -1.89 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | grid4x4 pedestrians medium | ≥ | 0.91 | -2.1 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | grid4x4 pedestrians peak | ✗ | 13.8 | 23.24 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | real_district emergency medium | ✗ | -0.11 | 4.07 | mp | coop_full | 0 | 0 | 0.997267 | 0 | 0.00273333 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | real_district emergency peak | ✗ | 11.42 | 50.46 | mp | mp | 0 | 0.368267 | 0.627967 | 0 | 0.00376667 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | real_district incident medium | ≥ | -0.7 | -5.83 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | real_district incident peak | ✗ | 7.31 | 24.05 | mp | mp | 0 | 0.185167 | 0.814833 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | real_district normal medium | ≥ | -0.64 | -0.69 | coop_full | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | real_district normal peak | ✗ | 8.87 | 36.83 | mp | mp | 0 | 0.3333 | 0.6667 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | grid4x4 emergency medium | ≥ | 0.8 | -1.42 | ev_rule_mp | coop_full | 0 | 0 | 0.9944 | 0 | 0.0056 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | grid4x4 emergency peak | ≥ | 0.36 | -0.91 | ev_rule_mp | coop_full | 0 | 0 | 0.9939 | 0 | 0.00616667 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | grid4x4 incident medium | ? | 1.48 | 0.43 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | grid4x4 incident peak | ≥ | -0.2 | -3.76 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | grid4x4 normal medium | ? | 1.07 | -1.32 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | grid4x4 normal peak | ≥ | -1.17 | -1.89 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | grid4x4 pedestrians medium | ≥ | 0.91 | -2.1 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | grid4x4 pedestrians peak | ✗ | 13.8 | 23.24 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | real_district emergency medium | ✗ | -0.11 | 4.07 | mp | coop_full | 0 | 0 | 0.997267 | 0 | 0.00273333 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | real_district emergency peak | ✗ | 8.07 | 34.1 | mp | mp | 0 | 0.184633 | 0.811567 | 0 | 0.0038 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | real_district incident medium | ≥ | -0.7 | -5.83 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | real_district incident peak | ✗ | 6.15 | 17.72 | mp | mp | 0 | 0.148133 | 0.851867 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | real_district normal medium | ≥ | -0.64 | -0.69 | coop_full | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | real_district normal peak | ✗ | 7.85 | 31.53 | mp | mp | 0 | 0.148133 | 0.851867 | 0 | 0 |
