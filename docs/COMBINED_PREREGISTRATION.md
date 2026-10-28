# Pré-enregistrement de l'étude combinée

**Statut : brouillon.** Aucun épisode sur les graines de test 0 à 4 n'est lancé avant le commit
qui fige la version finale de ce fichier (phase D). Ce qui est figé ne change plus après le
premier run de test ; toute analyse ajoutée ensuite est marquée « exploratoire ».

## 0. Règles de choix des variantes, fixées le 2026-10-27, avant les résultats de la phase A

Ces règles servent à choisir les variantes sur les graines de validation. Elles sont écrites et
committées avant le premier épisode de la phase A, et ne changent plus.

**Références.** Dans chaque case (réseau, scénario, demande), la meilleure référence est, pour
chaque métrique, la meilleure des références MP, EV-RULE-MP, COOP-FULL (moyenne des 3 modèles)
et TEAM-RULES ; PED-RULE-MP s'y ajoute dans le scénario piétons.

**Comparaison d'une variante à la meilleure référence**, pour chaque case et chaque métrique
(temps de trajet moyen, attente moyenne), sur les 3 modèles COOP-FULL de la variante ; l'écart
est relatif à la meilleure référence, positif quand la variante est pire :

- **meilleure ou égale** : la moyenne sur les 3 modèles n'est pas pire de plus de 1 % ;
- **incertaine** : pire de 1 à 3 % en moyenne, sans être pire sur les 3 modèles à la fois ;
- **pire** : pire de plus de 3 % en moyenne, ou pire de plus de 1 % sur les 3 modèles à la fois.

Une case compte comme « meilleure ou égale » pour une variante seulement si les deux métriques
le sont ; elle compte comme « pire » si l'une des deux l'est.

**Classement**, dans cet ordre :

1. le plus grand nombre de cases « meilleure ou égale » ;
2. puis le plus petit nombre de cases « pire » ;
3. puis le plus petit retard moyen des ambulances (cases urgences) ;
4. puis la plus petite attente moyenne des piétons (cases piétons).

**Contre la chance d'une graine.** Après la phase A (graine 1000), les 3 ou 4 premières
variantes du classement et les références sont rejouées sur les graines de validation 1001 et
1002, avec les mêmes règles. La candidate finale doit rester en tête du classement sur chacune
des trois graines. Les graines 1001 et 1002 ne sont ni d'entraînement (100000 et plus) ni de
test (0 à 999) ; la graine 1001 a servi une fois, à une étude exploratoire sur IND et DQN
(journal d'expériences), jamais à COOP-FULL ni à cette étude ; la graine 1002 n'a jamais servi.

**Phase B : l'oracle de stratégie** (fixé le 2026-10-28, après le classement de la phase A et
avant le premier épisode de la phase B). À chaque fenêtre de 300 s, l'oracle choisit un mode
pour tout le réseau parmi K = 3 : COOP-FULL, MP partout, et le meilleur hybride du classement
de la graine 1000 (H2, β = 4), tous avec la préemption EV-RULE et le bouclier. Chaque mode est
joué depuis le début de l'épisode (le planning déjà choisi, le mode sur la fenêtre, puis 300 s
de COOP-FULL, la même suite pour les trois modes) ; le mode de plus petit coût sur la fenêtre
et la suite est retenu. Coût : attente des véhicules (véh·s) + 10 × temps d'arrêt des
ambulances (s) + attente des piétons (personne·s), sur tout le réseau. On rejoue depuis le
début plutôt que depuis un instantané SUMO, parce qu'un état restauré s'écarte de l'épisode
ininterrompu (src/cotraffic/llm/snapshot.py) : l'oracle planifierait sur une autre trajectoire
que celle où il est mesuré. Le planning retenu est rejoué dans un épisode ordinaire, qui donne
les métriques. Le placebo joue, par case, 3 plannings tirés uniformément au hasard ; le
« meilleur du hasard » est le meilleur des 3 sur la métrique considérée.

Version rapide : modèle t1 seul, graine 1000, les 14 cases. **On continue vers la phase B
complète et la phase C seulement si, dans au moins 4 des 14 cases, l'oracle bat le meilleur
hybride fixe (H2, β = 4, même modèle t1) de plus de 3 % sur le temps de trajet ou sur
l'attente, et bat aussi le meilleur du hasard de plus de 3 % sur la même métrique.** Sinon,
on passe à la phase D sans couche de stratégie. Le rapport donne aussi, par case, l'écart au
meilleur des trois modes fixes et la part des fenêtres de chaque mode ; ils ne changent pas
la décision.

