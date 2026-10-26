# Validation : le LLM dans la boucle de décision des agents

Document de validation de la partie « LLM dans la boucle » de CoTraffic. Pour chaque
exigence, il dit ce qui a été fait, où c'est dans le code, comment le montrer, et quelle
est la preuve.

**Convention : gain positif = mieux** (moins d'attente que COOP-FULL seul, comme dans le
tableau de bord).

**Tous les chiffres sont des résultats de validation (graine 1000)**, sauf mention
contraire :
- les exemples d'entraînement viennent des graines 100001 à 100003 ;
- les graines de test 0 à 4 n'ont servi à rien régler, et l'évaluation sur ces graines
  reste à faire (section 7).

**LoRA et prompt tuning sont préliminaires.**
- Le lot final : 169 exemples d'entraînement (graines 100001 à 100003), et une validation
  qui ne compte que **15 situations étiquetées « conseil » sur 63**.
- Le lot préliminaire, qui a servi à tester le notebook : 69 exemples d'entraînement, et
  **8 situations « conseil » sur 63** en validation.

Autres documents :
- [GUIDE_SOUTENANCE_LLM.md](GUIDE_SOUTENANCE_LLM.md) (et sa version HTML hors ligne) :
  le guide de soutenance complet, en français simple ;
- [VISITE_DU_CODE.md](VISITE_DU_CODE.md) : le parcours du code devant le prof ;
- [FICHE_QUESTIONS_LLM.md](FICHE_QUESTIONS_LLM.md) : 15 questions probables ;
- [DEMO_GUIDE.md](DEMO_GUIDE.md), section « Démo LLM » : les commandes ;
- [LLM_DESIGN.md](LLM_DESIGN.md) : la conception ;
- [LLM_PREREGISTRATION.md](LLM_PREREGISTRATION.md) : l'évaluation prévue.

## En bref

