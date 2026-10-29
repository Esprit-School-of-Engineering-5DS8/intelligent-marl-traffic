# Classement des variantes, graine 1002

Règles : docs/COMBINED_PREREGISTRATION.md, section 0 (commit 7bd689e). ≥ meilleure ou égale, ? incertaine, ✗ pire ; « = » : identique par construction à la variante qu'elle devient dans cette case.

| rank | variant | cells | better_or_equal | uncertain | worse | ev_delay | ped_wait |
|---|---|---|---|---|---|---|---|
| 1 | H2 : COOP-FULL + biais MP β = 4, + EV-RULE | 14 | 10 | 1 | 3 | 35.79 | 13.42 |
| 2 | H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | 14 | 10 | 1 | 3 | 35.79 | 13.42 |
| 3 | H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | 14 | 10 | 1 | 3 | 35.79 | 13.42 |
| 4 | H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | 14 | 8 | 2 | 4 | 35.12 | 13.42 |
| 5 | H2 : COOP-FULL + biais MP β = 2, + EV-RULE | 14 | 7 | 1 | 6 | 33.24 | 12.97 |
| 6 | H2 : COOP-FULL + biais MP β = 8, + EV-RULE | 14 | 6 | 0 | 8 | 35.89 | 15.59 |
| 7 | V1 : COOP-FULL + EV-RULE (commutation) | 14 | 5 | 1 | 8 | 35.72 | 12.07 |
| 8 | COOP-FULL + EV-RULE + PED-RULE (commutation) | 14 | 5 | 1 | 8 | 35.72 | 12.64 |
| 9 | COOP-FULL seul | 14 | 5 | 1 | 8 | 52.73 | 12.07 |

## Détail par case