**Rapport.** Toutes les variantes essayées sont rapportées, pas seulement la meilleure.

## Brouillon de l'étape 4 (remplacé en phase D)

Les sections suivantes sont le brouillon écrit après l'étape 4 ; elles seront réécrites en
phase D (variantes finales, références, scénarios, famille « hybrid »).

## 1. Question

Guider COOP-FULL pendant les urgences avec une règle de préemption, sans aucun LLM :

1. réduit-il le retard des ambulances ;
2. sans coûter aux autres véhicules (attente, temps de trajet) ;
3. et les règles d'urgence du coéquipier (le travail de notre coéquipier,
   `src/cotraffic/controllers/llm_team/PROVENANCE.md`) apportent-elles quelque chose de plus que
   notre règle EV-RULE ?

Origine de la question, dite honnêtement : l'intérêt pour les urgences vient des résultats de
test de l'étude principale (retard des ambulances sur grid4x4 en pointe : COOP-FULL 73,5 s,
EV-RULE-MP 38,1 s). Les variantes et leurs paramètres ont été choisis sur la graine de
validation 1000 seulement (section 3).

## 2. Mécanisme (code figé)

`src/cotraffic/controllers/combined.py` :

- un **guide** dit, à chaque décision, quels carrefours doivent servir une ambulance, et avec
  quelle phase :
  - **EV-RULE** : l'ambulance est à moins de `ev_preemption_range_m` = 200 m de son prochain feu
    (`configs/protocol.yaml`), comme EV-RULE-MP ;
  - **ses règles** : le code de son équipe sur le backend `mock`, donc sans LLM, sans base de
    décision propre. Un carrefour n'est guidé que pendant une de ses fenêtres de préemption :
    corridor sur les 3 prochains feux, avance, durée de maintien ;
- deux façons d'appliquer le guide à COOP-FULL, toujours **avant notre bouclier** :
  - **A′ biais** : + β sur le logit de la phase guidée ;
  - **B′ commutation** : la phase guidée remplace celle de PPO, aux seuls carrefours guidés.

Sans ambulance, aucun carrefour n'est guidé et la politique est COOP-FULL elle-même (test
`tests/test_combined.py`). Les scénarios sans ambulance ne sont donc pas évalués.

## 3. Ce qui a été choisi sur la validation (graine 1000)

Source : `results/exploration/combined/guides.md` (commit `af36352`), 3 modèles COOP-FULL,
4 cases urgences. Observations qui fixent le choix :

- avec EV-RULE, β = 8 et β = 16 donnent exactement les mêmes épisodes que la commutation :
  le biais dépasse toujours l'écart de logits de PPO ; avec ses règles, β = 16 donne exactement
  la commutation. Le vrai choix est donc entre **β = 4 (biais doux)** et **la commutation** ;
- grid4x4 : retard moyen des ambulances (9 valeurs : 3 modèles x 3 ambulances) contre
  COOP-FULL 42,5 s (moyenne) et 55,0 s (pointe) :
  - EV-RULE, commutation : 21,4 s et 35,2 s ; coût en attente +1,1 % en pointe (« net ») ;
  - EV-RULE, β = 4 : 27,8 s et 47,3 s ; coût dans le bruit ;
  - ses règles, commutation : 19,6 s et 39,1 s ; coût +1,4 % en pointe (« net ») ;
  - ses règles, β = 4 : 27,8 s et 47,4 s, quasi identique à EV-RULE β = 4 ;
- real_district : aucun effet distinguable du bruit, pour aucune variante (10 à 13 décisions
  guidées, 1 à 3 changées par épisode).

## 4. Configurations retenues (figées)

| Code | Variante | Méthode (`scripts/combined_eval.py`) | β |
|---|---|---|---|
| V1 | COOP-FULL + EV-RULE, commutation (B′) | `coop_full_evrule_switch` | – |
| V2 | COOP-FULL + EV-RULE, biais doux (A′) | `coop_full_evrule_bias` | 4 |
| V3 | COOP-FULL + ses règles, commutation (B′) | `coop_full_team_switch` | – |