Un LLM local (`qwen2.5:3b`, via Ollama, sans aucune donnée envoyée à l'extérieur) est
appelé rarement : à chaque nouvel événement (ambulance, accident, capteur en panne, pertes
de messages, foule de piétons) et toutes les 10 minutes. Son conseil devient un **biais
borné** sur les logits des agents PPO (COOP-FULL). Ce biais n'agit qu'après la latence
réelle de l'appel, et le **bouclier de sécurité garde le dernier mot**.

Tout fonctionne de bout en bout et c'est testé. Mais, sur la validation, **aucun conseiller
n'améliore nettement les scores** :
- le LLM fait +0,16 %, le placebo +0,09 %, les règles −0,17 % ;
- même l'**oracle**, qui choisit après coup le meilleur conseil de chaque situation, ne
  gagne que **+1,09 %**.

COOP-FULL est déjà bon ici, et la marge de progrès est faible. Ce document le dit, montre
pourquoi, et liste ce qui a été essayé.

---

## 1. Tableau des exigences

| Exigence | Ce qui est fait | Fichier:lignes | Commande de démo | Preuve | Statut |
|---|---|---|---|---|---|
| 1. LLM dans la boucle de décision | **Biais** sur les logits de PPO, puis le bouclier. **Couloir vert** : un conseil couvre jusqu'à 4 carrefours, pendant 10 à 120 s. **Changement de mode** : non fait | `src/cotraffic/llm/advised.py:189-198` (PPO seul, biais, décision) ; `src/cotraffic/envs/traffic_env.py:190` (bouclier) ; `src/cotraffic/llm/advice.py:39` (jusqu'à 4 carrefours) | `python scripts/llm_demo.py` (2 min) | Démo : 106 décisions sous conseil, 6 changées par le conseil, 51 demandes corrigées par le bouclier. Tests `test_advice_applies_only_after_its_latency_and_expires`, `test_weak_advice_does_not_overturn_a_clear_preference`, `test_rules_build_a_green_wave_ahead_of_an_emergency_vehicle` | **PARTIEL** : biais et couloir vert faits ; changement de mode **pas fait** ; gain non démontré |
| 2. Choix du LLM | 8 modèles de 0,5B à 3,8B, testés sur 63 situations ; critères et règle de choix écrits avant les résultats | `scripts/llm_benchmark.py` ; `scripts/llm_step2.py:1-25` (règles), `:73` (`best`) ; `configs/llm.yaml:8-20` | `type results\exploration\llm_benchmark\step2_choice.json` | qwen2.5:3b : 100 % de JSON valide, latence p50 8,6 s, gain +0,29 % (`v2_zero_summary.csv`) | **FAIT** |
| 3. Hyperparamètres | Un seul fichier (inférence, beta, période N, délai, cache, vote), lu par le code, chaque valeur justifiée par une mesure | `configs/llm.yaml` ; `src/cotraffic/llm/settings.py:29` | `Get-Content configs\llm.yaml` | `test_code_defaults_match_the_settings_file`, `test_settings_are_complete_and_bounded`. beta 8 : −1,2 % (`beta_v1_summary.csv`) ; N = 3 min : −5,0 % (`period_summary.csv`) | **FAIT** |
| 4. Prompt engineering | Prompt versionné (v1, v2) ; zero, brief, few-shot (exemples des graines d'entraînement) ; vote sur 3 réponses ; sortie JSON contrainte par schéma | `configs/prompts/advisor-v2.yaml` ; `src/cotraffic/llm/prompts.py:23-82` ; `scripts/llm_fewshot.py:121` ; `src/cotraffic/llm/sources.py:103` (vote) ; `src/cotraffic/llm/advice.py:45` (schéma) | `type results\exploration\llm_benchmark\v2_tech_summary.csv` | `test_prompt_versions_and_techniques`, `test_self_consistency_keeps_majority_items_only`. v1 → v2 : JSON valide de 67 à 100 % (3B) ; zero +0,15 %, brief −0,18 %, few +0,08 %, vote +0,02 % | **FAIT** |
| 5. Tool schema | 5 outils en lecture seule et `submit_advice` ; JSON Schema strict ; validation Pydantic ; budget d'appels | `src/cotraffic/llm/tools.py:120-262` ; `src/cotraffic/llm/sources.py:152` (`ToolLlmSource`) | `pytest tests\test_llm_tools.py -v` (5 s) ; `python scripts\llm_tools_demo.py` (1 min) | 12 tests. Essai réel : 27 à 50 s par conseil (`docs/demo/llm_tools_demo.txt`) | **FAIT**, non retenu (trop lent) |
| 6. Fine-tuning LoRA | Jeu de données par rejeu (graines d'entraînement), rééquilibrage, hyperparamètres, notebook Kaggle et Colab, rejeu SUMO des prédictions | `scripts/llm_dataset.py:158-191` (étiquettes) ; `notebooks/llm_lora_colab.ipynb`, sections 4, 5 et 8 | `type results\exploration\llm_lora\final_lora_comparison.csv` | Lot final (169 exemples) : rappel 17 %, faux conseils 12 %, **gain dans SUMO +0,05 %** (`final_kaggle_val_summary.csv`) | **PARTIEL** : préliminaire (peu d'exemples, 15 situations « conseil » en validation) |
| 7. Prompt tuning | Soft prompt PEFT (20 jetons virtuels), mêmes données, comparé à LoRA et au prompt engineering | `notebooks/llm_lora_colab.ipynb`, sections 9 et 10 | même fichier que la ligne 6 | Lot final : rappel 11 %, faux conseils 15 %, **gain dans SUMO −0,09 %** | **PARTIEL** : préliminaire |
| 8. Évaluation | Protocole de rejeux appariés ; épisodes complets ; contrôles placebo, règles, oracle ; pré-enregistrement ; statistiques prévues (Mann-Whitney, Holm) | `src/cotraffic/llm/rollout.py:168` ; `scripts/llm_dataset.py:129` (oracle) ; `scripts/llm_period.py` ; `docs/LLM_PREREGISTRATION.md` | `python scripts\llm_results_table.py` (1 min) | Oracle +1,09 %, LLM +0,16 %, placebo +0,09 %, règles −0,17 % (`llm_oracle/oracle_summary.csv`) | **PARTIEL** : validation seulement ; graines de test et tests statistiques non lancés |
| 9. Sécurité | Lecture stricte et bornée ; taille maximale ; délai et repli ; données jamais traitées comme instructions ; outils en lecture seule ; bouclier final | `src/cotraffic/llm/advice.py:79` et `:125` ; `src/cotraffic/llm/sources.py:34` et `:84` ; `src/cotraffic/llm/client.py:73` ; `src/cotraffic/llm/prompts.py:47` | `pytest tests\test_llm_security.py -v` (20 s) | 10 tests adverses. Attaque avec un biais de 1000 : vert le plus court 13 s pour un minimum de 10 s, sur 100 verts | **FAIT** |
| 10. Orchestration | Déclencheurs, file d'attente, délai égal à la latence réelle, expiration, limite de fréquence, cache (désactivé), journal d'audit, schéma Mermaid | `src/cotraffic/llm/advised.py:104-198` ; `:48` (cache) ; `docs/LLM_DESIGN.md:59-100` (schéma), section 3 (flux pas à pas) | `type results\exploration\llm_period\calls\coop_full_llm-N600__grid4x4__emergency__peak__s1000.jsonl` | `test_latency_modes_for_the_sensitivity_analysis`, `test_the_cache_reuses_the_advice_of_an_identical_situation` | **FAIT** |

---

## 2. Chaque exigence expliquée simplement

**1. Le LLM intervient dans la décision.**
- **Le biais.** Toutes les 5 s, l'agent PPO calcule un score (logit) pour chaque phase de
  son feu. Quand un conseil est actif, on ajoute `beta × force / 3` au score de la phase
  conseillée, puis on prend la phase au plus grand score : le LLM change donc réellement la
  décision.
- **Le couloir vert.** Un même conseil peut viser jusqu'à 4 carrefours pendant 10 à 120 s,
  par exemple le long de la route d'une ambulance.
- **Le changement de mode** (passer à la politique `coop_full_ev4` pendant une urgence)
  n'a pas été réalisé.
- Ce n'est pas l'assistant du tableau de bord (`cotraffic ask`), qui répond seulement à des
  questions.

**2. Le choix du LLM.**
- 8 modèles locaux, de 0,5B à 3,8B, ont répondu aux 63 mêmes situations de validation.
- Pour chacun, on a mesuré la latence, le taux de JSON valide, et le gain obtenu en
  rejouant chaque conseil dans SUMO.
- La règle a été écrite avant les résultats : au moins 95 % de JSON valide, une latence
  p95 d'au plus 20 s, puis le meilleur gain. Elle retient `qwen2.5:3b`.
- Son avance est dans le bruit, et sa licence (Qwen Research) interdit l'usage commercial.

**3. Les hyperparamètres.**
- `configs/llm.yaml` rassemble tous les réglages, avec la mesure qui justifie chacun.
- Température 0 : même situation, même conseil. `num_predict` 96 : les réponses font au
  plus 75 tokens. Délai maximal 60 s : la latence p95 est de 11,7 s.
- beta 4 est le plus fort biais qui ne dégrade pas ; beta 8 donne −1,2 %.
- Période de 10 min : 3 min dégrade les piétons de 24,8 %.
- Le code lit ce fichier, et un test vérifie que les valeurs par défaut du code sont les
  mêmes.

**4. Les techniques de prompt engineering.**
- Le prompt est versionné, et son empreinte est enregistrée dans chaque résultat.
- La v2 a corrigé deux défauts mesurés avec la v1 :
  - les modèles 3B écrivaient des pourcentages : on demande une force 1, 2 ou 3, imposée
    par le schéma ;
  - aucun modèle ne s'abstenait : l'abstention devient le comportement par défaut.
- Quatre techniques ont été comparées sur le même modèle : zero-shot, brief (avec une
  raison), few-shot (6 exemples des graines d'entraînement, choisis par gain moyen) et vote
  sur 3 réponses.
- Zero-shot est la meilleure et la plus rapide.

**5. Le tool schema.**
- Le modèle peut lire la situation avec 5 outils (état d'un carrefour, voisins, événements,
  route d'une ambulance, véhicules qui arrivent), puis appeler `submit_advice`, le seul
  outil qui agit.
- Les outils lisent une copie de la situation : aucun ne peut toucher la simulation.
- Chaque appel est validé (schéma strict, Pydantic). Un outil inconnu, comme
  `set_traffic_light`, est refusé.
- Le mécanisme marche, mais le modèle lit les carrefours dans l'ordre au lieu de suivre
  l'ambulance, et un conseil prend 27 à 50 s : il n'est pas retenu.

**6. Le fine-tuning LoRA.**
- **Les étiquettes.** Chaque situation des graines d'entraînement est rejouée 5 min avec
  plusieurs conseils candidats. L'étiquette est le meilleur, ou l'abstention si aucun ne
  gagne au moins 0,25 %.
- **L'entraînement.** LoRA apprend de petites matrices de rang 16 sans toucher les poids
  du modèle. Les exemples de conseil sont suréchantillonnés, car les abstentions sont
  majoritaires.
- **Le premier essai** a montré le piège de la classe majoritaire (section 3.2).
- **Sur le lot final**, LoRA conseille dans 8 situations seulement, dont 7 urgences ; il
  retrouve 17 % des conseils attendus, avec 12 % de faux conseils.
- **Le juge final** est le rejeu dans SUMO : +0,05 %, donc pas de gain mesurable.

**7. Le prompt tuning.**
- On n'apprend que 20 vecteurs placés devant le prompt (17 920 paramètres) ; le modèle
  reste figé.
- C'est l'inverse du prompt engineering : on optimise le prompt par gradient au lieu de
  l'écrire à la main.
- Sur les mêmes données, il apprend moins que LoRA (rappel 11 % contre 17 %), et son effet
  dans SUMO est légèrement négatif (−0,09 %).

**8. L'évaluation.**
- **Deux niveaux, sur la validation :**
  - des rejeux appariés de 63 situations, depuis le même instantané SUMO que « sans
    conseil » ;
  - des épisodes complets de 50 minutes, avec le LLM dans la boucle.
- **Les contrôles :**
  - le conseiller à règles (mêmes principes, écrits à la main) ;
  - le placebo (conseils au hasard, même amplitude) ;
  - l'oracle (le meilleur conseil, choisi après coup).
- Tous ces conseils sont appliqués après le même délai de 8,2 s.
- L'évaluation finale sur les graines de test est pré-enregistrée : hypothèses, contrôles,
  tests de Mann-Whitney avec la correction de Holm, dans une famille séparée.

**9. La sécurité.**
- **Le LLM ne contrôle jamais un feu.** Tout ce qui sort du modèle passe par une lecture
  stricte : JSON, clés, types, bornes, carrefours et phases existants.
- **Le repli sur PPO seul** : une réponse trop longue est refusée avant lecture ; un délai
  dépassé ou une réponse invalide laisse PPO décider seul.
- **Les données ne sont jamais des instructions.** Elles sont entre balises `<state>`, et
  une injection cachée dans le nom d'une rue reste dans ce bloc.
- **L'attaque testée dans SUMO** : un conseil malveillant très fort (biais de 1000) change
  bien les demandes, mais le bouclier ne laisse jamais un vert durer moins de 10 s.

**10. L'orchestration.**
- **Le parcours d'un conseil :** événement ou minuteur → photographie de la situation →
  prompt balisé → LLM → validation → file d'attente → délai égal à la latence réelle →
  biais → bouclier → SUMO.
- **Les limites :** un seul appel à la fois, au plus un toutes les 30 s ; chaque conseil
  expire après 10 à 120 s.
- **Le journal :** chaque appel est enregistré (déclencheur, latence, conseil, rejets).
- **Le cache** des situations identiques est codé, mais désactivé faute d'évaluation.

---

## 3. Résultats (validation, graine 1000)

### 3.1 Tableau unique

Ce tableau est produit par `python scripts\llm_results_table.py`, à partir des fichiers de
résultats (copie : `results/exploration/llm_summary/validation_table.csv`).

Ce qu'il mesure :
- **le gain sur l'attente**, sur les 63 situations, rejouées 5 min depuis le même instantané ;
- **le rappel et les faux conseils**, par rapport aux étiquettes de validation du lot
  final : **15 situations « conseil » et 48 « abstention »**.

Les modèles 0,5B sont ceux entraînés sur le lot final (169 exemples). Le même tableau sur
le lot préliminaire s'obtient avec `--set prelim` (section 3.2).

| Contrôleur | Gain sur l'attente | JSON valide | Abstention | Rappel des conseils | Faux conseils | Latence |
|---|---|---|---|---|---|---|
| PPO seul (COOP-FULL) | 0,00 % | – | – | – | – | – |
| Toujours s'abstenir | 0,00 % | 100 % | 100 % | 0 % | 0 % | – |
| Règles | −0,17 % | 100 % | 11 % | 100 % | 85 % | – |
| Placebo (moyenne de 3 tirages) | +0,09 % | 100 % | 0 % | 9 % | 100 % | – |
| LLM zero-shot qwen2.5:3b | +0,16 % | 100 % | 0 % | 17 % | 100 % | 8,2 s (local) |
| Oracle (meilleur candidat, après coup) | +1,09 % | – | – | – | – | – |
| Base 0,5B (sans entraînement) | 0,00 % | 0 % | 0 % | 0 % | 0 % | 1,0 s (T4) |
| LoRA 0,5B (préliminaire, lot final) | +0,05 % | 100 % | 87 % | 17 % | 12 % | 0,8 s (T4) |
| Prompt tuning 0,5B (préliminaire, lot final) | −0,09 % | 100 % | 79 % | 11 % | 15 % | 0,6 s (T4) |

Comment le lire :
- **Règles et placebo** répondent instantanément, mais leurs conseils sont appliqués après
  8,2 s, la latence médiane du LLM, comme le LLM. Le rappel de 100 % des règles est obtenu
  par construction : les étiquettes sont des conseils de la famille des règles.
- **L'oracle** choisit après coup, pour chaque situation, le meilleur des candidats :
  aucun conseil, règles à la force 1, 2 ou 3, 3 tirages du placebo, LLM. C'est une borne
  haute : la marge de ce qu'un conseiller peut gagner ici est d'environ 1 %.
  - **Une part de ce gain vient de la chance** : le meilleur candidat est un tirage du
    placebo dans 21 situations sur 63 (`oracle_choices.csv`).
- **Le LLM et le placebo font presque pareil** (+0,16 % contre +0,09 %). Ils conseillent
  partout (100 % de faux conseils), alors que la plupart des situations n'en demandent pas.
- **Les modèles 0,5B sont sur un GPU T4** (Kaggle) : leur latence n'est pas comparable à
  celle d'Ollama en local. Leurs prédictions ont été rejouées en local avec la latence
  d'Ollama pour le même modèle (4,0 s). Le modèle de base n'a pas de décodage contraint
  sur Kaggle, d'où ses 0 % de JSON valide ; avec Ollama, le même modèle en a 100 %.

### 3.2 LoRA et prompt tuning : les trois essais, et le piège de la classe majoritaire

Trois essais sur Kaggle, avec Qwen2.5-0.5B. Les essais 1 et 2 portent sur le lot
préliminaire (69 exemples ; 8 situations « conseil » en validation), l'essai 3 sur le
lot final (169 exemples ; 15 situations « conseil »). Chaque lot a sa propre référence
« toujours s'abstenir » :

| Essai | Technique | JSON valide | Abstention | Accord | Rappel | Faux conseils | Gain dans SUMO |
|---|---|---|---|---|---|---|---|
| Référence, lot préliminaire | Toujours s'abstenir | 100 % | 100 % | **87 %** | 0 % | 0 % | 0 % |
| 1 (15 pas) | LoRA | 100 % | 100 % | **87 %** | 0 % | 0 % | 0 % (déduit : aucun conseil émis) |
| 1 | Prompt tuning | 71 % | 71 % | 67 % | 0 % | 0 % | 0 % (déduit : aucun conseil émis) |
| 2 (rééquilibré, 126 pas) | LoRA | 98 % | 76 % | 71 % | 27 % | 16 % | +0,01 % |
| 2 | Prompt tuning | 100 % | 79 % | 73 % | 9 % | 16 % | +0,04 % |
| Référence, lot final | Toujours s'abstenir | 100 % | 100 % | **76 %** | 0 % | 0 % | 0 % |
| **3 (lot final)** | **LoRA** | 100 % | 87 % | 67 % | 17 % | 12 % | **+0,05 %** |
| **3 (lot final)** | **Prompt tuning** | 100 % | 79 % | 65 % | 11 % | 15 % | **−0,09 %** |

- **Ce qui s'est passé au premier essai.** 55 des 63 situations de validation ont pour
  étiquette l'abstention. Répondre « rien » à tout donne donc 87 % d'accord, et LoRA n'avait
  appris que cela.
- **Les causes** : des abstentions majoritaires dans l'entraînement (42 sur 69), et
  seulement 15 pas d'optimisation.
- **Les corrections** :
  - suréchantillonnage des exemples de conseil, dans l'entraînement seulement ;
  - plus de pas d'optimisation ;
  - trois mesures ajoutées : la référence triviale, le rappel des conseils et les faux
    conseils.
- **Le résultat.** Au deuxième essai, LoRA conseille dans 14 situations et retrouve 27 %
  des conseils attendus, mais son effet dans SUMO reste nul.
- **Le lot final (essai 3).**
  - Plus prudent : 87 % d'abstentions, 12 % de faux conseils.
  - Il ne conseille que dans 8 situations, dont les 7 urgences de la validation, avec un
    gain de +0,45 % sur ces 7 urgences et de +0,05 % au total.
  - Le prompt tuning donne −0,09 %.
  - Tous deux ont un accord inférieur à la référence triviale (67 % et 65 % contre 76 %).
  - Ces écarts sont de l'ordre du bruit, sur très peu de situations : 7 urgences, et
    15 situations « conseil ».
- **La leçon** : l'accord avec une étiquette ne mesure pas l'utilité. On compare toujours à
  la référence triviale, et on juge sur l'effet réel dans SUMO.

### 3.3 Modèles (prompt v2, zero-shot, 63 situations)

| Modèle | Latence p50 / p95 | JSON valide | Gain, beta 2 | Gain, beta 4 |
|---|---|---|---|---|
| qwen2.5:0.5b | 4,0 / 4,4 s | 100 % | +0,07 % | +0,22 % |
| qwen2.5:1.5b | 4,8 / 6,0 s | 100 % | −0,39 % | −0,41 % |
| qwen3:1.7b | 6,6 / 12,0 s | 100 % | +0,09 % | −0,13 % |
| **qwen2.5:3b (choisi)** | 8,6 / 15,4 s | 100 % | −0,02 % | **+0,29 %** |
| llama3.2:3b | 12,4 / 14,9 s | 100 % | +0,01 % | −0,35 % |
| phi4-mini (3,8B) | 10,5 / 12,4 s | 100 % | +0,09 % | +0,10 % |
| Règles, sans délai (étape 2) | – | – | +0,01 % | −0,09 % |

Avec le prompt v1, gemma3:1b (27 % de JSON valide) et llama3.2:1b (68 %, conseil
constant) ont été éliminés (`models_zero_summary.csv`).

### 3.4 Force du biais (beta)

| beta | Décisions qu'un conseil maximal peut renverser | Gain, qwen2.5:1.5b | Pire que PPO seul |
|---|---|---|---|
| 2 | 27 % | +0,12 % | 22 % des situations |
| 4 | 63 % | +0,01 % | 37 % |
| 8 | 92 % | **−1,21 %** | 60 % |

La marge médiane de PPO entre ses deux phases vaut 3,3. Plus le LLM pèse, plus il
dégrade.

### 3.5 Techniques de prompt (qwen2.5:3b, beta 4)

| Technique | Latence p50 | Gain | Abstentions |
|---|---|---|---|
| **zero** | 8,2 s | **+0,15 %** | 0 % |
| brief (raison courte) | 10,1 s | −0,18 % | 0 % |
| few (6 exemples) | 9,2 s | +0,08 % | 40 % |
| zero + vote à 3 réponses | 18,4 s | +0,02 % | 3 % |

La même configuration donne +0,29 % avec `num_ctx` 2048 et +0,15 % avec 4096. Cet écart,
dû au calcul sur le GPU, donne **l'ordre de grandeur du bruit**.

### 3.6 Période N : épisodes complets avec le LLM (50 min, 6 scénarios)

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

---

## 4. Ordre de démonstration conseillé (15 min)

| Temps | Quoi | Commande ou fichier |
|---|---|---|
| 1 min | Le principe : le LLM conseille, le RL exécute, le bouclier décide en dernier | Schéma de `docs/LLM_DESIGN.md`, section 3 |
| 4 min | **La preuve que le LLM agit sur les décisions** : la démo en direct | `.venv\Scripts\python scripts\llm_demo.py` (secours : `type docs\demo\llm_demo_emergency.txt`) |
| 3 min | Le code, aux bons endroits | `docs/VISITE_DU_CODE.md`, étapes 2, 6 et 7 |
| 2 min | Les réglages, et le choix du modèle | `Get-Content configs\llm.yaml` ; `type results\exploration\llm_benchmark\step2_choice.json` |
| 2 min | La sécurité : tests adverses et attaque contre le bouclier | `.venv\Scripts\python -m pytest tests\test_llm_security.py -v` |
| 2 min | Les résultats, honnêtement, avec l'oracle | `.venv\Scripts\python scripts\llm_results_table.py` |
| 1 min | LoRA, le prompt tuning, et le piège de la classe majoritaire | Section 3.2 |

---

## 5. Limites, dites honnêtement

- **Pas de gain.**
  - Sur la validation, aucun conseiller n'améliore nettement les scores : le LLM fait
    +0,16 %, le placebo +0,09 %, les règles −0,17 %.
  - L'oracle ne gagne que 1,09 %, en partie par chance : COOP-FULL laisse peu de marge.
- **Une seule graine de validation.**
  - Les écarts entre réglages sont de l'ordre du bruit : la même configuration varie de
    0,15 point entre deux tailles de contexte.
  - Les choix de l'étape 2 sont donc peu discriminants, ce qui explique les règles de
    choix fixées à l'avance.
- **Le LLM conseille partout et suit mal les principes.**
  - Il conseille dans toutes les situations (100 % de faux conseils).
  - Il cite souvent les carrefours dans l'ordre de la liste, et propose parfois la phase
    inverse de celle dont l'ambulance a besoin (voir la démo).
- **Le changement de mode n'est pas réalisé**, ni l'ablation par masque d'actions.
- **LoRA et prompt tuning sont préliminaires.**
  - Le lot final ne compte que 169 exemples d'entraînement, et sa validation seulement
    15 situations étiquetées « conseil » (8 dans le lot préliminaire).
  - Les étiquettes sont bruitées : le meilleur de quelques candidats sur 5 min.
  - Un seul petit modèle (0,5B) ; le 1,5B n'a pas été essayé.
  - Résultat : LoRA +0,05 %, prompt tuning −0,09 %, dans le bruit.
- **Biais en faveur des règles à l'étape 2.** Dans le benchmark de l'étape 2, les règles
  ont été rejouées sans délai. C'est corrigé dans l'oracle et dans l'évaluation
  pré-enregistrée (8,2 s pour tous).
- **Latence.** 8 s par conseil sur la puce graphique intégrée (Iris Xe), 27 à 50 s avec les
  outils. Elle est modélisée : un conseil n'agit qu'après ce délai.
- **Détection des capteurs en panne.** Le détecteur d'événements lit l'information du
  scénario : on suppose la panne signalée.
- **Évaluation finale non faite.** Les graines de test 0 à 4 n'ont pas été lancées, et les
  tests statistiques ne sont donc pas encore appliqués.

---

## 6. LoRA et prompt tuning : données et étapes sur Kaggle

| Lot | Fichiers | Exemples | Graines | Étiquettes | Rôle |
|---|---|---|---|---|---|
| Préliminaire | `results/exploration/llm_lora/preliminary/` | 69 entraînement (42 abstentions, 27 conseils) ; 63 validation (**55 abstentions, 8 conseils**) | 100001 (entraînement), 1000 (validation) | Rejeux sans délai ; validation : règles ou abstention | Test du notebook ; chiffres de la section 3 |
| **Final** | `results/exploration/llm_lora/` | **169 entraînement (119 abstentions, 50 conseils)** ; 63 validation (**48 abstentions, 15 conseils**) | 100001 à 100003 (entraînement), 1000 (validation) | Rejeux avec le même délai pour tous (8,2 s) ; meilleur candidat, ou abstention sous 0,25 % | **Résultats présentés** (sections 3.1 et 3.2) ; sorties dans `llm_lora/final_*` et `llm_benchmark/final_*` |

Les graines d'entraînement servent uniquement à l'entraînement, et la graine 1000
uniquement à la mesure. Les graines de test 0 à 4 ne sont pas utilisées.

Étapes sur Kaggle (notebook `notebooks/llm_lora_colab.ipynb`, compatible Kaggle et Colab) :

1. Create > New Notebook > File > Import Notebook : `notebooks/llm_lora_colab.ipynb`.
2. Settings :
   - **GPU T4 x2** (le notebook n'en utilise qu'un) ;
   - **Internet on**, nécessaire pour installer les bibliothèques et télécharger le modèle.
3. Add Input > Upload > New Dataset : les deux fichiers du **lot final**.
4. Run All : environ 20 à 30 min avec 0,5B. Pour 1,5B, changer `MODEL` dans la cellule 4,
   et compter 30 à 45 min.
5. Récupérer dans l'onglet Output :
   - `lora_comparison.csv` ;
   - les prédictions `*_calls.csv` et `*_models.csv`.
6. En local, copier les `.csv` dans `results/exploration/llm_benchmark/`, avec un préfixe
   (par exemple `final_lora_calls.csv`), puis rejouer les prédictions dans SUMO :

```powershell
.venv\Scripts\python scripts\llm_benchmark.py --reuse-calls final_lora --techniques lora --betas 4 --tag final_lora_val
```

---

## 7. Prochaines étapes

1. **LoRA plus solide** : essayer Qwen2.5-1.5B, plus d'exemples (d'autres graines
   d'entraînement), et des étiquettes moins bruitées (rejeux plus longs). Le lot final
   (0,5B, 169 exemples) ne donne pas de gain mesurable.
2. **Évaluation sur les graines de test 0 à 4**, comme le prévoit
   `docs/LLM_PREREGISTRATION.md`.
   - Contrôleurs : COOP-FULL seul, + LLM, + placebo, + règles (même latence pour tous), et
     l'oracle au niveau des situations.
   - Volume : 15 runs par scénario.
   - Tests : Mann-Whitney avec la correction de Holm, dans une famille « llm » séparée.
   - Durée : environ 24 à 28 h de calcul, 16 h avec le plan réduit.
3. **Pistes, puisque l'oracle montre une marge faible :**
   - viser les situations où COOP-FULL est le plus faible ;
   - donner au LLM ce que PPO n'a pas : l'état au-delà des voisins, une prévision de la
     demande ;
   - ne laisser le LLM conseiller que les carrefours cités par un événement ;
   - réaliser le changement de mode (`coop_full_ev4` pendant une urgence).

---

## État des tests

Résultats de la suite complète au 26/10/2026 :

| Suite | Réussis | Échoués | Dont la partie LLM |
|---|---|---|---|
| pytest | **200** | 0 | 58 tests : `test_llm.py` (27), `test_llm_security.py` (10), `test_llm_tools.py` (12), `test_llm_settings.py` (2), `test_llm_snapshot.py` (1), et le garde du bouclier `test_shield_guard.py` (6) |
| Vitest | **110** | 0 | – (tableau de bord) |
| Playwright | **37** | 0 | – (tableau de bord) |

La suite Playwright compte 37 tests. Le chiffre de 38 donné dans l'audit de l'étape 1 était
une erreur de comptage : les fichiers de tests n'ont pas changé depuis.

---

## Où trouver quoi

| Sujet | Fichier |
|---|---|
| Conception, schéma, flux pas à pas | `docs/LLM_DESIGN.md` |
| Visite du code devant le prof | `docs/VISITE_DU_CODE.md` |
| 15 questions probables | `docs/FICHE_QUESTIONS_LLM.md` |
| Commandes de démo | `docs/DEMO_GUIDE.md`, section « Démo LLM » |
| Réglages justifiés | `configs/llm.yaml` |
| Pré-enregistrement | `docs/LLM_PREREGISTRATION.md` |
| Code | `src/cotraffic/llm/` (advice, advised, client, prompts, situation, snapshot, rollout, sources, tools, settings) |
| Tests | `tests/test_llm.py`, `test_llm_security.py`, `test_llm_tools.py`, `test_llm_settings.py`, `test_llm_snapshot.py` |
| Résultats de validation | `results/exploration/llm_benchmark/`, `llm_period/`, `llm_fewshot/`, `llm_oracle/`, `llm_summary/` |
| Jeux de données LoRA | `results/exploration/llm_lora/` (final), `llm_lora/preliminary/` |
| Sorties de démo (secours) | `docs/demo/llm_demo_emergency.txt`, `docs/demo/llm_tools_demo.txt` |
