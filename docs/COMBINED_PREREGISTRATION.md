# Pré-enregistrement de l'étude combinée

**Statut : gelé le 2026-10-29** (section « Pré-enregistrement final »). Aucun épisode sur les
graines de test 0 à 4 n'a été lancé avant le commit qui fige cette version finale (phase D). Ce qui est figé ne change plus après le
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

## Pré-enregistrement final (phase D), écrit le 2026-10-29 avant toute graine de test

**Gelé le 2026-10-29 à 11 h 40, validé par l'équipe.** Le commit qui contient cette ligne est
celui qu'on donne à `--prereg` (section 6). Décisions de l'équipe à la validation : F-H3 est
retirée des 4 cases nouvelles (section 4) ; F-H1 est gardée (famille d'ablation, sans effet sur
les tests principaux) ; chaque échec de non-infériorité est classé « vraie perte » ou
« intervalle trop large pour conclure », et l'analyse s'ouvre sur une phrase qui dit ce qu'on
peut affirmer et ce qu'on ne peut pas affirmer (section 9).

Les sections 1 à 11 remplacent le brouillon de l'étape 4. La section 0 (règles de choix,
critère de la phase B) ne change pas. Rien de ce qui suit n'a été réglé sur les graines de
test 0 à 4 : tous les choix viennent des graines de validation 1000, 1001 et 1002.

## 1. Question

Un contrôleur qui combine COOP-FULL, Max-Pressure (MP) et la préemption des ambulances, sans
LLM dans la décision, est-il, sur des graines jamais vues :

1. **jamais moins bon que la meilleure référence** (MP, EV-RULE-MP, COOP-FULL, TEAM-RULES ;
   PED-RULE-MP en plus dans le scénario piétons), à 2 % près, sur le temps de trajet et sur
   l'attente, dans chaque case ;
2. **meilleur** qu'elle, là où c'est possible ;
3. robuste (bus, capteurs bruités, pertes de messages) et transférable (grid8x8, sans
   réentraînement) ?

Question secondaire, sans valeur de preuve : que fait le conseiller LLM local quand on
l'ajoute à ce contrôleur, sur une case de test ?

## 2. Ce qui a été essayé sur la validation, et choisi

Toutes les variantes essayées sont rapportées (`results/exploration/combined/`).

| Étape | Variantes | Graines | Résultat |
|---|---|---|---|
| Étape 4 | guides d'urgence A′ (biais β = 4, 8, 16) et B′ (commutation), EV-RULE et ses règles | 1000 | `guides.md` ; V1 = EV-RULE en commutation |
| Phase A | H1 (4 seuils), H2 (β = 1, 2, 4), ses règles piétons, PED-RULE, V1 | 1000 | `rank_s1000.md` : H2 β = 4 premier (7 / 2 / 5) |
| Revérification | H2 β = 2 et 4, V1, PED-RULE, toutes les références | 1001, 1002 | `rank_s1001.md`, `rank_s1002.md` : H2 β = 4 premier sur les deux |
| Phase B | oracle de stratégie et placebo (modèle t1) | 1000 | `oracle_s1000.md` : 3 cases sur 14, arrêt (section 0) |
| Lot H3 | H3 (seuils q75, q90, q95, plancher 1 véhicule), H2 β = 8 | 1000, 1001, 1002 | `rank_s100*.md` : H2 β = 4 reste en tête (voir ci-dessous) |

**Candidate : H2 β = 4** (COOP-FULL + biais vers MP, β = 4, + EV-RULE en commutation),
première du classement sur chacune des trois graines de validation (règle de la section 0) :