Références : COOP-FULL seul (mêmes 3 modèles), MP, EV-RULE-MP, TEAM-RULES (contexte).

## 5. Protocole

- Cases : scénario urgences ; grid4x4 en demande moyenne et en pointe ; real_district en
  demande moyenne et en pointe.
- Graines de test 0 à 4, protocole d'évaluation (`configs/protocol.yaml` : 900 s de chauffe,
  3 600 s mesurées, 900 s de vidange).
- COOP-FULL et V1 à V3 : modèles entraînés 1, 2 et 3, donc 15 épisodes par case ; MP,
  EV-RULE-MP, TEAM-RULES : 5 épisodes par case.
- Total : 4 cases x (4 x 15 + 3 x 5) = **300 épisodes**, sans LLM.
- Sorties : `results/combined/` (jamais `results/raw`). Chaque ligne enregistre le commit, le
  mécanisme, la provenance et le retard de chaque ambulance. Les runs refusent un arbre git
  modifié.

## 6. Métriques

- `ev_delay` (principale) : retard moyen des ambulances de l'épisode (temps perdu). Le retard
  de chaque ambulance (`ev_delays`) et leur nombre par case sont rapportés.
- `mean_waiting_time` : attente de tous les véhicules (les ambulances pèsent moins de 0,2 %).
- `others_travel_time` : temps de trajet des véhicules autres que les ambulances, calculé
  exactement en retirant les ambulances de la moyenne.
- Rapportées sans test : décisions guidées et décisions changées, préemptions, véhicules
  non arrivés, téléportations.

## 7. Hypothèses et tests (famille de Holm « combined »)

Pour chaque case (4) et chaque métrique (3) :

- **H1 à H3** : V1, V2, V3 contre COOP-FULL (36 tests) ;
- **H4, la question clé** : V3 contre V1 (12 tests).

Total : **48 tests, une seule famille de Holm « combined »**, α = 0,05, séparée des familles
existantes. Le code statistique est celui du projet (`cotraffic.analysis.aggregate.compare`,
`cotraffic.analysis.stats`) :

- Mann-Whitney U bilatéral sur les épisodes (15 contre 15) ;
- gain apparié par graine de test (moyenne sur les modèles), IC bootstrap à 95 % ;
- delta de Cliff ;
- convention : gain positif = mieux.

## 8. Règles de décision (figées)

- **Gain sur les ambulances** pour une variante dans une case : `ev_delay` meilleur que
  COOP-FULL, significatif après Holm.
- **Coût pour les autres véhicules** : `mean_waiting_time` ou `others_travel_time` pire que
  COOP-FULL, significatif après Holm. Un coût non significatif est rapporté avec son IC.
- **Combinaison retenue** : une variante avec un gain sur les ambulances dans les deux cases
  grid4x4, et aucun coût significatif dans aucune case. Si plusieurs variantes le satisfont :
  la plus forte réduction moyenne du retard sur grid4x4 ; à égalité non significative entre
  V3 et V1, **V1** (plus simple, déjà dans le projet).
- **Réponse à la question clé** : ses règles apportent quelque chose de plus si V3 est
  meilleure que V1 sur `ev_delay`, significatif après Holm, dans au moins une case grid4x4,
  sans coût significatif de V3 contre V1. Sinon : « pas de différence démontrée ».
- real_district : sur la validation, aucun effet n'est attendu ; le résultat est rapporté
  tel quel, sans réglage.

## 9. Durée estimée

Mesurée sur la relance de l'étape 4 (104 épisodes de validation : 51 min, 4 en parallèle) et
doublée pour la longueur d'un épisode d'évaluation : environ **4 h 30** (fourchette 4 à 5 h 30),
dont grid4x4 en pointe environ la moitié. Aucun LLM : pas de latence à protéger, mais aucun
autre calcul pendant le run.

## 10. Limites connues

- 3 à 5 ambulances par épisode : la variance du retard est grande ; la significativité repose
  sur 15 contre 15 épisodes.
- Une seule demande de validation a servi aux choix ; real_district n'a montré aucun effet.
- La commutation (V1, V3) a montré en validation un coût faible mais régulier en pointe
  (+1,1 à +1,4 % d'attente) : c'est précisément ce que les tests de coût doivent trancher.
