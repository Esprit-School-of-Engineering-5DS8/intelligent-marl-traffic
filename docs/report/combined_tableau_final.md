# Tableau final : la candidate contre la meilleure référence

Évaluation unique sur les graines de test 0 à 4 (pré-enregistrement figé au commit `2c0dd1d`), famille de Holm « hybrid » : 18 situations x 2 mesures. Gain = (référence − candidate) / référence, positif = mieux ; intervalle à 95 % par bootstrap croisé (modèles x graines). Verdicts : « prouvée meilleure » (supériorité, Holm), « prouvée non inférieure » (non-infériorité à −2 %, Holm), « vraie perte » (l'intervalle entier sous 0), sinon « trop large pour conclure ».

Trop large pour conclure : 16 ; Prouvée non inférieure : 9 ; Prouvée meilleure : 6 ; Vraie perte : 5.

| situation | métrique | référence | gain (%) | IC à 95 % | p Holm (non-infériorité) | p Holm (supériorité) | verdict |
|---|---|---|---|---|---|---|---|
| grid4x4 · normal · moyenne | trajet | MP | −0,7 | [−1,0 ; −0,4] | < 0,01 | 1,00 | Prouvée non inférieure |
| grid4x4 · normal · moyenne | attente | COOP-FULL | +2,3 | [+1,4 ; +3,4] | < 0,01 | < 0,01 | Prouvée meilleure |
| grid4x4 · normal · pointe | trajet | MP | −1,6 | [−3,4 ; −0,2] | 1,00 | 1,00 | Vraie perte |
| grid4x4 · normal · pointe | attente | MP | −0,7 | [−4,8 ; +2,3] | 1,00 | 1,00 | Trop large pour conclure |
| grid4x4 · urgences · moyenne | trajet | MP | −1,0 | [−1,3 ; −0,8] | < 0,01 | 1,00 | Prouvée non inférieure |
| grid4x4 · urgences · moyenne | attente | MP | +1,4 | [+0,5 ; +2,1] | < 0,01 | 0,03 | Prouvée non inférieure |
| grid4x4 · urgences · pointe | trajet | MP | −1,1 | [−2,0 ; −0,1] | 0,54 | 1,00 | Vraie perte |
| grid4x4 · urgences · pointe | attente | MP | −0,2 | [−2,4 ; +1,9] | 0,84 | 1,00 | Trop large pour conclure |
| grid4x4 · incident · moyenne | trajet | MP | −0,8 | [−1,0 ; −0,5] | < 0,01 | 1,00 | Prouvée non inférieure |
| grid4x4 · incident · moyenne | attente | MP | +2,3 | [+1,5 ; +3,1] | < 0,01 | < 0,01 | Prouvée meilleure |
| grid4x4 · incident · pointe | trajet | MP | −0,9 | [−2,2 ; +0,3] | 0,81 | 1,00 | Trop large pour conclure |
| grid4x4 · incident · pointe | attente | MP | +0,6 | [−2,2 ; +3,4] | 0,63 | 1,00 | Trop large pour conclure |
| grid4x4 · piétons · moyenne | trajet | TEAM-RULES | −0,6 | [−0,8 ; −0,3] | < 0,01 | 1,00 | Prouvée non inférieure |
| grid4x4 · piétons · moyenne | attente | TEAM-RULES | +3,0 | [+1,9 ; +4,0] | < 0,01 | < 0,01 | Prouvée meilleure |
| grid4x4 · piétons · pointe | trajet | MP | −6,6 | [−18,8 ; +0,2] | 1,00 | 1,00 | Trop large pour conclure |
| grid4x4 · piétons · pointe | attente | MP | −12,9 | [−42,4 ; +2,4] | 1,00 | 1,00 | Trop large pour conclure |
| real_district · normal · moyenne | trajet | MP | +0,0 | [−0,2 ; +0,4] | < 0,01 | 1,00 | Prouvée non inférieure |
| real_district · normal · moyenne | attente | COOP-FULL | −0,2 | [−5,3 ; +6,2] | 1,00 | 1,00 | Trop large pour conclure |
| real_district · normal · pointe | trajet | MP | −2,6 | [−8,0 ; +2,2] | 1,00 | 1,00 | Trop large pour conclure |
| real_district · normal · pointe | attente | MP | −11,1 | [−32,1 ; +7,9] | 1,00 | 1,00 | Trop large pour conclure |
| real_district · urgences · moyenne | trajet | EV-RULE-MP | +0,2 | [−0,1 ; +0,6] | < 0,01 | 1,00 | Prouvée non inférieure |
| real_district · urgences · moyenne | attente | COOP-FULL | +0,9 | [−4,2 ; +6,4] | 1,00 | 1,00 | Trop large pour conclure |
| real_district · urgences · pointe | trajet | MP | −2,7 | [−10,2 ; +7,0] | 1,00 | 1,00 | Trop large pour conclure |
| real_district · urgences · pointe | attente | MP | −10,2 | [−39,7 ; +22,8] | 1,00 | 1,00 | Trop large pour conclure |
| real_district · incident · moyenne | trajet | MP | +0,4 | [−0,1 ; +0,8] | < 0,01 | 1,00 | Prouvée non inférieure |
| real_district · incident · moyenne | attente | COOP-FULL | +0,8 | [−3,8 ; +5,0] | 1,00 | 1,00 | Trop large pour conclure |
| real_district · incident · pointe | trajet | COOP-FULL | −0,4 | [−8,3 ; +7,4] | 1,00 | 1,00 | Trop large pour conclure |
| real_district · incident · pointe | attente | COOP-FULL | −2,7 | [−35,5 ; +24,4] | 1,00 | 1,00 | Trop large pour conclure |
| grid4x4 · capteurs bruités · pointe | trajet | COOP-FULL | +6,1 | [+2,1 ; +13,9] | < 0,01 | < 0,01 | Prouvée meilleure |
| grid4x4 · capteurs bruités · pointe | attente | COOP-FULL | +14,1 | [+3,3 ; +34,0] | < 0,01 | 0,02 | Prouvée meilleure |
| grid4x4 · pertes de messages 30 % · pointe | trajet | MP | −1,7 | [−3,0 ; −0,5] | 1,00 | 1,00 | Vraie perte |
| grid4x4 · pertes de messages 30 % · pointe | attente | MP | −1,0 | [−3,5 ; +1,6] | 1,00 | 1,00 | Trop large pour conclure |
| grid4x4 · bus · moyenne | trajet | MP | −0,9 | [−1,3 ; −0,6] | < 0,01 | 1,00 | Prouvée non inférieure |
| grid4x4 · bus · moyenne | attente | MP | +2,0 | [+1,0 ; +2,9] | < 0,01 | < 0,01 | Prouvée meilleure |
| grid8x8 · normal · pointe | trajet | MP | −2,1 | [−2,6 ; −1,7] | 1,00 | 1,00 | Vraie perte |
| grid8x8 · normal · pointe | attente | MP | −1,4 | [−2,1 ; −0,8] | 0,93 | 1,00 | Vraie perte |

**Remarque.** Deux groupes de cas « trop larges pour conclure » ont une estimation nettement défavorable : real_district en pointe (−0,4 à −11 % selon la situation et la mesure) et grid4x4 avec piétons en pointe (−6,6 % de trajet, −12,9 % d'attente). La candidate y fait probablement moins bien que Max-Pressure ; 5 graines ne suffisent pas à le démontrer, et la validation allait dans le même sens. Avec piétons en pointe, la candidate s'engorge sur certains épisodes ; COOP-FULL seul s'engorge plus souvent.

Figure : `figures/combined/fig_forest.png`. Calcul : `scripts/combined_analysis.py` (figé avec le pré-enregistrement), sortie complète dans `results/combined/analysis.md`.
