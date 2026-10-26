# Validation : le LLM dans la boucle de décision des agents

Document de validation de la partie « LLM dans la boucle » de CoTraffic : pour chaque
exigence, ce qui a été fait, où c'est dans le code, comment le montrer, et la preuve.

**Convention : gain positif = mieux** (moins d'attente que COOP-FULL seul, comme dans le
tableau de bord). **Tous les chiffres sont des résultats de validation (graine 1000)**,
sauf mention contraire. Les graines de test 0 à 4 n'ont servi à rien régler, et
l'évaluation sur ces graines n'est pas encore faite (section 7).

## En bref

Un LLM local (`qwen2.5:3b`, via Ollama, sans aucune donnée envoyée à l'extérieur) est
appelé rarement : à chaque nouvel événement (ambulance, accident, capteur en panne, pertes
de messages, foule de piétons) et toutes les 10 minutes. Son conseil devient un **biais
borné** sur les logits des agents PPO (COOP-FULL). Ce biais n'agit qu'après la latence
réelle de l'appel, et le **bouclier de sécurité garde le dernier mot**.

Tout fonctionne de bout en bout et c'est testé. Mais, sur la validation, **le LLM
n'améliore pas les scores** : les gains vont de −0,4 % à +0,3 %, dans le bruit. Ce document
le dit, montre pourquoi, et liste ce qui a été essayé pour l'améliorer.

État des tests au 26/10/2026 : **pytest 200 / 200**, **Vitest 110 / 110**,
**Playwright 37 / 37** (la suite compte 37 tests ; le chiffre de 38 donné dans l'audit
était une erreur de comptage).

---

## 1. Tableau des exigences

| Exigence | Ce qui a été fait | Fichier:lignes | Commande de démo | Preuve (test ou chiffre) | Statut |
|---|---|---|---|---|---|
| 1. Le LLM intervient dans la décision des agents | Le conseil devient un biais sur les logits PPO ; le bouclier filtre ensuite | `src/cotraffic/llm/advised.py:189-198` (PPO seul, biais, décision) ; `src/cotraffic/envs/traffic_env.py:190` (bouclier) | `python scripts/llm_demo.py` (environ 2 min) | Démo : 106 décisions sous conseil, 6 changées par le conseil, 51 demandes corrigées par le bouclier. Tests `test_advice_applies_only_after_its_latency_and_expires`, `test_weak_advice_does_not_overturn_a_clear_preference` | **FAIT** (mécanisme) ; gain non démontré |
| 2. LLM choisi | 8 modèles de 0,5B à 3,8B, testés sur 63 situations ; règle de choix fixée avant les résultats | `scripts/llm_benchmark.py` ; règle `scripts/llm_step2.py:73` ; `configs/llm.yaml:8-20` | `type results\exploration\llm_benchmark\v2_zero_summary.csv` | qwen2.5:3b : 100 % de JSON valide, latence p50 8,6 s, gain +0,29 % (dans le bruit) | **FAIT** |
| 3. Hyperparamètres | Un fichier unique ; chaque valeur est justifiée par une mesure | `configs/llm.yaml` ; lecture `src/cotraffic/llm/settings.py:29` | `Get-Content configs\llm.yaml` | `test_code_defaults_match_the_settings_file`. Calibration : beta 8 donne −1,2 % ; N = 3 min donne −5,0 % | **FAIT** |
| 4. Prompt engineering | Prompt versionné (v1, v2) ; données balisées ; zero, brief, few-shot (exemples des graines d'entraînement) ; self-consistency ; décodage contraint par schéma | `configs/prompts/advisor-v2.yaml` ; `src/cotraffic/llm/prompts.py:23-82` ; `scripts/llm_fewshot.py` ; `src/cotraffic/llm/sources.py:103` (vote) ; `src/cotraffic/llm/advice.py:45` (schéma) | `type results\exploration\llm_benchmark\v2_tech_summary.csv` | v1 → v2 : JSON valide de 67 à 100 % (modèles 3B). Zero +0,15 %, brief −0,18 %, few +0,08 %, vote +0,02 % | **FAIT** |
| 5. Tool schema | 5 outils en lecture seule et `submit_advice` ; schémas JSON stricts ; validation Pydantic | `src/cotraffic/llm/tools.py:120-262` ; `src/cotraffic/llm/sources.py:152` (`ToolLlmSource`) | `pytest tests\test_llm_tools.py -v` ; `python scripts\llm_tools_demo.py` (environ 1 min) | 12 tests. Essai réel : 27 à 50 s par conseil, le modèle lit les carrefours dans l'ordre | **FAIT**, non retenu (trop lent) |
| 6. Fine-tuning LoRA | Jeu de données tiré des graines d'entraînement ; notebook Colab prêt (0,5B ou 1,5B, moins d'une heure sur un T4) | `scripts/llm_dataset.py` ; `notebooks/llm_lora_colab.ipynb` (section 8) | Colab (section 6 ci-dessous) | Entraînement lancé ce soir sur Colab | **PRÉLIMINAIRE** |
| 7. Prompt tuning | Soft prompt PEFT (20 jetons virtuels), même jeu de données, comparé à LoRA et au prompt engineering | `notebooks/llm_lora_colab.ipynb` (sections 9 et 10) | Colab | Entraînement lancé ce soir | **PRÉLIMINAIRE** |
| 8. Évaluation | Rejeux appariés (63 situations) ; épisodes complets (6 scénarios × 3 périodes) ; contrôle à règles ; placebo et oracle ; pré-enregistrement | `src/cotraffic/llm/rollout.py:168` ; `scripts/llm_period.py` ; `scripts/llm_dataset.py` ; `docs/LLM_PREREGISTRATION.md` | `type results\exploration\llm_period\period_summary.csv` | Épisodes, N = 10 min : −0,38 % en moyenne. Règles : −0,09 %. Oracle et placebo : section 4.5 | **PARTIEL** : validation seulement |
| 9. Sécurité | Lecture stricte et bornée ; taille maximale ; délai et repli ; données jamais traitées comme instructions ; outils en lecture seule ; bouclier | `src/cotraffic/llm/advice.py:79` et `:125` ; `src/cotraffic/llm/sources.py:34` et `:84` ; `src/cotraffic/llm/client.py:73` ; `src/cotraffic/llm/prompts.py:47` ; `tests/test_llm_security.py` | `pytest tests\test_llm_security.py -v` (environ 20 s) | 10 tests adverses. Attaque avec un biais de 1000 : vert le plus court 13 s pour un minimum de 10 s, sur 100 verts | **FAIT** |
| 10. Orchestration | Déclencheurs, file d'attente, latence réelle, expiration, limite de fréquence, cache (optionnel), journal d'audit | `src/cotraffic/llm/advised.py:104-198` ; `docs/LLM_DESIGN.md`, section 3 (schéma et flux pas à pas) | `type results\exploration\llm_period\calls\coop_full_llm-N600__grid4x4__emergency__peak__s1000.jsonl` | `test_latency_modes_for_the_sensitivity_analysis`, `test_the_cache_reuses_the_advice_of_an_identical_situation` | **FAIT** |

---

## 2. Chaque exigence expliquée simplement

**1. Le LLM intervient dans la décision.**
- Toutes les 5 s, l'agent PPO calcule un score (logit) pour chaque phase de son feu.
- Quand un conseil est actif, on ajoute `beta × force / 3` au score de la phase conseillée,
  puis on prend la phase au plus grand score : le LLM change donc réellement la décision.
- Un conseil faible ne renverse pas une forte préférence du RL, et le bouclier peut encore
  refuser la phase demandée.
- La démo affiche, pour chaque décision changée : la phase que PPO aurait choisie seul,
  celle demandée avec le conseil, et celle que le bouclier exécute.
- Ce n'est donc pas l'assistant du tableau de bord (`cotraffic ask`), qui répond seulement
  à des questions.

**2. Le LLM choisi.**
- 8 modèles locaux, de 0,5B à 3,8B, ont répondu aux 63 mêmes situations de validation.
- Pour chacun, on a mesuré la latence, le taux de JSON valide, et le gain obtenu en
  rejouant chaque conseil dans SUMO.
- La règle de choix a été écrite avant de voir les résultats : JSON valide au moins 95 %,
  latence p95 au plus 20 s, puis le meilleur gain.
- Elle retient `qwen2.5:3b`. Mais son avance (+0,29 %) est dans le bruit, et sa licence
  (Qwen Research) interdit l'usage commercial.

**3. Les hyperparamètres.**
- `configs/llm.yaml` rassemble tous les réglages, avec, pour chacun, la mesure qui le
  justifie.
- Température 0 : même situation, même conseil, donc des runs reproductibles.
- `num_predict` 96 : les réponses font au plus 75 tokens. Délai maximal 60 s : la latence
  p95 est de 11,7 s.
- beta 4 : c'est le plus fort biais qui ne dégrade pas ; beta 8 donne −1,2 %. Période de
  10 min : 3 min dégrade les piétons de 24,8 %.
- Un test vérifie que les valeurs par défaut du code sont celles du fichier.

**4. Les techniques de prompt engineering.**
- **Le prompt est versionné**, et son empreinte est enregistrée dans chaque résultat.
- **La v2 a corrigé deux défauts mesurés avec la v1 :**
  - les modèles 3B écrivaient des pourcentages : on demande donc une force 1, 2 ou 3,
    imposée par le schéma ;
  - aucun modèle ne s'abstenait : l'abstention est donc devenue la règle par défaut.
- **Quatre techniques ont été comparées sur le même modèle :**
  - zero-shot, la consigne seule ;
  - brief, avec une raison courte ;
  - few-shot, avec 6 exemples tirés des graines d'entraînement et choisis par gain moyen ;
  - self-consistency, 3 réponses et un vote majoritaire.
- **Résultat : zero-shot est la meilleure et la plus rapide.** Ni les exemples ni le vote
  n'aident.

**5. Le tool schema.**
- Le modèle peut lire la situation par 5 outils : état d'un carrefour, voisins, événements,
  route d'une ambulance, véhicules qui arrivent. Puis il appelle `submit_advice`.
- Les outils lisent une copie de la situation : aucun ne peut toucher la simulation.
- Chaque appel est validé (schéma strict, Pydantic). Un outil inconnu, comme
  `set_traffic_light`, est refusé, et le modèle en est informé.
- Le mécanisme marche (`docs/demo/llm_tools_demo.txt`), mais le modèle lit les carrefours
  dans l'ordre au lieu de suivre l'ambulance, et chaque conseil prend 27 à 50 s : il n'a
  donc pas été retenu.

**6. Le fine-tuning LoRA.**
- **Le jeu de données** : chaque situation des graines d'entraînement (100001 à 100003) est
  rejouée 5 min avec plusieurs conseils candidats.
- **L'étiquette** est le meilleur candidat, ou l'abstention si aucun ne gagne au moins
  0,25 %.
- **L'entraînement** : LoRA apprend de petites matrices de rang 16 ajoutées au modèle,
  sans toucher ses poids. Le notebook entraîne Qwen2.5 0,5B (ou 1,5B) en moins d'une heure
  sur un GPU T4 gratuit, puis mesure le modèle sur les 63 situations de validation.
- Résultats **préliminaires** : peu d'exemples, et des étiquettes bruitées.

**7. Le prompt tuning.**
- On n'apprend que 20 vecteurs placés devant le prompt (environ 20 000 paramètres), et le
  modèle reste entièrement figé.
- C'est l'opposé du prompt engineering : on optimise le prompt par gradient au lieu de
  l'écrire à la main.
- Le notebook l'entraîne sur les mêmes données que LoRA, et compare les trois approches :
  paramètres entraînés, temps, JSON valide, accord avec l'étiquette.

**8. L'évaluation.**
- **Deux niveaux, sur la validation :**
  - des rejeux appariés : chaque conseil est rejoué depuis le même instantané SUMO que
    « sans conseil », donc une comparaison exacte ;
  - des épisodes complets de 50 minutes, avec le LLM dans la boucle.
- **Les contrôles :**
  - le conseiller à règles : mêmes principes, mais écrits à la main ;
  - le placebo : des conseils aléatoires de même amplitude ;
  - l'oracle : le meilleur conseil possible, choisi après coup.
- **L'évaluation finale sur les graines de test est pré-enregistrée** : hypothèses,
  contrôles, tests et famille Holm séparée.

**9. La sécurité.**
- **Le LLM ne contrôle jamais un feu.** Tout ce qui sort du modèle passe par une lecture
  stricte : JSON, clés, types, bornes, carrefours et phases existants.
- **Les cas de repli sur PPO seul** : une réponse trop longue (refusée avant lecture), un
  délai dépassé ou une réponse invalide. PPO décide alors seul.
- **Les données ne sont jamais des instructions.** Elles sont placées entre balises
  `<state>`, et une injection cachée dans le nom d'une rue d'un accident ne peut pas en
  sortir.
- **L'attaque testée dans SUMO** : une source qui conseille de changer de phase à chaque
  décision, avec un biais de 1000. Elle change bien les demandes, mais le bouclier ne
  laisse jamais un vert durer moins de 10 s.

**10. L'orchestration.**
- **Le parcours d'un conseil :** événement ou minuteur → photographie de la situation →
  prompt balisé → LLM → validation → file d'attente → délai égal à la latence réelle →
  biais → bouclier → SUMO.
- **Les limites :** un seul appel à la fois, au plus un toutes les 30 s ; chaque conseil
  expire après 10 à 120 s.
- **Le journal :** chaque appel est enregistré (déclencheur, latence, conseil, rejets).
- **Le cache** des situations identiques est codé mais désactivé, car il n'a pas été évalué.
- `docs/LLM_DESIGN.md` (section 3) donne le schéma et le flux pas à pas, avec les lignes de
  code.

---

## 3. Ordre de démonstration conseillé (15 min)

| Temps | Quoi | Commande ou fichier |
|---|---|---|
| 1 min | Le principe : le LLM conseille, le RL exécute, le bouclier décide en dernier | Schéma de `docs/LLM_DESIGN.md`, section 3 |
| 4 min | **La preuve que le LLM agit sur les décisions** : la démo en direct | `.venv\Scripts\python scripts\llm_demo.py` (secours : `type docs\demo\llm_demo_emergency.txt`) |
| 2 min | Le modèle et les réglages justifiés | `Get-Content configs\llm.yaml` ; `type results\exploration\llm_benchmark\step2_choice.json` |
| 2 min | La sécurité : tests adverses, et l'attaque contre le bouclier | `.venv\Scripts\python -m pytest tests\test_llm_security.py -v` |
| 1 min | Le tool schema | `type docs\demo\llm_tools_demo.txt` (ou `pytest tests\test_llm_tools.py -v`) |
| 3 min | Les résultats, honnêtement : pas de gain, et pourquoi | Section 4 de ce document |
| 1 min | LoRA et prompt tuning | `notebooks/llm_lora_colab.ipynb`, section 10 (tableau de comparaison) |
| 1 min | Ce qui reste : l'évaluation pré-enregistrée sur les graines de test | `docs/LLM_PREREGISTRATION.md` |

Pendant la démo, il faut montrer :
- une ligne `PPO seul -> p0 | avec le conseil -> p1 | bouclier -> p1 (accepté)` : le LLM a
  changé la décision ;
- une ligne `..., corrigé : vert minimum pas encore atteint` : le bouclier a refusé ;
- la ligne « Pour comparaison, le conseiller à règles proposerait » : à l'appel n°4, les
  règles proposent la phase dont l'ambulance a besoin, et le LLM l'inverse.

---

## 4. Résultats (validation, graine 1000)

### 4.1 Modèles (prompt v2, zero-shot, 63 situations, rejeux de 5 min)

| Modèle | Latence p50 / p95 | JSON valide | Gain, beta 2 | Gain, beta 4 |
|---|---|---|---|---|
| qwen2.5:0.5b | 4,0 / 4,4 s | 100 % | +0,07 % | +0,22 % |
| qwen2.5:1.5b | 4,8 / 6,0 s | 100 % | −0,39 % | −0,41 % |
| qwen3:1.7b | 6,6 / 12,0 s | 100 % | +0,09 % | −0,13 % |
| **qwen2.5:3b (choisi)** | 8,6 / 15,4 s | 100 % | −0,02 % | **+0,29 %** |
| llama3.2:3b | 12,4 / 14,9 s | 100 % | +0,01 % | −0,35 % |
| phi4-mini (3,8B) | 10,5 / 12,4 s | 100 % | +0,09 % | +0,10 % |
| Règles (contrôle) | – | – | +0,01 % | −0,09 % |

Avec le prompt v1, gemma3:1b (27 % de JSON valide) et llama3.2:1b (68 %, conseil
constant) ont été éliminés.

### 4.2 Force du biais (beta)

La marge médiane de PPO entre ses deux phases vaut 3,3. Un conseil de force maximale peut
donc renverser :

| beta | Décisions qu'un conseil maximal peut renverser | Gain, qwen2.5:1.5b | Pire que PPO seul |
|---|---|---|---|
| 2 | 27 % | +0,12 % | 22 % des situations |
| 4 | 63 % | +0,01 % | 37 % |
| 8 | 92 % | **−1,21 %** | 60 % |

Plus le LLM pèse, plus il dégrade. beta 4 est le plus fort biais qui ne dégrade pas en
moyenne.

### 4.3 Techniques de prompt (qwen2.5:3b, beta 4)

| Technique | Latence p50 | Gain | Abstentions |
|---|---|---|---|
| **zero** | 8,2 s | **+0,15 %** | 0 % |
| brief (raison courte) | 10,1 s | −0,18 % | 0 % |
| few (6 exemples) | 9,2 s | +0,08 % | 40 % |
| zero + vote à 3 réponses | 18,4 s | +0,02 % | 3 % |

La même configuration donne +0,29 % (avec `num_ctx` 2048) et +0,15 % (avec 4096). Cet écart
dû au calcul sur le GPU est **de l'ordre de grandeur du bruit**.

### 4.4 Période N : épisodes complets avec le LLM (50 min, 6 scénarios)

Gain sur le temps d'attente moyen, par rapport à COOP-FULL seul :

| Scénario | N = 3 min | N = 5 min | **N = 10 min (choisi)** |
|---|---|---|---|
| Accident | −2,09 % | −1,47 % | +0,94 % |
| Urgences | +1,77 % | +1,45 % | −0,25 % |
| Capteurs en panne | −3,50 % | −2,95 % | −1,59 % |
| Pertes de messages (30 %) | −1,24 % | −3,18 % | +0,21 % |
| Piétons | **−24,76 %** | +3,33 % | −0,16 % |
| Trafic normal | −0,07 % | +2,46 % | −1,45 % |
| **Moyenne** | −4,98 % | −0,06 % | **−0,38 %** |

Une seule graine par case : un écart de ±3 % n'est pas significatif. L'épisode accident à
3 min a été rejoué, car une mise en veille du PC avait fait expirer un appel.

### 4.5 Oracle et placebo

*En cours de calcul (`scripts/llm_dataset.py`) : section complétée dès la fin du calcul.*

### 4.6 LoRA et prompt tuning

*Entraînement sur Colab ce soir (notebook prêt) : section complétée avec les chiffres du
notebook, puis avec le rejeu SUMO des prédictions.*

---

## 5. Limites, dites honnêtement

- **Pas de gain.**
  - Sur la validation, le LLM n'améliore pas les scores : de −0,4 à +0,3 %, dans le bruit.
  - Appelé trop souvent (3 min), il dégrade les piétons de 24,8 %.
- **Les petits modèles suivent mal les principes.**
  - Ils conseillent souvent les carrefours dans l'ordre de la liste (A0, A1…).
  - Ils proposent parfois la phase inverse de celle dont l'ambulance a besoin (voir la démo).
- **Même les règles écrites à la main n'aident pas en moyenne.**
  - COOP-FULL gère déjà bien ces situations ; la marge de progrès est faible.
  - L'oracle (section 4.5) mesure cette marge.
- **Une seule graine de validation.** Les écarts entre réglages sont du même ordre que le
  bruit, donc les choix de l'étape 2 sont peu discriminants. C'est pour cela que la règle
  de choix a été fixée à l'avance.
- **Biais en faveur des règles.** Dans le benchmark de l'étape 2, le contrôle à règles a
  été rejoué sans délai, ce qui l'avantage. C'est corrigé pour l'évaluation finale (même
  latence pour tous) et dans le calcul de l'oracle.
