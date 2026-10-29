# Classement des variantes, graine 1001

Règles : docs/COMBINED_PREREGISTRATION.md, section 0 (commit 7bd689e). ≥ meilleure ou égale, ? incertaine, ✗ pire ; « = » : identique par construction à la variante qu'elle devient dans cette case.

| rank | variant | cells | better_or_equal | uncertain | worse | ev_delay | ped_wait |
|---|---|---|---|---|---|---|---|
| 1 | H2 : COOP-FULL + biais MP β = 4, + EV-RULE | 14 | 7 | 3 | 4 | 39.98 | 14.1 |
| 2 | H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | 14 | 7 | 3 | 4 | 39.98 | 14.1 |
| 3 | H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | 14 | 7 | 3 | 4 | 39.98 | 14.1 |
| 4 | H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | 14 | 7 | 3 | 4 | 39.98 | 14.1 |
| 5 | H2 : COOP-FULL + biais MP β = 8, + EV-RULE | 14 | 7 | 0 | 7 | 54.08 | 16.57 |
| 6 | V1 : COOP-FULL + EV-RULE (commutation) | 14 | 6 | 0 | 8 | 46.15 | 12.44 |
| 7 | COOP-FULL + EV-RULE + PED-RULE (commutation) | 14 | 6 | 0 | 8 | 46.15 | 12.74 |
| 8 | COOP-FULL seul | 14 | 6 | 0 | 8 | 72.1 | 12.44 |
| 9 | H2 : COOP-FULL + biais MP β = 2, + EV-RULE | 14 | 5 | 1 | 8 | 38.11 | 14.45 |

## Détail par case