- H3 l'égale exactement sur 1001 et 1002, et ne passe devant sur 1000 qu'au départage
  (retard des ambulances 30,8 s contre 31,1 s). 106 de ses 126 épisodes au quantile 90 % sont
  ceux de H2 β = 4 (aucune bascule) ; là où elle bascule (real_district en pointe), elle fait
  moins bien (trajet −0,9 à −1,3 %, attente −3,7 à −6,3 %). Basculer sur MP quand la file
  d'entrée s'est formée arrive trop tard : MP gagne en l'empêchant de se former. H3 ne
  devient donc pas la candidate (règle fixée par l'équipe le 2026-10-28) ;
- H2 β = 8 est sous β = 4 sur les trois graines : la tendance β = 1 < 2 < 4 s'arrête, β = 4
  est figé.

**Variantes finales**, la meilleure de chaque famille sur les trois graines, et V1 :

| Code | Variante | Famille | Méthode (`scripts/combined_eval.py`) |
|---|---|---|---|
| C | H2 β = 4 + EV-RULE | candidate (et meilleure H2) | `hybrid_h2` β = 4 |
| F-H1 | H1, quantile 90 % | bascule par carrefour | `hybrid_h1` q90 |
| F-H3 | H3, quantile 90 % (14 cases principales) | bascule réseau sur file d'entrée | `hybrid_h3` q90 |
| F-PED | COOP-FULL + EV-RULE + PED-RULE | règles piétons | `coop_full_pedrule_switch` |
| V1 | COOP-FULL + EV-RULE, commutation | préemption seule | `coop_full_evrule_switch` |

La candidate est aussi la meilleure de la famille H2 : elle n'est jouée qu'une fois. F-H1 n'a
été classée que sur la graine 1000 (la revérification ne prenait que les 4 premières).

## 3. Mécanisme et code figés

Commit du gel (celui de ce document, donné à `--prereg`), `src/cotraffic/controllers/hybrid.py` : stratégie, tactique, préemption,
bouclier (section « The layered controller »). H3 : toutes les 300 s, si la file d'entrée
moyenne de la dernière minute (véhicules que SUMO n'a pas encore pu insérer) dépasse le
seuil, MP décide à tous les carrefours pendant 300 s ; sinon H2 β = 4. Seuils :
`results/exploration/combined/backlog_thresholds.json`, appliqués comme
max(quantile, 1 véhicle). H1 : `congestion_thresholds.json`. Sur grid8x8, réseau sans profil,
H1 et H3 prennent les seuils de grid4x4, le réseau d'entraînement des modèles.

## 4. Contrôleurs évalués sur les graines de test

- Variantes finales (section 2), chacune avec les modèles COOP-FULL 1, 2 et 3.
- Références : MP, EV-RULE-MP, COOP-FULL (modèles 1, 2, 3), TEAM-RULES (backend `mock`, sans
  LLM) ; PED-RULE-MP dans le scénario piétons.
- Un contrôleur identique par construction à un autre dans une case n'y est pas rejoué : il
  reprend ses épisodes (comme dans le classement, marque « = ») :
  - sans ambulance, V1 et EV-RULE-MP sont COOP-FULL et MP ;
  - sans ambulance ni piéton, TEAM-RULES est MP (épisodes identiques dans toutes ces cases
    des graines de validation, les 4 cases nouvelles comprises) ;
  - sans piéton, F-PED est V1 (urgences) ou COOP-FULL.
- F-H3 n'est pas jouée dans les 4 cases nouvelles (décision de l'équipe à la validation) : sur
  la graine de validation, elle n'y a jamais basculé (0 % des périodes en MP) et ses 12
  épisodes y sont exactement ceux de H2 β = 4.
- **Secondaire** : la candidate + le conseiller LLM (qwen2.5:3b local, `configs/llm.yaml`
  actuel, latence mesurée appliquée), sur la seule case grid4x4 urgences pointe, modèle t1,
  graines 0 à 4. Ses épisodes tournent seuls, après tous les autres.

## 5. Cases

- **Principales (14)** : grid4x4 et real_district x normal, urgences, incident x demande
  moyenne et pointe ; grid4x4 x piétons x moyenne et pointe.
- **Robustesse (3)**, grid4x4 : capteurs bruités en pointe, pertes de messages 30 % en
  pointe, bus en demande moyenne (les cases de robustesse de l'étude principale).
- **Généralisation (1)** : grid8x8 en pointe, scénario normal, modèles entraînés sur grid4x4.

Avant les graines de test, chaque contrôleur a été joué une fois sur la graine de validation
1000 dans les 4 cases nouvelles, pour vérifier qu'il tourne (2026-10-29, commit `00327fd`) :
60 épisodes, aucun plantage, COOP-FULL tourne sur grid8x8 sans réentraînement. Rien n'y a
été réglé.

## 6. Protocole

- Graines de test 0 à 4, épisodes d'évaluation (`configs/protocol.yaml` : 900 s de chauffe,
  3 600 s mesurées, 900 s de vidange).
- libsumo (mêmes épisodes que TraCI, `scripts/backend_check.py`).
- Exécution : `python scripts/combined_final.py --prereg <commit du gel>`, qui contient ce plan
  écrit en clair (contrôleurs, cases, graines). Sorties : `results/combined/` (jamais
  `results/raw`). Chaque ligne enregistre le commit et le moteur. Le script refuse de
  démarrer si ce document, `src/cotraffic`, `configs`, les scripts d'évaluation ou les seuils
  diffèrent du commit du gel, ou si l'arbre est modifié ; il ne rejoue jamais un épisode déjà
  écrit. Aucun fichier suivi n'est modifié pendant l'exécution.
- Analyse : `python scripts/combined_analysis.py` (`results/combined/analysis.md`), écrite et
  figée avec ce document, vérifiée sur les données de validation.
- Une seule exécution. Un épisode qui plante est rejoué tel quel (même graine, même code) ;
  tout plantage est rapporté.

## 7. Métriques

- **Principales** : `mean_travel_time`, `mean_waiting_time`.
- **Secondaires, sans test de Holm** : retard de chaque ambulance (`ev_delay`, `ev_delays`),
  attente des piétons, trajet des autres véhicules, débit, CO2, téléportations, véhicules
  non insérés, part des décisions de chaque couche.
- **LLM** (variante secondaire) : latence p50 / p95, JSON valides, replis, conseils modifiés
  par la validation ou le bouclier, appels par heure simulée, tokens.

## 8. Hypothèses et tests

Écart relatif, positif = mieux : gain = (référence − contrôleur) / référence. Dans chaque case
et pour chaque métrique, **la meilleure référence est celle de meilleure moyenne sur les
graines de test** (choix conservateur : il ne peut que rendre la preuve plus difficile).
Dans les cases où EV-RULE-MP ou TEAM-RULES sont identiques à MP par construction (section 4),
ils reprennent les épisodes de MP.

Appariement : par graine de test ; quand la meilleure référence est COOP-FULL, construite sur
les mêmes 3 modèles que la candidate, par modèle et par graine. Bootstrap croisé (modèles x
graines rééchantillonnés, 10 000 tirages, graine 0), comme
`cotraffic.analysis.stats.paired_change_ci` ; IC à 95 % par les percentiles. p unilatéral de
non-infériorité = (1 + nombre de tirages où le gain ≤ −2 %) / (1 + 10 000) ; de supériorité,
la même chose avec 0 au lieu de −2 %.

- **Famille de Holm « hybrid » (principale)** : la candidate contre la meilleure référence,
  18 cases x 2 métriques = **36 tests de non-infériorité**. H0 : gain ≤ −2 %. Non-infériorité
  démontrée si la borne basse de l'IC à 95 % est au-dessus de −2 %, équivalent à p < 0,025
  unilatéral ; p bootstrap unilatéral, Holm sur les 36, α = 0,025.
- **Famille « hybrid-sup » (secondaire)** : les mêmes 36 comparaisons, H0 : gain ≤ 0
  (supériorité), Holm sur les 36, α = 0,025 unilatéral.
- **Famille « hybrid-ablation » (exploratoire)** : chacune des autres variantes finales
  contre la meilleure référence, même test de non-infériorité, Holm dans la famille ; et le
  tableau d'ablation des couches (COOP-FULL → V1 : préemption ; → H2 : biais MP ; → H3 :
  bascule sur saturation), sans test de Holm.