- **Latence.**
  - 8 s par conseil sur la puce graphique intégrée (Iris Xe), et 27 à 50 s avec les outils.
  - La latence est modélisée : le conseil n'agit qu'après ce délai.
- **Détection des capteurs en panne.** Le détecteur d'événements lit l'information du
  scénario : on suppose la panne signalée.
- **LoRA et prompt tuning sont préliminaires.** Peu d'exemples (environ 200), étiquettes
  bruitées, petit modèle.
- **Évaluation finale non faite.** Les graines de test 0 à 4 n'ont pas encore été lancées
  (section 7).

---

## 6. LoRA et prompt tuning : les étapes sur Colab

1. Ouvrir <https://colab.research.google.com>, puis Fichier > Importer un notebook >
   `notebooks/llm_lora_colab.ipynb`.
2. Exécution > Modifier le type d'exécution > **GPU T4** > Enregistrer.
3. Exécuter les cellules **dans l'ordre**, avec Exécution > Tout exécuter, ou Ctrl+Entrée
   cellule par cellule.
4. À la cellule 3, téléverser les deux fichiers de `results/exploration/llm_lora/` :
   `llm_lora_train.jsonl` et `llm_lora_val.jsonl`.
5. Attendre : 20 à 30 min avec 0,5B. Pour 1,5B, changer `MODEL` dans la cellule 4 ; compter
   45 à 60 min.
