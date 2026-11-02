# LLM dans la boucle de décision : la candidate + le LLM stratège (exploratoire)

## Graines de validation

| network | scenario | demand | seeds | travel_llm | travel_candidate | travel_gain_pct | waiting_llm | waiting_candidate | waiting_gain_pct | ambulances_llm | ambulances_candidate | ambulances_gain_pct | share_equilibre | share_fluidite | share_agent | switches | valid_rate | latency_p50_s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| grid4x4 | emergency | medium | 1 | 159.39 | 159.39 | 0 | 25.18 | 25.18 | 0 | 30.41 | 30.41 | 0 | 1 | 0 | 0 | 0 | 1 | 7.66 |
| grid4x4 | emergency | peak | 1 | 205.79 | 205.79 | 0 | 51.61 | 51.61 | 0 | 34.08 | 34.08 | 0 | 1 | 0 | 0 | 0 | 1 | 7.87 |
| grid4x4 | incident | medium | 1 | 159.79 | 159.98 | 0.12 | 25.36 | 25.36 | -0 | – | – | – | 0.889 | 0.111 | 0 | 2 | 1 | 7.57 |
| grid4x4 | incident | peak | 1 | 207.35 | 207.35 | 0 | 51.66 | 51.66 | 0 | – | – | – | 1 | 0 | 0 | 0 | 1 | 10.69 |
| grid4x4 | normal | medium | 1 | 159.47 | 159.47 | 0 | 25.12 | 25.12 | 0 | – | – | – | 1 | 0 | 0 | 0 | 1 | 6.28 |
| grid4x4 | normal | peak | 1 | 205.41 | 205.41 | 0 | 51.53 | 51.53 | 0 | – | – | – | 1 | 0 | 0 | 0 | 1 | 5.72 |
| grid4x4 | pedestrians | medium | 1 | 166.21 | 166.21 | 0 | 29.43 | 29.43 | 0 | – | – | – | 1 | 0 | 0 | 0 | 1 | 7.07 |
| grid4x4 | pedestrians | peak | 1 | 238.47 | 240.44 | 0.82 | 69.4 | 71.48 | 2.91 | – | – | – | 0.448 | 0.111 | 0.441 | 3 | 1 | 6.35 |
| real_district | emergency | medium | 1 | 110.6 | 110.6 | 0 | 7.38 | 7.38 | 0 | 21.66 | 21.66 | 0 | 1 | 0 | 0 | 0 | 1 | 8.53 |
| real_district | emergency | peak | 1 | 155.05 | 156.83 | 1.13 | 36.77 | 38.1 | 3.5 | 40.54 | 38.84 | -4.37 | 0.889 | 0.111 | 0 | 2 | 1 | 7.53 |
| real_district | incident | medium | 1 | 109.72 | 109.72 | 0 | 6.96 | 6.96 | 0 | – | – | – | 1 | 0 | 0 | 0 | 1 | 10.9 |
| real_district | incident | peak | 1 | 156.87 | 161.72 | 3 | 36.16 | 42.03 | 13.97 | – | – | – | 0.889 | 0.111 | 0 | 2 | 1 | 8.96 |
| real_district | normal | medium | 1 | 110.35 | 110.35 | 0 | 7.15 | 7.15 | 0 | – | – | – | 1 | 0 | 0 | 0 | 1 | 7.45 |
| real_district | normal | peak | 1 | 153.05 | 153.05 | 0 | 34.91 | 34.91 | 0 | – | – | – | 1 | 0 | 0 | 0 | 1 | 8.81 |

- travel : gain moyen +0.36 % (min +0.00, max +3.00)
- waiting : gain moyen +1.46 % (min +0.00, max +13.97)
- ambulances : gain moyen -1.09 % (min -4.37, max +0.00)

## Graines de test

