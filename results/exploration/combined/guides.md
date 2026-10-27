# Étape 4 : COOP-FULL guidé pendant les urgences (graine 1000)

* a delay difference of one vehicle counts only beyond 2 s;
* a cost to the other vehicles is "net" when the waiting time is worse in all three
  paired runs and worse by more than 1 % on average; "possible" when it is worse by more
  than 1 % on average with mixed signs; otherwise it is within the noise. The waiting time
  is that of all vehicles: the three emergency vehicles weigh less than 0.2 % of the mean.

Provenance des lignes :

* toutes les lignes lues sont dans `results/exploration/combined/raw/` ; les variantes guidées
  et COOP-FULL t2, t3 viennent de la relance au commit `4ca5f4b`, COOP-FULL t1 du lot 1 ;
* les 20 lignes du premier essai interrompu (commit `a11f878`) sont gardées à part dans
  `step4_first_try/` et ne servent qu'au contrôle de reproductibilité : identiques aux lignes
  de la relance sur toutes les métriques ;
* 96 lignes portent `4ca5f4b-dirty` : le seul fichier suivi modifié pendant leur calcul était
  `combined_summary.csv`, un fichier généré, réécrit à la fin de la première invocation ; le
  code (src, scripts, configs, tests) était exactement celui de `4ca5f4b`.

## grid4x4, urgences, demande medium

Références (modèle unique) : MP 56,2 s, EV-RULE-MP 17,5 s, TEAM-RULES 20,7 s.

| Variante | Retard moyen (s) | Retard de chaque ambulance, run 1 · 2 · 3 (s) | Ambulances mieux / pire (sur 9) | Attente (s) | Attente, écart apparié par run (%) | Coût voitures | Trajet des autres (s, écart %) | Décisions guidées | Décisions changées |
|---|---:|---|---:|---:|---|---|---:|---:|---:|
| COOP-FULL seul | 42,5 | 53/30/8 · 56/76/47 · 41/22/50 | – | 25,8 | – | – | 161,8 (+0,0) | – | – |
| A′ biais, β = 4, EV-RULE | 27,8 | 14/25/14 · 31/32/40 · 39/22/33 | 7 / 1 | 25,8 | -0,4 / +0,6 / +0,7 | bruit | 161,9 (+0,0) | 50 | 10 |
| A′ biais, β = 8, EV-RULE | 21,4 | 14/25/14 · 18/28/44 · 15/18/16 | 8 / 1 | 25,9 | -0,4 / +1,1 / +1,0 | bruit | 162,1 (+0,2) | 49 | 12 |
| A′ biais, β = 16, EV-RULE | 21,4 | 14/25/14 · 18/28/44 · 15/18/16 | 8 / 1 | 25,9 | -0,4 / +1,1 / +1,0 | bruit | 162,1 (+0,2) | 49 | 12 |
| B′ commutation, EV-RULE | 21,4 | 14/25/14 · 18/28/44 · 15/18/16 | 8 / 1 | 25,9 | -0,4 / +1,1 / +1,0 | bruit | 162,1 (+0,2) | 49 | 12 |
| A′ biais, β = 4, ses règles | 27,8 | 14/25/14 · 31/32/40 · 39/22/33 | 7 / 1 | 25,8 | -0,4 / +0,6 / +0,7 | bruit | 161,9 (+0,0) | 52 | 10 |
| A′ biais, β = 8, ses règles | 21,8 | 14/25/14 · 30/31/37 · 16/18/11 | 8 / 1 | 26,0 | -0,4 / +1,0 / +2,2 | bruit | 162,1 (+0,2) | 54 | 16 |
| A′ biais, β = 16, ses règles | 19,6 | 14/25/14 · 30/29/19 · 16/18/11 | 8 / 1 | 25,9 | -0,4 / +0,2 / +2,2 | bruit | 161,9 (+0,1) | 53 | 20 |
| B′ commutation, ses règles | 19,6 | 14/25/14 · 30/29/19 · 16/18/11 | 8 / 1 | 25,9 | -0,4 / +0,2 / +2,2 | bruit | 161,9 (+0,1) | 53 | 20 |

## grid4x4, urgences, demande peak

