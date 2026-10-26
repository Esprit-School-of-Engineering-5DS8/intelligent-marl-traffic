# Pré-enregistrement : évaluation du LLM dans la boucle

Écrit le 26/10/2026, **avant toute exécution sur les graines de test 0 à 4**, et figé par
le commit qui ajoute ce fichier. Tous les réglages ci-dessous ont été choisis sur la graine
de validation 1000 (et les exemples few-shot sur la graine d'entraînement 100001). Aucune
graine de test n'a servi à régler quoi que ce soit. Toute déviation sera signalée dans
`docs/LLM_RESULTS.md`, avec sa raison.

Convention : **gain positif = mieux** (moins d'attente que COOP-FULL seul).

## 1. Question et hypothèses

Question : un LLM local, qui conseille rarement les agents PPO (biais borné, bouclier en
dernier recours), améliore-t-il leurs scores dans les situations rares ?

| Hypothèse | Énoncé | Ce qu'on attend, d'après la validation |
|---|---|---|
| H1 | COOP-FULL + LLM réduit le temps d'attente moyen par rapport à COOP-FULL seul, dans au moins un scénario prioritaire | Pas de gain : sur la validation, le gain moyen est de −0,4 % (épisodes complets) à +0,3 % (situations) |
| H2 | COOP-FULL + LLM fait mieux que le placebo (conseils aléatoires de même fréquence et de même amplitude) | Inconnu : le placebo n'a été mesuré que sur les situations |
| H3 | COOP-FULL + LLM fait au moins aussi bien que le conseiller à règles | Probable : les règles n'apportent pas de gain non plus |

L'hypothèse nulle (aucun effet) est le résultat attendu. Elle sera rapportée telle quelle.

## 2. Réglage figé (configs/llm.yaml)

| Élément | Valeur |
|---|---|
| Modèle | `qwen2.5:3b`, Q4_K_M, digest `357c53fb659c…` (enregistré dans chaque ligne) |
| Prompt | `advisor-v2`, technique `zero` (identifiant avec empreinte du texte dans chaque ligne) |
| Échantillonnage | température 0, top_p 1, top_k 1, repeat_penalty 1, seed 0 |
| Contexte et sortie | num_ctx 4096, num_predict 96, timeout 60 s, keep_alive 30 min |
| Mécanisme | biais `beta × force / 3` sur les logits de COOP-FULL, beta = 4 |
| Appels | à chaque nouvel événement, et toutes les N = 10 min ; au plus 1 appel / 30 s |
| Latence | mesurée (le conseil agit à t + latence réelle de l'appel) |
| Cache, vote | désactivés |

## 3. Contrôleurs comparés

| Contrôleur | Définition |
|---|---|
| COOP-FULL seul | Référence (runs existants, plus les runs manquants sur capteurs bruités et pertes de messages à 30 %) |
| + LLM | Réglage figé ci-dessus |
| + placebo | `RandomSource` : même fréquence d'appel, même nombre de carrefours conseillés, mêmes forces et mêmes durées que les conseils du LLM sur la validation (distributions tirées de `results/exploration/llm_benchmark/v2_tech_calls.csv`), carrefours et phases au hasard ; graine `10000 + graine de l'épisode` |
| + règles | `RuleSource` : les principes du prompt écrits en règles (couloir vert, accident, capteur, piétons, file négligée) ; même mécanisme et même fréquence |
| + LLM LoRA | Seulement si l'adaptateur est prêt et converti avant le lancement ; sinon exclu, et signalé |
| Oracle | Au niveau des situations seulement (section 5) : le meilleur conseil candidat, choisi après coup par rejeu |

**Même latence pour tous** : le placebo et les règles répondent instantanément ; pour une
comparaison juste, leurs conseils sont retardés de la latence médiane du LLM sur la
validation (8,2 s, `latency: fixed:8.2`). Dans le benchmark de l'étape 2, les règles
avaient été rejouées sans délai, ce qui les avantageait.

## 4. Niveau 1, confirmatoire : épisodes complets

- Réseau `grid4x4`, demande `peak`, protocole d'évaluation (900 s de chauffe, 3 600 s
  mesurées, 900 s de fin).
- Scénarios, par priorité : `incident`, `emergency`, `sensor_noise`, `comm_dropout_30`,
  `pedestrians`, puis `normal` (pour vérifier l'absence de dégradation).
- 15 runs par cellule : les 3 modèles COOP-FULL entraînés (seed1 à seed3) × les graines de
  test 0 à 4.
- Métrique principale : `mean_waiting_time`, gain en % par rapport à COOP-FULL seul.
- Métriques secondaires : `ev_delay` (urgences), `ped_mean_waiting_time` (piétons),
  `p95_waiting_time`, `mean_travel_time`, `throughput_per_h`.
- Sécurité : interventions du bouclier, téléportations.
- Coût du LLM : appels, taux de validité, latence p50 et p95, replis, décisions changées.

## 5. Niveau 2, exploratoire : situations appariées

Les situations où le conseiller serait appelé sont enregistrées sur les épisodes COOP-FULL
des graines de test 0 à 4 (même enregistreur que pour la validation). Chacune est rejouée
300 s depuis son instantané SUMO avec : aucun conseil, LLM, placebo (3 tirages), règles,
oracle (le meilleur de tous les candidats). La différence avec « aucun conseil » est
appariée : même départ, même trafic.

## 6. Statistiques (protocole du projet)

- Test de Mann-Whitney bilatéral entre les 15 runs d'un contrôleur et les 15 runs de
  COOP-FULL seul, cellule par cellule (`src/cotraffic/analysis/stats.py`).
- Correction de Holm dans une **famille « llm »** séparée : LLM contre COOP-FULL, LLM contre
  placebo, LLM contre règles, sur la métrique principale et les 6 scénarios (18 tests).
- Les nouveaux runs de COOP-FULL seul (capteurs bruités, pertes de messages) forment une
  **famille Holm séparée « coopfull_robustness »**, pas dans `core` : ils ne peuvent pas
  changer les p-valeurs du rapport.
- Seuil 0,05 après correction ; intervalle de confiance à 95 % par bootstrap croisé
  (modèles × graines) ; taille d'effet de Cliff.
- **Critère « le LLM améliore un scénario »** : gain positif, p de Holm < 0,05 contre
  COOP-FULL seul, intervalle de confiance qui exclut 0, et p de Holm < 0,05 contre le
  placebo. Sinon le scénario est rapporté comme « pas d'amélioration ».

## 7. Analyse de sensibilité à la latence (exploratoire)

Pour le réglage figé : délai nul (`latency: zero`), délai mesuré, délai doublé
(`latency: double`), sur `incident` et `emergency`, 5 runs (modèle seed1, graines 0 à 4).
Famille Holm « llm_latency », exploratoire. Elle dit si un LLM plus rapide changerait la
conclusion.

## 8. Règles de conduite

- Un run qui échoue (erreur, coupure, mise en veille) est relancé une fois avec la même
  graine ; les deux sont signalés. Un appel qui expire à cause d'une mise en veille est
  signalé et l'épisode rejoué.
- Aucun réglage ne change après le lancement. Si un réglage devait changer, tous les runs
  concernés seraient relancés, et la déviation documentée.
- Chaque ligne de résultat enregistre : commit git, modèle et digest, identifiant du prompt,
  hyperparamètres, mécanisme d'intervention, latence de chaque appel.
- Les résultats vont dans des fichiers dédiés (`results/llm/`), jamais dans `results/raw`.

## 9. Coût estimé et plan réduit

| Lot | Runs | Temps estimé |
|---|---|---|
| COOP-FULL seul, runs manquants (capteurs, pertes de messages) | 30 | 1 h |
| + LLM, 6 scénarios | 90 | 9 h (un épisode à la fois, pour une latence honnête) |
| + placebo et + règles | 180 | 9 h (3 en parallèle) |
| Situations appariées (5 graines, 4 candidats et l'oracle) | environ 1 500 rejeux | 3 h |
| Sensibilité à la latence | 20 | 2 h |
| **Total** | | **environ 24 à 28 h** |

Plan réduit, si le temps manque : les 4 scénarios prioritaires, sans `pedestrians` ni
`normal`, et la sensibilité à la latence sur `incident` seulement (environ 16 h).