6. La cellule 11 télécharge :
   - `adapter_lora.zip` et `adapter_prompt_tuning.zip` ;
   - `lora_comparison.csv`, le tableau de comparaison ;
   - les prédictions `base_*`, `lora_*` et `prompt_tuning_*`, en `.csv`.
7. En local, copier les `.csv` dans `results/exploration/llm_benchmark/`, puis lancer les
   commandes de la cellule 12, qui rejouent les prédictions dans SUMO :

```powershell
.venv\Scripts\python scripts\llm_benchmark.py --reuse-calls lora --techniques lora --betas 4 --tag lora_val
.venv\Scripts\python scripts\llm_benchmark.py --reuse-calls prompt_tuning --techniques prompt_tuning --betas 4 --tag pt_val
.venv\Scripts\python scripts\llm_benchmark.py --reuse-calls base --techniques base --betas 4 --tag base_val
```

---

## 7. Prochaines étapes

1. **Évaluation sur les graines de test 0 à 4**, comme le prévoit
   `docs/LLM_PREREGISTRATION.md`.
   - Contrôleurs : COOP-FULL seul, + LLM, + placebo, + règles (même latence pour tous), et
     l'oracle au niveau des situations.
   - Volume : 15 runs par scénario.
   - Tests : Mann-Whitney avec correction de Holm dans une famille « llm » séparée.
   - Durée : environ 24 à 28 h de calcul, 16 h avec le plan réduit.