- Rapportés aussi, comme dans l'étude principale : Mann-Whitney sur les épisodes, delta de
  Cliff.
- **Variante LLM** : 5 paires (graines) contre la candidate seule, modèle t1 ; gain apparié et
  IC, sans test de Holm (5 paires ne suffisent pas à une preuve).

## 9. Règles de décision

- « Jamais moins bon que la meilleure référence » n'est affirmé que si les **36** tests de
  non-infériorité passent après Holm. Sinon, le rapport donne, case par case, où il est
  démontré, où il ne l'est pas, et l'IC.
- « Non démontré » ne veut pas dire « pire ». Chaque test de non-infériorité qui échoue est
  classé :
  - **vraie perte** si la borne haute de l'IC du gain est elle aussi sous 0 (marquée « au-delà
    de −2 % » si elle est sous −2 %) ;
  - sinon **intervalle trop large pour conclure** : avec 5 graines, un IC large peut empêcher
    la preuve.
- L'analyse s'ouvre sur une phrase : ce qu'on peut affirmer, et ce qu'on ne peut pas affirmer.
- « Meilleur » n'est affirmé que dans les cases où la supériorité passe après Holm.
- Le LLM : effet rapporté avec son IC, et ses métriques ; aucune conclusion générale.

## 10. Durée estimée

