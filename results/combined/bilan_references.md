# Bilan de la candidate contre chaque référence

Graines de test 0 à 4. Un critère = une case et une mesure (trajet, attente ; ambulances dans les cases urgences, piétons dans les cases piétons). « Meilleure » : l'intervalle de confiance à 95 % du gain est au-dessus de 0 ; « moins bonne » : il est en dessous (de moins de 2 % ou de 2 % ou plus, selon l'écart moyen) ; sinon « pas d'écart démontré ». **Exploratoire** : ce tableau compare à chaque référence, sans correction de Holm ; les tests qui font foi sont ceux de `analysis.md` (famille « hybrid », contre la meilleure référence de chaque case). Chaque critère est détaillé dans `bilan_detail.csv`, avec le test pré-enregistré de la même comparaison quand il y en a un.

| référence | meilleure | pas d'écart démontré | moins bonne, de moins de 2 % | moins bonne, de 2 % ou plus | critères |
|---|---|---|---|---|---|
| MP | 15 | 18 | 8 | 1 | 42 |
| EV-RULE-MP | 11 | 21 | 7 | 3 | 42 |
| COOP-FULL | 25 | 16 | 0 | 1 | 42 |
| TEAM-RULES | 16 | 17 | 8 | 1 | 42 |
| PED-RULE-MP | 2 | 4 | 0 | 0 | 6 |
