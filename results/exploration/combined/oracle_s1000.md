# Phase B rapide : oracle de stratégie, graine 1000, modèle t1

python scripts/oracle_report.py --best hybrid_h2:2 [--seed 1000]
        # -> results/exploration/combined/oracle_s<seed>.md

Meilleur hybride fixe : `hybrid_h2:4`. Cases qui remplissent le critère : **3 sur 14** (seuil : 4). Décision fixée à l'avance : **s'arrêter (phase D)**.

| cellule | trajet oracle (s) | trajet gain vs hybride (%) | trajet gain vs meilleur du hasard (%) | trajet gain vs meilleur mode fixe (%) | attente oracle (s) | attente gain vs hybride (%) | attente gain vs meilleur du hasard (%) | attente gain vs meilleur mode fixe (%) | critère | fenêtres coop/mp/mix | rejeu = plan | retard ambulances oracle / hybride (s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| grid4x4 emergency medium | 158.9 | 0.28 | 0.03 | -0.09 | 24.8 | 1.53 | 0.87 | 1.53 | non | 0.33 / 0.22 / 0.44 | True | 21.7 / 30.4 |
| grid4x4 emergency peak | 205.5 | 0.13 | 1.32 | -0.05 | 50.8 | 1.64 | 2.82 | 1.64 | non | 0.22 / 0.22 / 0.56 | True | 40.5 / 34.1 |
| grid4x4 incident medium | 158.2 | 1.12 | 0.73 | -0.2 | 24.1 | 5.04 | 6.31 | 4.33 | oui | 0.33 / 0.22 / 0.44 | True | – |
| grid4x4 incident peak | 206 | 0.67 | 0.59 | 0.35 | 50.9 | 1.53 | 2.79 | 1.53 | non | 0.56 / 0.00 / 0.44 | True | – |
| grid4x4 normal medium | 157.8 | 1.06 | 0.48 | 0.33 | 24.3 | 3.38 | 1.49 | 3.38 | non | 0.22 / 0.44 / 0.33 | True | – |
| grid4x4 normal peak | 204.7 | 0.32 | -0.3 | 0.32 | 50.1 | 2.75 | 0.26 | 2.75 | non | 0.33 / 0.33 / 0.33 | True | – |
| grid4x4 pedestrians medium | 165.6 | 0.35 | 0.12 | -0.68 | 28.8 | 2.27 | 1.69 | 2.27 | non | 0.56 / 0.22 / 0.22 | True | – |
| grid4x4 pedestrians peak | 235.2 | 2.18 | 0.11 | 2.11 | 69.3 | 3.12 | -1.88 | 3.12 | non | 0.00 / 0.44 / 0.56 | True | – |
| real_district emergency medium | 109.2 | 1.29 | 0.91 | 0.46 | 6.7 | 9.11 | 7.23 | 1.44 | oui | 0.67 / 0.11 / 0.22 | True | 32.6 / 21.7 |
| real_district emergency peak | 164.5 | -4.87 | -16.53 | -13.48 | 44.7 | -17.45 | -80.93 | -56.2 | non | 0.44 / 0.00 / 0.56 | True | 26.8 / 38.8 |
| real_district incident medium | 109.9 | -0.18 | 0.28 | -0.18 | 6.9 | 0.42 | 3.67 | 0.42 | non | 0.89 / 0.00 / 0.11 | True | – |
| real_district incident peak | 175.7 | -8.62 | -12.68 | -22.25 | 54.5 | -29.56 | -49.21 | -83.67 | non | 0.33 / 0.11 / 0.56 | True | – |
| real_district normal medium | 109.2 | 1.01 | 0.84 | 0.73 | 6.7 | 6.29 | 8.94 | 3.59 | oui | 0.67 / 0.00 / 0.33 | True | – |
| real_district normal peak | 159.1 | -3.95 | -2.99 | -9.55 | 38.6 | -10.47 | -8.51 | -33.7 | non | 0.22 / 0.11 / 0.67 | True | – |