| variant | cell | verdict | mean_travel_time_gap_% | mean_waiting_time_gap_% | mean_travel_time_ref | mean_waiting_time_ref | share_coop | share_mp | share_mix | share_ped | share_ev |
|---|---|---|---|---|---|---|---|---|---|---|---|
| COOP-FULL seul | grid4x4 emergency medium | ✗ | 2.71 | 1.06 | team_rules | team_rules | – | – | – | – | – |
| COOP-FULL seul | grid4x4 emergency peak | ✗ | 3.2 | 3.11 | ev_rule_mp | ev_rule_mp | – | – | – | – | – |
| COOP-FULL seul | grid4x4 incident medium | ✗ | 2.58 | 1.57 | mp | mp | – | – | – | – | – |
| COOP-FULL seul | grid4x4 incident peak | ≥ | 0.78 | 0 | mp | coop_full | – | – | – | – | – |
| COOP-FULL seul | grid4x4 normal medium | ✗ | 2.62 | 1.86 | mp | mp | – | – | – | – | – |
| COOP-FULL seul | grid4x4 normal peak | ✗ | 3.71 | 3.88 | mp | mp | – | – | – | – | – |
| COOP-FULL seul | grid4x4 pedestrians medium | ✗ | 2.59 | 1.53 | mp | mp | – | – | – | – | – |
| COOP-FULL seul | grid4x4 pedestrians peak | ✗ | 3.39 | 1.71 | mp | mp | – | – | – | – | – |
| COOP-FULL seul | real_district emergency medium | ≥ | 0.84 | 0 | team_rules | coop_full | – | – | – | – | – |
| COOP-FULL seul | real_district emergency peak | ≥ | 0.22 | 0 | ev_rule_mp | coop_full | – | – | – | – | – |
| COOP-FULL seul | real_district incident medium | ≥ | 0.78 | -0 | mp | coop_full | – | – | – | – | – |
| COOP-FULL seul | real_district incident peak | ✗ | 2.16 | 10.93 | mp | mp | – | – | – | – | – |
| COOP-FULL seul | real_district normal medium | ≥ | 0 | -0 | coop_full | coop_full | – | – | – | – | – |
| COOP-FULL seul | real_district normal peak | ≥ | 0 | -0 | coop_full | coop_full | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | grid4x4 emergency medium | ✗ | 2.73 | 2.12 | team_rules | team_rules | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | grid4x4 emergency peak | ✗ | 3.93 | 4.77 | ev_rule_mp | ev_rule_mp | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | grid4x4 incident medium | ✗= | 2.58 | 1.57 | mp | mp | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | grid4x4 incident peak | ≥= | 0.78 | 0 | mp | coop_full | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | grid4x4 normal medium | ✗= | 2.62 | 1.86 | mp | mp | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | grid4x4 normal peak | ✗= | 3.71 | 3.88 | mp | mp | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | grid4x4 pedestrians medium | ✗= | 2.59 | 1.53 | mp | mp | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | grid4x4 pedestrians peak | ✗= | 3.39 | 1.71 | mp | mp | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | real_district emergency medium | ≥ | 0.84 | 0 | team_rules | coop_full | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | real_district emergency peak | ≥ | -0.51 | -2.38 | ev_rule_mp | coop_full | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | real_district incident medium | ≥= | 0.78 | -0 | mp | coop_full | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | real_district incident peak | ✗= | 2.16 | 10.93 | mp | mp | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | real_district normal medium | ≥= | 0 | -0 | coop_full | coop_full | – | – | – | – | – |
| V1 : COOP-FULL + EV-RULE (commutation) | real_district normal peak | ≥= | 0 | -0 | coop_full | coop_full | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | grid4x4 emergency medium | ✗= | 2.73 | 2.12 | team_rules | team_rules | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | grid4x4 emergency peak | ✗= | 3.93 | 4.77 | ev_rule_mp | ev_rule_mp | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | grid4x4 incident medium | ✗= | 2.58 | 1.57 | mp | mp | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | grid4x4 incident peak | ≥= | 0.78 | 0 | mp | coop_full | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | grid4x4 normal medium | ✗= | 2.62 | 1.86 | mp | mp | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | grid4x4 normal peak | ✗= | 3.71 | 3.88 | mp | mp | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | grid4x4 pedestrians medium | ✗ | 3.14 | 3.17 | mp | mp | 0.998033 | 0 | 0 | 0.00196667 | 0 |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | grid4x4 pedestrians peak | ✗ | 7.66 | 9.6 | mp | mp | 0.9935 | 0 | 0 | 0.0065 | 0 |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | real_district emergency medium | ≥= | 0.84 | 0 | team_rules | coop_full | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | real_district emergency peak | ≥= | -0.51 | -2.38 | ev_rule_mp | coop_full | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | real_district incident medium | ≥= | 0.78 | -0 | mp | coop_full | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | real_district incident peak | ✗= | 2.16 | 10.93 | mp | mp | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | real_district normal medium | ≥= | 0 | -0 | coop_full | coop_full | – | – | – | – | – |
| COOP-FULL + EV-RULE + PED-RULE (commutation) | real_district normal peak | ≥= | 0 | -0 | coop_full | coop_full | – | – | – | – | – |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | grid4x4 emergency medium | ✗ | 1.62 | -0.83 | team_rules | team_rules | 0 | 0 | 0.995 | 0 | 0.005 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | grid4x4 emergency peak | ✗ | 3.01 | 2.64 | ev_rule_mp | ev_rule_mp | 0 | 0 | 0.9923 | 0 | 0.0077 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | grid4x4 incident medium | ✗ | 1.95 | -0.44 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | grid4x4 incident peak | ≥ | 0.46 | -0.2 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | grid4x4 normal medium | ? | 1.25 | -1.8 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | grid4x4 normal peak | ✗ | 3.59 | 3.82 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | grid4x4 pedestrians medium | ✗ | 8 | 21.98 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | grid4x4 pedestrians peak | ✗ | 6.54 | 8.57 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | real_district emergency medium | ≥ | 0.72 | -0.14 | team_rules | coop_full | 0 | 0 | 0.997467 | 0 | 0.00253333 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | real_district emergency peak | ≥ | -5.42 | -20.94 | ev_rule_mp | coop_full | 0 | 0 | 0.997367 | 0 | 0.00263333 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | real_district incident medium | ≥ | -0.24 | -6.36 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | real_district incident peak | ✗ | 2.28 | 12.05 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | real_district normal medium | ✗ | 0.17 | 3.27 | coop_full | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 2, + EV-RULE | real_district normal peak | ≥ | -3.21 | -12.06 | coop_full | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | grid4x4 emergency medium | ? | 1.33 | -0.2 | team_rules | team_rules | 0 | 0 | 0.9952 | 0 | 0.0048 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | grid4x4 emergency peak | ≥ | -0.57 | -3.77 | ev_rule_mp | ev_rule_mp | 0 | 0 | 0.992933 | 0 | 0.00706667 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | grid4x4 incident medium | ? | 1.24 | -1.04 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | grid4x4 incident peak | ≥ | -0.3 | -1.16 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | grid4x4 normal medium | ≥ | 0.78 | -1.99 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | grid4x4 normal peak | ≥ | 0.32 | -1.61 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | grid4x4 pedestrians medium | ✗ | 1.41 | -0.29 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | grid4x4 pedestrians peak | ? | 1.68 | 1.01 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | real_district emergency medium | ≥ | 0.27 | 0.15 | team_rules | coop_full | 0 | 0 | 0.9977 | 0 | 0.0023 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | real_district emergency peak | ≥ | -0.49 | -3.01 | ev_rule_mp | coop_full | 0 | 0 | 0.996467 | 0 | 0.00353333 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | real_district incident medium | ✗ | 0.49 | 3.74 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | real_district incident peak | ✗ | 3.94 | 16.91 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | real_district normal medium | ✗ | 0.33 | 7.02 | coop_full | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 4, + EV-RULE | real_district normal peak | ≥ | -1.16 | -4.2 | coop_full | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | grid4x4 emergency medium | ≥ | 0.32 | -0.59 | team_rules | team_rules | 0 | 0 | 0.994767 | 0 | 0.00523333 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | grid4x4 emergency peak | ≥ | 0.72 | 0.53 | ev_rule_mp | ev_rule_mp | 0 | 0 | 0.9931 | 0 | 0.0069 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | grid4x4 incident medium | ≥ | 0.55 | 0.18 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | grid4x4 incident peak | ≥ | -0.98 | -0.03 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | grid4x4 normal medium | ≥ | 0.05 | -1.17 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | grid4x4 normal peak | ≥ | 0.26 | -0.56 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | grid4x4 pedestrians medium | ✗ | 6.9 | 24.18 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | grid4x4 pedestrians peak | ✗ | 2.83 | 3.95 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | real_district emergency medium | ✗ | 0.51 | 8.13 | team_rules | coop_full | 0 | 0 | 0.997433 | 0 | 0.00256667 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | real_district emergency peak | ✗ | 0.2 | 3.35 | ev_rule_mp | coop_full | 0 | 0 | 0.996633 | 0 | 0.00336667 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | real_district incident medium | ✗ | 0.55 | 11.56 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | real_district incident peak | ✗ | 4.35 | 21.66 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | real_district normal medium | ✗ | 0.04 | 12.67 | coop_full | coop_full | 0 | 0 | 1 | 0 | 0 |
| H2 : COOP-FULL + biais MP β = 8, + EV-RULE | real_district normal peak | ≥ | 0.18 | -0.18 | coop_full | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | grid4x4 emergency medium | ? | 1.33 | -0.2 | team_rules | team_rules | 0 | 0 | 0.9952 | 0 | 0.0048 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | grid4x4 emergency peak | ≥ | -0.57 | -3.77 | ev_rule_mp | ev_rule_mp | 0 | 0 | 0.992933 | 0 | 0.00706667 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | grid4x4 incident medium | ? | 1.24 | -1.04 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | grid4x4 incident peak | ≥ | -0.3 | -1.16 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | grid4x4 normal medium | ≥ | 0.78 | -1.99 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | grid4x4 normal peak | ≥ | 0.32 | -1.61 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | grid4x4 pedestrians medium | ✗ | 1.41 | -0.29 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | grid4x4 pedestrians peak | ? | 1.68 | 1.01 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | real_district emergency medium | ≥ | 0.27 | 0.15 | team_rules | coop_full | 0 | 0 | 0.9977 | 0 | 0.0023 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | real_district emergency peak | ≥ | -0.44 | -2.23 | ev_rule_mp | coop_full | 0 | 0.1111 | 0.885367 | 0 | 0.00353333 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | real_district incident medium | ✗ | 0.49 | 3.74 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | real_district incident peak | ✗ | 3.79 | 16.24 | mp | mp | 0 | 0.1111 | 0.8889 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | real_district normal medium | ✗ | 0.33 | 7.02 | coop_full | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 75 %, + EV-RULE | real_district normal peak | ≥ | -0.97 | -2.75 | coop_full | coop_full | 0 | 0.1111 | 0.8889 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | grid4x4 emergency medium | ? | 1.33 | -0.2 | team_rules | team_rules | 0 | 0 | 0.9952 | 0 | 0.0048 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | grid4x4 emergency peak | ≥ | -0.57 | -3.77 | ev_rule_mp | ev_rule_mp | 0 | 0 | 0.992933 | 0 | 0.00706667 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | grid4x4 incident medium | ? | 1.24 | -1.04 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | grid4x4 incident peak | ≥ | -0.3 | -1.16 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | grid4x4 normal medium | ≥ | 0.78 | -1.99 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | grid4x4 normal peak | ≥ | 0.32 | -1.61 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | grid4x4 pedestrians medium | ✗ | 1.41 | -0.29 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | grid4x4 pedestrians peak | ? | 1.68 | 1.01 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | real_district emergency medium | ≥ | 0.27 | 0.15 | team_rules | coop_full | 0 | 0 | 0.9977 | 0 | 0.0023 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | real_district emergency peak | ≥ | -0.44 | -2.23 | ev_rule_mp | coop_full | 0 | 0.1111 | 0.885367 | 0 | 0.00353333 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | real_district incident medium | ✗ | 0.49 | 3.74 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | real_district incident peak | ✗ | 3.79 | 16.24 | mp | mp | 0 | 0.1111 | 0.8889 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | real_district normal medium | ✗ | 0.33 | 7.02 | coop_full | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 90 %, + EV-RULE | real_district normal peak | ≥ | -0.97 | -2.75 | coop_full | coop_full | 0 | 0.1111 | 0.8889 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | grid4x4 emergency medium | ? | 1.33 | -0.2 | team_rules | team_rules | 0 | 0 | 0.9952 | 0 | 0.0048 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | grid4x4 emergency peak | ≥ | -0.57 | -3.77 | ev_rule_mp | ev_rule_mp | 0 | 0 | 0.992933 | 0 | 0.00706667 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | grid4x4 incident medium | ? | 1.24 | -1.04 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | grid4x4 incident peak | ≥ | -0.3 | -1.16 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | grid4x4 normal medium | ≥ | 0.78 | -1.99 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | grid4x4 normal peak | ≥ | 0.32 | -1.61 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | grid4x4 pedestrians medium | ✗ | 1.41 | -0.29 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | grid4x4 pedestrians peak | ? | 1.68 | 1.01 | mp | mp | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | real_district emergency medium | ≥ | 0.27 | 0.15 | team_rules | coop_full | 0 | 0 | 0.9977 | 0 | 0.0023 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | real_district emergency peak | ≥ | -0.44 | -2.23 | ev_rule_mp | coop_full | 0 | 0.1111 | 0.885367 | 0 | 0.00353333 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | real_district incident medium | ✗ | 0.49 | 3.74 | mp | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | real_district incident peak | ✗ | 3.78 | 16.27 | mp | mp | 0 | 0.0740667 | 0.925933 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | real_district normal medium | ✗ | 0.33 | 7.02 | coop_full | coop_full | 0 | 0 | 1 | 0 | 0 |
| H3 : H2 β = 4, MP partout si file d'entrée > quantile 95 %, + EV-RULE | real_district normal peak | ≥ | -0.97 | -2.75 | coop_full | coop_full | 0 | 0.1111 | 0.8889 | 0 | 0 |