2. **Rejouer dans SUMO les prédictions LoRA et prompt tuning.** Si elles dépassent le
   zero-shot sur la validation, les ajouter à l'évaluation.
3. **Pistes pour obtenir un gain** :
   - donner au LLM ce que PPO n'a pas, comme l'état au-delà des voisins ou une prévision
     de la demande ;
   - ne laisser le LLM conseiller que les carrefours cités par un événement ;
   - essayer le changement de mode (`coop_full_ev4` pendant une urgence).

---

## 8. Questions probables et réponses courtes

1. **Le LLM commande-t-il les feux ?**
   Non. Il donne un conseil borné qui modifie le score des phases de PPO. PPO choisit, et le
   bouclier peut encore refuser. Les tests le vérifient, y compris sous attaque.
2. **Pourquoi un LLM, s'il n'améliore pas les scores ?**
   C'était l'hypothèse à tester, et la réponse honnête, sur la validation, est « pas
   d'amélioration ». Le travail montre une architecture sûre et mesurable pour le tester.
   L'oracle dit combien un meilleur conseiller pourrait gagner.
3. **Pourquoi qwen2.5:3b ?**
   Une règle fixée avant les résultats : au moins 95 % de JSON valide, une latence p95 d'au
   plus 20 s, puis le meilleur gain. Son avance est dans le bruit ; qwen2.5:0.5b est un
   choix presque équivalent et deux fois plus rapide.