Mesurée sur la validation (libsumo, 4 épisodes en parallèle ; un épisode d'évaluation compte
pour deux de validation ; grid8x8 et robustesse mesurées sur la graine 1000) :

| Partie | Épisodes | Durée |
|---|---|---|
| Sans LLM, 4 en parallèle | 1 260 | environ 11,6 h (dont grid8x8 2 h, grid4x4 piétons pointe 1,9 h) |
| Avec le LLM, seuls, à la fin | 5 | environ 25 min (247 s par épisode mesuré, 12 appels) |
| **Total** | **1 265** | **environ 12 h** |

Retiré à la validation : F-H3 dans les 4 cases nouvelles (60 épisodes, 1,0 h). Gardé : F-H1
partout (270 épisodes, 2,7 h).

## 11. Limites connues

- **Oracle de stratégie (phase B)** : son coût ne compte que l'attente des véhicules déjà
  dans le réseau, pas la file d'entrée. Dans les cases saturées, il a appris à garder les
  véhicules dehors. real_district en pointe, graine 1000, modèle t1 :

  | Cas | Trajet oracle / H2 β = 4 / MP (s) | File d'entrée oracle / H2 β = 4 / MP |
  |---|---|---|
  | normal | 159 / 153 / 145 | 9,4 / 8,0 / 2,0 |
  | urgences | 164 / 157 / 145 | 14,5 / 11,7 / 2,6 |
  | incident | 176 / 162 / 144 | 24,9 / 13,9 / 5,3 |

  Il y fait pire que le meilleur hybride fixe (−4 à −9 % de trajet) et que MP (−10 à −22 %).
  Dans les cases saturées, il **sous-estime donc la marge** d'une couche de stratégie ; le
  verdict de la phase B (3 cases sur 14) est un minorant là-bas. Dans les cases sans file
  d'entrée (toutes les demandes moyennes), il fait ce qui est attendu. H3 a été conçu pour
  ces cases saturées.
- **Instantanés SUMO** : un état restauré s'écarte de l'épisode ininterrompu (SUMO 1.27.1) ;
  l'oracle rejoue donc tout depuis le début (`src/cotraffic/llm/snapshot.py`).
- H3 lit la file d'entrée dans SUMO, sans bruit, même dans le scénario capteurs bruités : sur
  le terrain, il faudrait la mesurer (boucles en amont des entrées).
- 5 graines de test et 3 modèles : les IC restent larges ; la preuve de non-infériorité peut
  manquer de puissance.
- Graines de test déjà jouées par l'étude principale pour les références ; les variantes de
  cette étude ne l'ont jamais été.
- Les lignes de validation d'avant la colonne `sumo_backend` ont tourné sur TraCI, les
  suivantes sur libsumo (mêmes épisodes, vérifié sur 8 épisodes).

Le brouillon de l'étape 4 (V1 à V3, 48 tests) est remplacé par ce document ; il reste
dans l'historique git (commit `7bd689e`).