| network | scenario | demand | seeds | travel_llm | travel_candidate | travel_gain_pct | waiting_llm | waiting_candidate | waiting_gain_pct | share_equilibre | share_fluidite | share_agent | switches | valid_rate | latency_p50_s | ambulances_llm | ambulances_candidate | ambulances_gain_pct |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| grid4x4 | buses | medium | 5 | 158.98 | 158.98 | 0 | 25.03 | 25.03 | 0 | 1 | 0 | 0 | 0 | 1 | 6.47 | – | – | – |
| grid4x4 | comm_dropout_30 | peak | 5 | 212.27 | 213.71 | 0.67 | 55.4 | 56.01 | 1.1 | 0.866 | 0.134 | 0 | 4 | 1 | 8.09 | – | – | – |
| grid4x4 | emergency | medium | 5 | 158.88 | 158.88 | 0 | 25.02 | 25.02 | 0 | 1 | 0 | 0 | 0 | 1 | 6.88 | 23.35 | 23.35 | 0 |
| grid4x4 | emergency | peak | 5 | 213.69 | 213.69 | 0 | 56.1 | 56.1 | 0 | 1 | 0 | 0 | 0 | 1 | 7.91 | 40.37 | 40.37 | 0 |
| grid4x4 | incident | medium | 5 | 158.86 | 158.96 | 0.07 | 24.94 | 25 | 0.24 | 0.989 | 0.011 | 0 | 0.4 | 1 | 7.25 | – | – | – |
| grid4x4 | incident | peak | 5 | 214.25 | 214.49 | 0.11 | 56.12 | 56.26 | 0.24 | 0.989 | 0.011 | 0 | 0.4 | 1 | 7.7 | – | – | – |
| grid4x4 | normal | medium | 5 | 158.6 | 158.6 | 0 | 24.84 | 24.84 | 0 | 1 | 0 | 0 | 0 | 1 | 7.19 | – | – | – |
| grid4x4 | normal | peak | 5 | 213.62 | 213.62 | 0 | 55.77 | 55.77 | 0 | 1 | 0 | 0 | 0 | 1 | 7.62 | – | – | – |
| grid4x4 | pedestrians | medium | 5 | 165.58 | 165.46 | -0.07 | 29.15 | 29.16 | 0 | 0.856 | 0 | 0.144 | 1.2 | 1 | 7.54 | – | – | – |
| grid4x4 | pedestrians | peak | 5 | 266.15 | 274.57 | 3.07 | 85.12 | 91.68 | 7.15 | 0.534 | 0.111 | 0.355 | 5.4 | 1 | 7.98 | – | – | – |
| grid4x4 | sensor_noise | peak | 5 | 221.82 | 219.38 | -1.11 | 61.5 | 59.87 | -2.72 | 0.866 | 0.134 | 0 | 4 | 1 | 7.38 | – | – | – |
| grid8x8 | normal | peak | 5 | 305.79 | 305.79 | 0 | 53.11 | 53.11 | 0 | 1 | 0 | 0 | 0 | 1 | 6.38 | – | – | – |
| real_district | emergency | medium | 5 | 109.49 | 109.49 | 0 | 7.41 | 7.41 | 0 | 1 | 0 | 0 | 0 | 1 | 9.8 | 21.28 | 21.28 | 0 |
| real_district | emergency | peak | 5 | 150.93 | 152.55 | 1.07 | 33.79 | 35.45 | 4.7 | 0.9 | 0.1 | 0 | 1.2 | 1 | 7.98 | 71.1 | 78.1 | 8.96 |
| real_district | incident | medium | 5 | 109.23 | 109.23 | 0 | 7.32 | 7.32 | 0 | 1 | 0 | 0 | 0 | 1 | 9.85 | – | – | – |
| real_district | incident | peak | 5 | 152.71 | 150.19 | -1.68 | 36.33 | 33.91 | -7.16 | 0.855 | 0.145 | 0 | 0.8 | 1 | 7.66 | – | – | – |
| real_district | normal | medium | 5 | 109.46 | 109.46 | 0 | 7.41 | 7.41 | 0 | 1 | 0 | 0 | 0 | 1 | 8.16 | – | – | – |
| real_district | normal | peak | 5 | 157.54 | 156.69 | -0.54 | 40.15 | 39.34 | -2.04 | 0.955 | 0.045 | 0 | 1.2 | 1 | 8.28 | – | – | – |

- travel : gain moyen +0.09 % (min -1.68, max +3.07)
- waiting : gain moyen +0.08 % (min -7.16, max +7.15)
- ambulances : gain moyen +2.24 % (min +0.00, max +8.96)