4. **Comment la latence est-elle prise en compte ?**
   Le conseil n'agit qu'à t + la latence réelle mesurée de l'appel (8 s en médiane). Une
   analyse de sensibilité (délai nul, mesuré, doublé) est prévue dans le pré-enregistrement.
5. **Et si le LLM répond n'importe quoi, ou s'il est attaqué ?**
   Une réponse invalide, trop longue ou trop lente est ignorée, et PPO décide seul. Une
   injection dans les données reste dans le bloc de données. Même un conseil malveillant
   très fort ne viole jamais le bouclier.
6. **Pourquoi beta = 4 ?**
   La marge de PPO entre ses phases vaut 3,3 en médiane. Avec beta 4, un conseil fort peut
   renverser 63 % des décisions sans dégrader en moyenne ; avec beta 8, il dégrade
   (−1,2 %).
7. **Comment éviter le sur-ajustement ?**
   - Tous les choix sont faits sur la seule graine 1000, et les exemples sur les graines
     d'entraînement.
   - Les règles de choix ont été écrites avant les résultats.
   - Les graines de test sont réservées à une évaluation pré-enregistrée.
8. **LoRA, prompt tuning, prompt engineering : quelle différence ?**
   - Le prompt engineering écrit le texte à la main (0 paramètre).
   - Le prompt tuning apprend 20 vecteurs devant le prompt (environ 20 000 paramètres).
   - LoRA apprend de petites matrices dans chaque couche (quelques millions de paramètres).
   - Dans les trois cas, le modèle de base reste figé.