Références (modèle unique) : MP 85,2 s, EV-RULE-MP 34,7 s, TEAM-RULES 42,0 s.

| Variante | Retard moyen (s) | Retard de chaque ambulance, run 1 · 2 · 3 (s) | Ambulances mieux / pire (sur 9) | Attente (s) | Attente, écart apparié par run (%) | Coût voitures | Trajet des autres (s, écart %) | Décisions guidées | Décisions changées |
|---|---:|---|---:|---:|---|---|---:|---:|---:|
| COOP-FULL seul | 55,0 | 64/36/35 · 78/64/57 · 82/23/57 | – | 52,0 | – | – | 208,7 (+0,0) | – | – |
| A′ biais, β = 4, EV-RULE | 47,3 | 64/18/18 · 58/38/74 · 51/45/59 | 5 / 2 | 52,3 | -0,1 / +0,9 / +1,2 | bruit | 209,1 (+0,2) | 58 | 11 |
| A′ biais, β = 8, EV-RULE | 35,2 | 47/23/19 · 58/20/30 · 51/45/23 | 8 / 1 | 52,5 | +1,7 / +0,5 / +1,1 | net | 209,4 (+0,3) | 53 | 19 |
| A′ biais, β = 16, EV-RULE | 35,2 | 47/23/19 · 58/20/30 · 51/45/23 | 8 / 1 | 52,5 | +1,7 / +0,5 / +1,1 | net | 209,4 (+0,3) | 53 | 19 |
| B′ commutation, EV-RULE | 35,2 | 47/23/19 · 58/20/30 · 51/45/23 | 8 / 1 | 52,5 | +1,7 / +0,5 / +1,1 | net | 209,4 (+0,3) | 53 | 19 |
| A′ biais, β = 4, ses règles | 47,4 | 59/33/26 · 58/38/74 · 58/25/54 | 7 / 2 | 52,4 | +0,4 / +0,9 / +1,0 | bruit | 209,2 (+0,2) | 63 | 15 |
| A′ biais, β = 8, ses règles | 41,5 | 41/27/23 · 46/66/31 · 58/25/54 | 7 / 2 | 52,7 | +2,0 / +1,2 / +1,0 | net | 209,6 (+0,4) | 56 | 22 |
| A′ biais, β = 16, ses règles | 39,1 | 39/17/19 · 46/66/31 · 58/25/49 | 7 / 2 | 52,7 | +1,1 / +1,2 / +1,8 | net | 209,7 (+0,5) | 52 | 21 |
| B′ commutation, ses règles | 39,1 | 39/17/19 · 46/66/31 · 58/25/49 | 7 / 2 | 52,7 | +1,1 / +1,2 / +1,8 | net | 209,7 (+0,5) | 52 | 21 |

## real_district, urgences, demande medium

Références (modèle unique) : MP 26,5 s, EV-RULE-MP 26,5 s, TEAM-RULES 28,7 s.