| variant | cell | verdict | mean_travel_time_gap_% | mean_waiting_time_gap_% | mean_travel_time_ref | mean_waiting_time_ref | share_coop | share_mp | share_mix | share_ped | share_ev |
|---|---|---|---|---|---|---|---|---|---|---|---|
| COOP-FULL seul | grid4x4 emergency medium | ✗ | 2.44 | 0.25 | team_rules | team_rules | – | – | – | – | – |
| COOP-FULL seul | grid4x4 emergency peak | ✗ | 4.63 | 7.47 | mp | mp | – | – | – | – | – |
| COOP-FULL seul | grid4x4 incident medium | ✗ | 1.99 | 0 | mp | coop_full | – | – | – | – | – |
| COOP-FULL seul | grid4x4 incident peak | ✗ | 3.58 | 3.9 | mp | mp | – | – | – | – | – |
| COOP-FULL seul | grid4x4 normal medium | ✗ | 2.47 | -0 | mp | coop_full | – | – | – | – | – |
| COOP-FULL seul | grid4x4 normal peak | ✗ | 2.59 | 1.49 | mp | mp | – | – | – | – | – |
| COOP-FULL seul | grid4x4 pedestrians medium | ✗ | 2.62 | 1.79 | team_rules | team_rules | – | – | – | – | – |
| COOP-FULL seul | grid4x4 pedestrians peak | ✗ | 3.76 | 3.51 | mp | mp | – | – | – | – | – |
| COOP-FULL seul | real_district emergency medium | ? | 1.32 | 0 | mp | coop_full | – | – | – | – | – |
| COOP-FULL seul | real_district emergency peak | ≥ | 0 | -0 | coop_full | coop_full | – | – | – | – | – |
| COOP-FULL seul | real_district incident medium | ≥ | 0.79 | -0 | mp | coop_full | – | – | – | – | – |
| COOP-FULL seul | real_district incident peak | ≥ | -0 | -0 | coop_full | coop_full | – | – | – | – | – |
| COOP-FULL seul | real_district normal medium | ≥ | 0.57 | 0 | mp | coop_full | – | – | – | – | – |
| COOP-FULL seul | real_district normal peak | ≥ | -0 | -0 | coop_full | coop_full | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | grid4x4 emergency medium | ✗ | 2.29 | 0.11 | team_rules | team_rules | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | grid4x4 emergency peak | ✗ | 4.88 | 8.02 | mp | mp | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | grid4x4 incident medium | ✗= | 1.99 | 0 | mp | coop_full | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | grid4x4 incident peak | ✗= | 3.58 | 3.9 | mp | mp | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | grid4x4 normal medium | ✗= | 2.47 | -0 | mp | coop_full | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | grid4x4 normal peak | ✗= | 2.59 | 1.49 | mp | mp | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | grid4x4 pedestrians medium | ✗= | 2.62 | 1.79 | team_rules | team_rules | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | grid4x4 pedestrians peak | ✗= | 3.76 | 3.51 | mp | mp | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | real_district emergency medium | ? | 1.1 | -1.91 | mp | coop_full | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | real_district emergency peak | ≥ | -1.35 | -5.26 | coop_full | coop_full | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | real_district incident medium | ≥= | 0.79 | -0 | mp | coop_full | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | real_district incident peak | ≥= | -0 | -0 | coop_full | coop_full | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | real_district normal medium | ≥= | 0.57 | 0 | mp | coop_full | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | real_district normal peak | ≥= | -0 | -0 | coop_full | coop_full | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | grid4x4 emergency medium | ✗= | 2.29 | 0.11 | team_rules | team_rules | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | grid4x4 emergency peak | ✗= | 4.88 | 8.02 | mp | mp | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | grid4x4 incident medium | ✗= | 1.99 | 0 | mp | coop_full | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | grid4x4 incident peak | ✗= | 3.58 | 3.9 | mp | mp | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | grid4x4 normal medium | ✗= | 2.47 | -0 | mp | coop_full | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | grid4x4 normal peak | ✗= | 2.59 | 1.49 | mp | mp | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | grid4x4 pedestrians medium | ✗ | 2.62 | 1.79 | team_rules | team_rules | 0.999567 | 0 | 0 | 0.000433333 | 0 |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | grid4x4 pedestrians peak | ✗ | 5.62 | 8.09 | mp | mp | 0.992967 | 0 | 0 | 0.00703333 | 0 |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | real_district emergency medium | ?= | 1.1 | -1.91 | mp | coop_full | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | real_district emergency peak | ≥= | -1.35 | -5.26 | coop_full | coop_full | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | real_district incident medium | ≥= | 0.79 | -0 | mp | coop_full | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | real_district incident peak | ≥= | -0 | -0 | coop_full | coop_full | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | real_district normal medium | ≥= | 0.57 | 0 | mp | coop_full | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | real_district normal peak | ≥= | -0 | -0 | coop_full | coop_full | – | – | – | – | – |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | grid4x4 emergency medium | ✗ | 1.3 | -2.2 | team_rules | team_rules | 0 | 0 | 0.991133 | 0 | 0.00886667 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | grid4x4 emergency peak | ✗ | 3.84 | 6.86 | mp | mp | 0 | 0 | 0.987267 | 0 | 0.0127333 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | grid4x4 incident medium | ✗ | 1.6 | -0.95 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | grid4x4 incident peak | ? | 1.76 | 0.58 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | grid4x4 normal medium | ✗ | 1.53 | -1.25 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | grid4x4 normal peak | ≥ | 0.94 | -1.45 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | grid4x4 pedestrians medium | ✗ | 2.27 | 2.23 | team_rules | team_rules | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | grid4x4 pedestrians peak | ✗ | 3.07 | 3.67 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | real_district emergency medium | ≥ | 0.64 | -3.54 | mp | coop_full | 0 | 0 | 0.9955 | 0 | 0.0045 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | real_district emergency peak | ≥ | -1.48 | -5.95 | coop_full | coop_full | 0 | 0 | 0.994267 | 0 | 0.00573333 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | real_district incident medium | ≥ | 0.27 | -2.79 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | real_district incident peak | ≥ | -3.15 | -11.08 | coop_full | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | real_district normal medium | ≥ | 0.35 | 0.89 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | real_district normal peak | ≥ | -0.98 | -4.72 | coop_full | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | grid4x4 emergency medium | ≥ | 0.86 | -3.18 | team_rules | team_rules | 0 | 0 | 0.990367 | 0 | 0.00963333 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | grid4x4 emergency peak | ✗ | 1.89 | 2.88 | mp | mp | 0 | 0 | 0.987 | 0 | 0.013 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | grid4x4 incident medium | ≥ | 0.9 | -2.08 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | grid4x4 incident peak | ≥ | 0.84 | -0.21 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | grid4x4 normal medium | ≥ | 0.45 | -4.42 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | grid4x4 normal peak | ≥ | 0.58 | -1.42 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | grid4x4 pedestrians medium | ? | 1.05 | -0.94 | team_rules | team_rules | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | grid4x4 pedestrians peak | ≥ | 0.73 | -1.05 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | real_district emergency medium | ≥ | 0.72 | -0.52 | mp | coop_full | 0 | 0 | 0.9953 | 0 | 0.0047 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | real_district emergency peak | ≥ | -1.51 | -1.78 | coop_full | coop_full | 0 | 0 | 0.995067 | 0 | 0.00493333 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | real_district incident medium | ✗ | 0.41 | 3.29 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | real_district incident peak | ≥ | -0.87 | -2.1 | coop_full | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | real_district normal medium | ≥ | -0.24 | -0.99 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | real_district normal peak | ✗ | 3.02 | 14.73 | coop_full | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | grid4x4 emergency medium | ≥ | 0.32 | -0.91 | team_rules | team_rules | 0 | 0 | 0.990933 | 0 | 0.00906667 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | grid4x4 emergency peak | ✗ | 1.13 | 2.87 | mp | mp | 0 | 0 | 0.987267 | 0 | 0.0127333 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | grid4x4 incident medium | ≥ | 0.01 | -0.75 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | grid4x4 incident peak | ≥ | -0.19 | -0.84 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | grid4x4 normal medium | ≥ | 0.05 | -1.36 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | grid4x4 normal peak | ≥ | -0.52 | -1.7 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | grid4x4 pedestrians medium | ✗ | 4.17 | 17.87 | team_rules | team_rules | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | grid4x4 pedestrians peak | ≥ | 0.12 | 0.45 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | real_district emergency medium | ✗ | 0.53 | 3.61 | mp | coop_full | 0 | 0 | 0.995233 | 0 | 0.00476667 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | real_district emergency peak | ✗ | 0.4 | 6.04 | coop_full | coop_full | 0 | 0 | 0.995033 | 0 | 0.00496667 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | real_district incident medium | ✗ | 0.15 | 7.72 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | real_district incident peak | ✗ | 2.73 | 15.31 | coop_full | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | real_district normal medium | ✗ | 0.14 | 8.96 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | real_district normal peak | ✗ | 5.09 | 27.02 | coop_full | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | grid4x4 emergency medium | ≥ | 0.86 | -3.18 | team_rules | team_rules | 0 | 0 | 0.990367 | 0 | 0.00963333 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | grid4x4 emergency peak | ✗ | 1.89 | 2.88 | mp | mp | 0 | 0 | 0.987 | 0 | 0.013 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | grid4x4 incident medium | ≥ | 0.9 | -2.08 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | grid4x4 incident peak | ≥ | 0.84 | -0.21 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | grid4x4 normal medium | ≥ | 0.45 | -4.42 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | grid4x4 normal peak | ≥ | 0.58 | -1.42 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | grid4x4 pedestrians medium | ? | 1.05 | -0.94 | team_rules | team_rules | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | grid4x4 pedestrians peak | ≥ | 0.73 | -1.05 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | real_district emergency medium | ≥ | 0.72 | -0.52 | mp | coop_full | 0 | 0 | 0.9953 | 0 | 0.0047 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | real_district emergency peak | ✗ | 0.55 | 4.89 | coop_full | coop_full | 0 | 0.1111 | 0.884333 | 0 | 0.00456667 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | real_district incident medium | ✗ | 0.41 | 3.29 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | real_district incident peak | ? | 0.3 | 2.68 | coop_full | coop_full | 0 | 0.0740667 | 0.925933 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | real_district normal medium | ≥ | -0.24 | -0.99 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | real_district normal peak | ✗ | 3.72 | 16.17 | coop_full | coop_full | 0 | 0.0740667 | 0.925933 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | grid4x4 emergency medium | ≥ | 0.86 | -3.18 | team_rules | team_rules | 0 | 0 | 0.990367 | 0 | 0.00963333 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | grid4x4 emergency peak | ✗ | 1.89 | 2.88 | mp | mp | 0 | 0 | 0.987 | 0 | 0.013 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | grid4x4 incident medium | ≥ | 0.9 | -2.08 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | grid4x4 incident peak | ≥ | 0.84 | -0.21 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | grid4x4 normal medium | ≥ | 0.45 | -4.42 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | grid4x4 normal peak | ≥ | 0.58 | -1.42 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | grid4x4 pedestrians medium | ? | 1.05 | -0.94 | team_rules | team_rules | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | grid4x4 pedestrians peak | ≥ | 0.73 | -1.05 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | real_district emergency medium | ≥ | 0.72 | -0.52 | mp | coop_full | 0 | 0 | 0.9953 | 0 | 0.0047 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | real_district emergency peak | ≥ | -1.51 | -1.7 | coop_full | coop_full | 0 | 0.0370333 | 0.958033 | 0 | 0.00493333 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | real_district incident medium | ✗ | 0.41 | 3.29 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | real_district incident peak | ≥ | -0.3 | 0.02 | coop_full | coop_full | 0 | 0.0370333 | 0.962967 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | real_district normal medium | ≥ | -0.24 | -0.99 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | real_district normal peak | ✗ | 4.28 | 19.61 | coop_full | coop_full | 0 | 0.0370333 | 0.962967 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | grid4x4 emergency medium | ≥ | 0.86 | -3.18 | team_rules | team_rules | 0 | 0 | 0.990367 | 0 | 0.00963333 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | grid4x4 emergency peak | ✗ | 1.89 | 2.88 | mp | mp | 0 | 0 | 0.987 | 0 | 0.013 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | grid4x4 incident medium | ≥ | 0.9 | -2.08 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | grid4x4 incident peak | ≥ | 0.84 | -0.21 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | grid4x4 normal medium | ≥ | 0.45 | -4.42 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | grid4x4 normal peak | ≥ | 0.58 | -1.42 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | grid4x4 pedestrians medium | ? | 1.05 | -0.94 | team_rules | team_rules | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | grid4x4 pedestrians peak | ≥ | 0.73 | -1.05 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | real_district emergency medium | ≥ | 0.72 | -0.52 | mp | coop_full | 0 | 0 | 0.9953 | 0 | 0.0047 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | real_district emergency peak | ≥ | -1.51 | -1.78 | coop_full | coop_full | 0 | 0 | 0.995067 | 0 | 0.00493333 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | real_district incident medium | ✗ | 0.41 | 3.29 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | real_district incident peak | ≥ | -0.87 | -2.1 | coop_full | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | real_district normal medium | ≥ | -0.24 | -0.99 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | real_district normal peak | ✗ | 2.98 | 14.65 | coop_full | coop_full | 0 | 0.0370333 | 0.962967 | 0 | 0 |