9. **Pourquoi le few-shot n'aide-t-il pas ?**
   Les exemples apprennent surtout au modèle à s'abstenir (40 % d'abstentions). Or COOP-FULL
   gère déjà bien les situations : se taire ne gagne rien, et les conseils restants ne sont
   pas meilleurs.
10. **Qu'apporte l'oracle ?**
    C'est le meilleur conseil candidat de chaque situation, choisi après coup par rejeu :
    une borne haute de ce qu'un conseiller peut gagner ici. Si elle est faible, la marge de
    progrès est faible, quel que soit le modèle.

---

## Où trouver quoi

| Sujet | Fichier |
|---|---|
| Conception, schéma, flux pas à pas | `docs/LLM_DESIGN.md` |
| Réglages justifiés | `configs/llm.yaml` |
| Pré-enregistrement | `docs/LLM_PREREGISTRATION.md` |
| Commandes de démo | `docs/DEMO_GUIDE.md`, section « LLM dans la boucle » |
| Code | `src/cotraffic/llm/` (advice, advised, client, prompts, situation, snapshot, rollout, sources, tools, settings) |
| Tests | `tests/test_llm.py`, `test_llm_security.py`, `test_llm_tools.py`, `test_llm_settings.py`, `test_llm_snapshot.py` |
| Résultats de validation | `results/exploration/llm_benchmark/`, `llm_period/`, `llm_fewshot/`, `llm_oracle/` |
| Sorties de démo (secours) | `docs/demo/llm_demo_emergency.txt`, `docs/demo/llm_tools_demo.txt` |