| Variante | Retard moyen (s) | Retard de chaque ambulance, run 1 · 2 · 3 (s) | Ambulances mieux / pire (sur 9) | Attente (s) | Attente, écart apparié par run (%) | Coût voitures | Trajet des autres (s, écart %) | Décisions guidées | Décisions changées |
|---|---:|---|---:|---:|---|---|---:|---:|---:|
| COOP-FULL seul | 27,4 | 7/16/35 · 18/38/43 · 2/49/40 | – | 7,4 | – | – | 110,7 (+0,0) | – | – |
| A′ biais, β = 4, EV-RULE | 27,4 | 7/16/35 · 18/38/43 · 2/49/40 | 0 / 0 | 7,4 | +0,0 / +0,0 / +0,0 | bruit | 110,7 (+0,0) | 11 | 1 |
| A′ biais, β = 8, EV-RULE | 27,4 | 7/15/34 · 18/38/43 · 2/49/40 | 0 / 0 | 7,4 | -1,6 / +0,0 / +0,0 | bruit | 110,7 (-0,1) | 11 | 2 |
| A′ biais, β = 16, EV-RULE | 27,4 | 7/15/34 · 18/38/43 · 2/49/40 | 0 / 0 | 7,4 | -1,6 / +0,0 / +0,0 | bruit | 110,7 (-0,1) | 11 | 2 |
| B′ commutation, EV-RULE | 27,4 | 7/15/34 · 18/38/43 · 2/49/40 | 0 / 0 | 7,4 | -1,6 / +0,0 / +0,0 | bruit | 110,7 (-0,1) | 11 | 2 |
| A′ biais, β = 4, ses règles | 27,4 | 7/16/35 · 18/38/43 · 2/49/40 | 0 / 0 | 7,4 | +0,0 / +0,0 / +0,0 | bruit | 110,7 (+0,0) | 10 | 1 |
| A′ biais, β = 8, ses règles | 29,7 | 7/37/34 · 18/38/43 · 2/49/40 | 0 / 1 | 7,5 | +2,6 / +0,0 / +0,0 | bruit | 110,8 (+0,1) | 11 | 3 |
| A′ biais, β = 16, ses règles | 28,3 | 7/17/41 · 18/38/43 · 2/49/40 | 0 / 1 | 7,4 | +1,1 / +0,0 / +0,0 | bruit | 110,8 (+0,0) | 11 | 3 |
| B′ commutation, ses règles | 28,3 | 7/17/41 · 18/38/43 · 2/49/40 | 0 / 1 | 7,4 | +1,1 / +0,0 / +0,0 | bruit | 110,8 (+0,0) | 11 | 3 |

## real_district, urgences, demande peak

Références (modèle unique) : MP 29,9 s, EV-RULE-MP 32,0 s, TEAM-RULES 31,1 s.

| Variante | Retard moyen (s) | Retard de chaque ambulance, run 1 · 2 · 3 (s) | Ambulances mieux / pire (sur 9) | Attente (s) | Attente, écart apparié par run (%) | Coût voitures | Trajet des autres (s, écart %) | Décisions guidées | Décisions changées |
|---|---:|---|---:|---:|---|---|---:|---:|---:|
| COOP-FULL seul | 35,8 | 31/32/36 · 30/40/37 · 12/57/46 | – | 33,8 | – | – | 152,4 (+0,0) | – | – |
| A′ biais, β = 4, EV-RULE | 33,2 | 12/33/51 · 12/40/35 · 12/57/46 | 2 / 1 | 31,6 | -17,4 / -3,4 / +0,0 | bruit | 149,6 (-1,9) | 13 | 2 |
| A′ biais, β = 8, EV-RULE | 32,5 | 12/33/44 · 12/40/35 · 12/57/46 | 2 / 1 | 33,0 | -3,9 / -3,4 / +0,0 | bruit | 151,5 (-0,6) | 12 | 2 |
| A′ biais, β = 16, EV-RULE | 32,5 | 12/33/44 · 12/40/35 · 12/57/46 | 2 / 1 | 33,0 | -3,9 / -3,4 / +0,0 | bruit | 151,5 (-0,6) | 12 | 3 |
| B′ commutation, EV-RULE | 32,5 | 12/33/44 · 12/40/35 · 12/57/46 | 2 / 1 | 33,0 | -3,9 / -3,4 / +0,0 | bruit | 151,5 (-0,6) | 12 | 3 |
| A′ biais, β = 4, ses règles | 35,8 | 31/32/36 · 30/40/37 · 12/57/46 | 0 / 0 | 33,8 | +0,0 / +0,0 / +0,0 | bruit | 152,4 (+0,0) | 10 | 1 |
| A′ biais, β = 8, ses règles | 36,5 | 31/32/42 · 30/40/37 · 12/57/46 | 0 / 1 | 33,4 | -4,0 / +0,0 / +0,0 | bruit | 152,1 (-0,2) | 10 | 2 |
| A′ biais, β = 16, ses règles | 36,5 | 31/32/42 · 30/40/37 · 12/57/46 | 0 / 1 | 33,4 | -4,0 / +0,0 / +0,0 | bruit | 152,1 (-0,2) | 10 | 2 |
| B′ commutation, ses règles | 36,5 | 31/32/42 · 30/40/37 · 12/57/46 | 0 / 1 | 33,4 | -4,0 / +0,0 / +0,0 | bruit | 152,1 (-0,2) | 10 | 2 |

