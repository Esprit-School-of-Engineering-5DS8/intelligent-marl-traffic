# CoTraffic : feux de circulation multi-agents coopératifs

Projet de fin d'études AI & Data Science (Esprit, 5DS8), *Intelligent Multi-Agent Traffic
Management*. Branche de Rami Ben Slimene.

Chaque carrefour à feux est un **agent d'apprentissage par renforcement** autonome. Les agents
partagent une même politique (PPO avec partage des paramètres), échangent de courts messages
avec leurs voisins, passent par un **bouclier de sécurité** qui rend impossible toute séquence
de feux dangereuse, et apprennent à réduire l'attente pondérée par personne en tenant compte du
CO2, des véhicules d'urgence et des piétons. Ils sont comparés aux feux à temps fixe (Webster),
aux feux actionnés, à Max-Pressure et à des règles de préemption pour les urgences, sur une
grille synthétique et sur un quartier réel de Tunis importé d'OpenStreetMap, en trafic normal,
de pointe, avec accident, urgences, piétons, bus et pannes.

- Simulation : [SUMO](https://eclipse.dev/sumo/) 1.27 via libsumo, CPU uniquement.
- Apprentissage : PettingZoo + Stable-Baselines3 (PPO et DQN), partage des paramètres via SuperSuit.
- Tableau de bord : React + TypeScript (carte deck.gl, 3D three.js, graphiques ECharts),
  backend FastAPI optionnel, assistant avec modèle de langage local (Ollama).

La branche contient **tout le travail et tous les résultats** : code, configurations, réseaux,
modèles entraînés, 1 395 simulations d'évaluation, statistiques, figures, tableau de bord et
replays. On peut donc lancer le tableau de bord et les démonstrations sans rien réentraîner
(section 4), ou tout reproduire depuis zéro (section 6).

---

## Sommaire

1. [Résultats principaux](#1-résultats-principaux)
2. [Organisation du dépôt](#2-organisation-du-dépôt)
3. [Installation](#3-installation)
4. [Démarrage rapide : version fonctionnelle en 10 minutes](#4-démarrage-rapide--version-fonctionnelle-en-10-minutes)
5. [Démonstrations dans SUMO](#5-démonstrations-dans-sumo)
6. [Reproduire tout le travail étape par étape](#6-reproduire-tout-le-travail-étape-par-étape)
7. [Le tableau de bord en détail](#7-le-tableau-de-bord-en-détail)
8. [L'assistant (modèle de langage local)](#8-lassistant-modèle-de-langage-local)
9. [Tests et qualité](#9-tests-et-qualité)
10. [Méthodologie et reproductibilité](#10-méthodologie-et-reproductibilité)
11. [Dépannage](#11-dépannage)
12. [Documentation](#12-documentation)

---

## 1. Résultats principaux

Matrice complète : 1 290 simulations d'évaluation (expérience principale, matrice étendue,
sensibilité) plus 105 simulations DQN, 5 graines de test par cellule, 3 entraînements par agent
appris (modèle choisi sur des graines de validation). Tous les tableaux, avec intervalles de
confiance à 95 % et tests : `results/summary/REPORT_TABLES.md` ; rédaction par question de
recherche : `docs/report/08_results.md`.

Temps de trajet moyen (s), trafic normal (plus bas = meilleur ; meilleur en gras) :

| Réseau, demande | FT | ACT | MP | IND | COOP | COOP-FULL | DQN |
|---|---|---|---|---|---|---|---|
| grille 4x4, faible | 171,4 | **145,0** | 148,5 | 150,8 | 150,8 | 151,9 | 151,4 |
| grille 4x4, moyenne | 179,8 | **157,3** | 157,9 | 161,1 | 161,0 | 161,1 | 160,6 |
| grille 4x4, pointe | 261,2 | 275,3 | **210,2** | 217,5 | 224,6 | 219,7 | 331,0 |
| grille 4x4, profil de pointe | 209,2 | 195,0 | **179,9** | 184,5 | 186,7 | 184,5 | 183,5 |
| quartier, moyenne | 112,7 | 109,9 | **109,4** | 109,7 | 109,9 | 109,9 | 109,8 |
| quartier, pointe | 196,8 | 158,3 | **153,4** | 158,4 | 159,5 | 156,5 | 159,7 |
| grille 8x8, pointe (entraîné sur 4x4) | 365,5 | - | **300,7** | 312,7 | 313,1 | - | 312,9 |

Ce qu'il faut retenir :

- **Les agents appris battent nettement les feux à temps fixe** : −36 % d'attente moyenne en
  pointe sur la grille pour COOP-FULL (58,1 s contre 91,1 s), −43 % sur le quartier ; 16 gains
  significatifs sur 18 scénarios après correction de Holm.
- **Max-Pressure reste le meilleur contrôleur sur ces réseaux** : il est le meilleur dans 4
  cellules sur 6 et à moins de 2,4 % du meilleur partout. Les agents appris sont 0,2 à 7 % plus
  lents que le meilleur contrôleur de chaque cellule ; les écarts avec MP ne sont pas
  significatifs.
- **Urgences** : COOP-FULL divise par deux le retard des ambulances par rapport à FT (73,5 s
  contre 154,7 s en pointe sur la grille), mais une règle de préemption sur Max-Pressure
  (EV-RULE-MP) fait mieux (38,1 s) pour un coût de +0,4 % de temps de trajet.
- **Piétons** : en demande moyenne, COOP-FULL réduit l'attente piétonne de 24 % par rapport à une
  règle piétons sur Max-Pressure, pour +2,6 % de temps de trajet. En pointe, COOP-FULL se bloque
  dans 4 runs sur 15 (`docs/FAILURES.md`, F-014) : c'est la principale limite.
- **Pannes de capteurs** : IND perd 1,4 % de temps de trajet, Max-Pressure 21,5 %.
- **Généralisation** : la politique entraînée sur 16 carrefours tourne telle quelle sur 64, à
  4 % de Max-Pressure.
- **DQN** (même observation et même récompense qu'IND) fait aussi bien qu'IND partout sauf en
  pointe sur la grille : 2 runs sur 15 s'y bloquent (plus de 2 000 véhicules non arrivés), ce
  qui porte la moyenne à 331 s alors que les autres runs restent entre 200 et 260 s. PPO est
  plus stable dans notre cadre.
- **Ce qui n'a pas marché** : les messages entre voisins (F-009), la refonte de la récompense
  (F-007) et la prévision des arrivées n'ont pas comblé l'écart avec Max-Pressure.
- **Contribution** : un banc d'essai équitable et reproductible (même bouclier, mêmes graines,
  mêmes statistiques pour toutes les méthodes) et le diagnostic de pourquoi l'apprentissage ne
  bat pas Max-Pressure ici (F-007, F-009, F-013).

![Temps de trajet par niveau de demande](figures/fig02_travel_time_by_demand.png)

---

## 2. Organisation du dépôt

```
configs/          tous les paramètres (aucun nombre magique dans le code)
  protocol.yaml     cadence des décisions (5 s), feux (jaune 3 s, vert 10-60 s), protocole d'évaluation
  networks/         grid4x4, grid8x8, real_district (OSM Tunis), real_district_ped
  demand/           low, medium, peak, rush_profile
  scenarios/        normal, emergency, incident, pedestrians, buses, sensor_noise, comm_dropout_*
  agents/           ind, coop, coop_eco, coop_full, coop_forecast, dqn, variantes de sensibilité
  experiments/      core, extended, full_matrix, sensitivity, dqn, extra
src/cotraffic/    le package Python
  networks/         construction des réseaux (netgenerate, netconvert)
  demand/           génération du trafic (Poisson, duarouter), bus, urgences, piétons, accident
  envs/             environnement PettingZoo : carrefour, observations, récompense, bouclier
  controllers/      FT, ACT, MP, préemption urgences, règle piétons, politique apprise
  training/         entraînement PPO/DQN, sélection des modèles, normalisation des récompenses
  evaluation/       simulations d'évaluation, métriques, matrice d'expériences, mesures extra
  analysis/         statistiques (bootstrap, Mann-Whitney, Holm, Cliff), figures, tableaux
  forecasting/      prévision du trafic entrant (Ridge)
  explainability/   décisions expliquées, importance des groupes de variables
  assistant/        assistant : lecture des questions, recherche dans les résultats, rédaction
api/              backend FastAPI du tableau de bord
frontend/         tableau de bord React + TypeScript
scripts/          démonstrations SUMO, export des données, enregistrement des replays
dashboard/        ancien tableau de bord Streamlit (toujours fonctionnel)
sumo_files/       réseaux SUMO générés
results/          raw/ (1 ligne par simulation), summary/ (statistiques), logs/, training/, checkpoints/
figures/          figures du rapport (PNG + SVG)
notebooks/        entraînement sur Kaggle et Colab
docs/             décisions (ADR), journal d'expériences, échecs, rapport, guide de démonstration
tests/            tests pytest
```

---

## 3. Installation

### Prérequis

| Outil | Version | Pour quoi |
|---|---|---|
| Python | 3.10 à 3.12 | simulations, entraînement, analyse, backend |
| Node.js | 22 ou plus | tableau de bord |
| Git | récent | cloner la branche |
| Ollama | facultatif | assistant avec modèle de langage local |

SUMO s'installe avec pip : aucune installation système n'est nécessaire. Tout tourne sur CPU.
Prévoir environ 3 Go d'espace disque (dépendances Python et Node comprises).

### Cloner la branche

```bash
git clone -b rami-benslimene https://github.com/Esprit-School-of-Engineering-5DS8/intelligent-marl-traffic.git
cd intelligent-marl-traffic
```

### Environnement Python

```bash
python -m venv .venv
# Windows (PowerShell) : .venv\Scripts\activate
# Linux / macOS        : source .venv/bin/activate
pip install torch==2.14.0 --index-url https://download.pytorch.org/whl/cpu   # version CPU, plus légère
pip install -r requirements.txt
pip install -e . --no-deps
```

Sous Windows, si PowerShell refuse d'activer l'environnement :
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

### Tableau de bord

```bash
cd frontend
npm install
npx playwright install chromium     # uniquement pour les tests de bout en bout
cd ..
```

### Vérifier l'installation

```bash
python -m pytest -q          # 142 tests, moins d'une minute
python -m cotraffic smoke    # passe rapide sur chaque fonctionnalité, quelques minutes
```

---

## 4. Démarrage rapide : version fonctionnelle en 10 minutes

Les résultats et les modèles entraînés sont dans la branche : il suffit de lancer.

```bash
# 1. le tableau de bord, sur les vrais résultats exportés (aucun backend nécessaire)
cd frontend
npm run dev                  # ouvrir http://localhost:5173
```

```bash
# 2. facultatif : le backend (assistant avec modèle local, lancement de simulations, temps réel)
#    depuis la racine du dépôt, dans un deuxième terminal
uvicorn api.main:app --port 8000
#    puis, dans le tableau de bord : Paramètres > Source des données > « Backend en direct »
```

```bash
# 3. facultatif : le modèle de langage local de l'assistant
ollama pull qwen2.5:3b
python -m cotraffic llm-status
```

```bash
# 4. une démonstration SUMO : FT contre COOP-FULL, avec piétons, ambulances, bus et accident
python scripts/demo_side_by_side.py --net grid4x4 --scenarios pedestrians emergency buses --follow-incident --quick
```

Le guide de la soutenance (déroulé, chiffres à citer, questions probables, plan B) est dans
[docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md).

---

## 5. Démonstrations dans SUMO

`scripts/demo_side_by_side.py` ouvre deux fenêtres SUMO côte à côte sur exactement le même trafic
(même demande, mêmes événements, même graine), plus une fenêtre de graphique en direct.

```bash
# scénario complet sur la grille, caméra sur l'accident
python scripts/demo_side_by_side.py --net grid4x4 --scenarios pedestrians emergency buses --follow-incident --quick

# la meilleure règle pour les ambulances contre l'agent, caméra qui suit chaque ambulance
python scripts/demo_side_by_side.py --left ev_rule_mp --net grid4x4 --scenarios emergency --follow-ev --quick

# le quartier réel de Tunis (avec trottoirs ajoutés pour la démonstration)
python scripts/demo_side_by_side.py --left ev_rule_mp --net real_district_ped --scenarios emergency pedestrians buses --follow-incident --quick

# un seul épisode dans sumo-gui, en vue 3D
python scripts/open_in_sumo.py --net grid4x4 --3d
```

| Option | Valeurs |
|---|---|
| `--left`, `--right` | `ft`, `act`, `mp`, `ev_rule`, `ev_rule_mp`, `ped_rule_mp`, `ind`, `coop`, `coop_full` (par défaut `ft` contre `coop_full`) |
| `--net` | `grid4x4`, `real_district`, `real_district_ped` |
| `--scenarios` | une ou plusieurs valeurs parmi `emergency`, `pedestrians`, `buses`, `incident` |
| `--follow-incident` | ajoute l'accident et place la caméra sur la rue bloquée |
| `--follow-ev` | la caméra suit chaque véhicule d'urgence |
| `--quick` | épisode court (environ 3 minutes) |
| `--snapshot-at 900 1800` | captures d'écran des deux fenêtres à ces instants |

`pedestrians` n'existe pas sur `real_district` (le réseau OSM n'a presque pas de trottoirs) :
utiliser `real_district_ped`.

---

## 6. Reproduire tout le travail étape par étape

Chaque étape lit les sorties de la précédente. Les commandes `make` sont des alias de la CLI
Python : tout fonctionne aussi sous Windows sans `make`. `python -m cotraffic <commande> --help`
liste les options. Pour les commandes longues, désactiver la mise en veille du PC.

### Étape 1 : réseaux routiers

```bash
python -m cotraffic networks --all
```

- `grid4x4` et `grid8x8` sont générés par `netgenerate` (tronçons de 250 m, 2 voies, 50 km/h,
  trottoirs et passages piétons).
- `real_district` est importé d'OpenStreetMap (centre de Tunis) par `netconvert` : 7 carrefours
  à feux.

Résultat : `sumo_files/<réseau>/<réseau>.net.xml`.

### Étape 2 : calibration de la demande (déjà faite, facultatif)

```bash
python -m cotraffic calibrate-demand --net grid4x4 --scales 0.8 1.0 1.2 1.4
```

Balayage du débit de pointe : en pointe, FT doit être clairement congestionné sans blocage
permanent. Le débit retenu est dans `configs/networks/`.

### Étape 3 : constantes de normalisation des récompenses

```bash
python -m cotraffic calibrate --net grid4x4
python -m cotraffic calibrate --net real_district
```

Chaque terme de la récompense (attente, CO2, urgences, piétons) est ramené autour de 1 à partir
de simulations de référence. Résultat : `configs/reward_norm/`.

### Étape 4 : entraînement des agents

```bash
python -m cotraffic train --agent coop_full --net grid4x4 --seed 1
```

À répéter pour chaque agent, réseau et graine :

| Agents | Réseaux | Graines |
|---|---|---|
| `ind`, `coop`, `coop_full` | `grid4x4`, `real_district` | 1, 2, 3 |
| `coop_eco05`, `coop_eco`, `coop_forecast`, `coop_full_ev1`, `coop_full_ev4`, `dqn` | `grid4x4` (et `real_district` pour `dqn`) | 1, 2, 3 |

- 500 000 décisions par entraînement ; à chaque épisode, un niveau de demande et une graine
  d'entraînement sont tirés au hasard.
- Une sauvegarde toutes les 50 000 décisions ; relancer la même commande reprend un
  entraînement interrompu.
- `coop_forecast` demande d'abord le modèle de prévision : `python -m cotraffic forecast --net grid4x4`.
- Pour répartir les entraînements entre plusieurs machines, Kaggle
  (`notebooks/kaggle_train.ipynb`) ou Colab (`notebooks/colab_train.ipynb`) : voir
  `docs/RUN_PLAN.md`.

Résultat : `results/training/<agent>/<réseau>/seed<k>/` (checkpoints, courbes d'apprentissage).

### Étape 5 : sélection des modèles

```bash
python -m cotraffic select
```

Pour chaque entraînement, les 4 derniers checkpoints sont évalués sur la graine de validation
1000 (demandes moyenne et pointe) ; celui qui a le plus petit temps de trajet moyen est copié dans
`results/checkpoints/<agent>/<réseau>/seed<k>.zip`. Les graines de test ne servent jamais ici.

### Étape 6 : évaluation

```bash
python -m cotraffic evaluate --experiment full_matrix --jobs 2    # expérience principale + matrice étendue
python -m cotraffic evaluate --experiment sensitivity --jobs 2    # prévision, poids des urgences, règles
python -m cotraffic evaluate --experiment dqn --jobs 2            # comparaison PPO / DQN
python -m cotraffic evaluate --experiment extra --extra --jobs 2  # mesures piétons et urgences détaillées
```

- Chaque simulation : 15 min de chauffe, 60 min mesurées, 15 min de vidange, sur 5 graines de test.
- Les simulations déjà faites sont sautées : la commande peut être relancée sans risque.

Résultat : une ligne par simulation dans `results/raw/` (et `results/extra/` pour les mesures extra).

### Étape 7 : statistiques, figures, tableaux

```bash
python -m cotraffic aggregate     # moyennes, IC 95 % (bootstrap), Mann-Whitney, Holm, Cliff
python -m cotraffic figures       # figures du rapport dans figures/
python -m cotraffic tables        # results/summary/REPORT_TABLES.md
python -m cotraffic explain --agent coop_full --net grid4x4   # décisions expliquées, importance
```

### Étape 8 : données du tableau de bord

```bash
python scripts/export_dashboard_data.py
python scripts/record_replay.py --net grid4x4 --scenarios emergency --demand peak --left ft --right coop_full
python scripts/export_dashboard_data.py --skip-networks
```

- `export_dashboard_data.py` convertit les résultats en fichiers JSON dans `frontend/public/data/`.
- `record_replay.py` enregistre le même épisode sous deux contrôleurs pour la carte et la 3D
  (environ 5 minutes par replay).

Tout enchaîner d'un coup : `make reproduce` (ou `bash scripts/reproduce_all.sh` sous Git Bash) ;
avec `TRAIN=1`, réentraîne aussi les agents manquants (plusieurs heures).

---

## 7. Le tableau de bord en détail

### D'où viennent les chiffres

```
SUMO -> results/raw (1 ligne par simulation) -> aggregate -> results/summary
     -> scripts/export_dashboard_data.py -> frontend/public/data/*.json
     -> tableau de bord : fichiers statiques  OU  backend FastAPI (mêmes fichiers)
```

- **Sans backend**, les chiffres sont les vrais résultats, figés au moment de l'export ; la date
  d'export est affichée dans « Provenance des données ». Le navigateur ne simule rien.
- **Avec le backend**, les chiffres sont identiques. Il ajoute l'assistant avec modèle local, le
  lancement de vraies simulations depuis la page Scénarios, et l'état en temps réel (WebSocket
  avec reconnexion automatique).

### Les pages

| Page | Contenu |
|---|---|
| Vue d'ensemble | Indicateurs d'un contrôleur face à une référence (IC 95 %, gain apparié, significativité), barres par contrôleur, véhicules arrêtés minute par minute, provenance des données |
| Carte en direct | Replay côte à côte de deux contrôleurs sur le même trafic (deck.gl), feux aux lignes d'arrêt, détail d'un carrefour, suivi du véhicule d'urgence |
| Simulation 3D | Le même replay en 3D (three.js) : rotation, zoom, déplacement |
| Agents RL | Courbes d'apprentissage par graine (PPO, DQN), décomposition de la récompense, décisions expliquées et corrections du bouclier |
| Analyse comparative | Forest plot des gains, carte des gains, tableau des tests (export CSV), distribution des attentes |
| Assistant | Questions en langage courant, réponses chiffrées avec sources, graphiques, propositions d'actions confirmées par l'utilisateur |
| Scénarios | Replays enregistrés, formulaire pour en lancer un nouveau (backend), export CSV |
| Piétons | Attente moyenne, P95 et maximale, traversées au vert, durée du vert selon la foule, compromis piétons / véhicules |
| Urgences | Retard des ambulances, arrêts au rouge, erreur d'ETA, effet sur les autres usagers, journal des interventions |
| Paramètres | Thème, langue (français, anglais, arabe de droite à gauche), unités, source des données, modèle de l'assistant |

### Technologies

React 19 + TypeScript strict + Vite, Tailwind CSS et composants Radix, Zustand, TanStack Query,
Zod, ECharts, deck.gl, React Three Fiber, React Hook Form, i18next ; backend FastAPI (SSE,
WebSocket). Détails : [frontend/README.md](frontend/README.md) ; contrat des données et de l'API :
[docs/API_CONTRACT.md](docs/API_CONTRACT.md).

---

## 8. L'assistant (modèle de langage local)

L'assistant répond en français aux questions sur les résultats, dans le tableau de bord (Ctrl+K)
et en ligne de commande. Un petit modèle tourne sur le portable via [Ollama](https://ollama.com) :
gratuit, hors ligne, sans compte.

```bash
# Windows : winget install --id Ollama.Ollama -e --source winget   (ou l'installateur d'ollama.com)
ollama pull qwen2.5:3b
python -m cotraffic llm-status
python -m cotraffic ask "Compare COOP et MP sur le quartier à la pointe" --table
python -m cotraffic ask "Quel est le meilleur contrôleur à la pointe sur la grille ?" --no-llm
python -m cotraffic demo-plan "MP contre COOP-FULL à Tunis avec un accident et des piétons" --run
```

1. Des mots-clés lisent la question ; le modèle ne lit que celles qu'ils ne savent pas classer.
2. Le code cherche la réponse dans `results/summary/` et les journaux de décisions.
3. Le modèle rédige ; si un seul nombre de son texte n'est pas dans les résultats, la phrase
   écrite par le code le remplace.

Sans Ollama, tout fonctionne encore (réponses écrites par le code, voir ADR-011).
`COTRAFFIC_LLM_MODEL` choisit un autre modèle, par exemple `qwen2.5:7b` (meilleur, plus lent).
Dans le tableau de bord, sans backend, l'assistant calcule ses réponses directement dans le
navigateur à partir des résultats exportés. Lancer une simulation demande toujours une
confirmation, et aucune clé d'API n'est stockée dans le navigateur.

---

## 9. Tests et qualité

```bash
# Python
python -m pytest -q                         # 142 tests (environnement, bouclier, métriques, statistiques...)
python -m ruff check src tests scripts api  # style
python scripts/check_assistant.py --no-write   # précision de lecture de l'assistant

# tableau de bord (dans frontend/)
npm run lint                  # ESLint (TypeScript, hooks React, accessibilité)
npm run typecheck             # TypeScript strict
npm test                      # 26 tests unitaires (Vitest)
npm run e2e                   # 37 tests de bout en bout (Playwright) : pages, assistant, accessibilité WCAG 2.1 AA
npm run build                 # build de production
```

Pour regarder les tests du navigateur au ralenti pendant une présentation (PowerShell) :

```powershell
$env:SLOWMO = "300"
npx playwright test tests/e2e/pages.spec.ts --headed
Remove-Item Env:SLOWMO
```

Les tests de bout en bout lisent les fichiers de résultats et vérifient que chaque page affiche
exactement les mêmes nombres. Un hook de pré-commit formate et vérifie les fichiers modifiés, et
le workflow GitHub `frontend` rejoue toutes ces vérifications.

---

## 10. Méthodologie et reproductibilité

- **Agents** : un agent par carrefour à feux, décision toutes les 5 s, bouclier (vert minimum
  10 s, maximum 60 s si d'autres attendent, anti-famine à 90 s, jaune de 3 s automatique).
  Récompense de base : baisse de l'attente accumulée sur les voies d'entrée du carrefour.
- **Graines séparées** : entraînement (100 000 et plus), validation (1 000 à 1 999), test (0 à
  999 ; 0 à 4 utilisées). `evaluate` et `select` refusent une graine hors de sa plage.
- **Trafic identique pour tous** : chaque composant (voitures, bus, urgences, piétons) a son propre
  générateur aléatoire dérivé de la graine ; tous les contrôleurs voient exactement le même
  trafic, ce qui permet les comparaisons appariées.
- **Statistiques** : intervalles de confiance à 95 % par bootstrap à deux niveaux (entraînements et
  graines de test), test de Mann-Whitney, correction de Holm par famille de tests (principale,
  exploratoire, DQN), taille d'effet par le delta de Cliff.
- **Traçabilité** : chaque ligne de résultat enregistre méthode, réseau, scénario, demande,
  graine, modèle et commit git.
- **Déterminisme vérifié** : les 340 simulations refaites avec les mesures supplémentaires donnent
  exactement les mêmes métriques que les simulations d'origine.

---

## 11. Dépannage

| Problème | Solution |
|---|---|
| `.venv\Scripts\activate` n'est pas reconnu | Se placer d'abord dans le dossier du projet (`cd intelligent-marl-traffic`), puis relancer |
| PowerShell refuse les scripts | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `argument --net: expected one argument` | Chaque option attend une valeur : `--net grid4x4`, `--scenarios emergency buses` |
| `pedestrians` refusé sur `real_district` | Utiliser `--net real_district_ped` |
| Le tableau de bord affiche « Le backend ne répond pas » | Lancer `uvicorn api.main:app --port 8000` ou revenir à la source « Résultats réels » dans Paramètres |
| La carte ou la 3D indiquent « Aucun replay enregistré » | `python scripts/record_replay.py ...` puis `python scripts/export_dashboard_data.py --skip-networks` |
| La 3D est lente ou indisponible | Le navigateur doit activer WebGL ; la carte 2D montre la même information |
| L'assistant met longtemps à répondre | Le modèle local partage le CPU avec les simulations : 10 à 40 s ; `--fast` ou `--no-llm` en ligne de commande |
| Port 5173 ou 8000 déjà utilisé | `npm run dev -- --port 5174` ou `uvicorn api.main:app --port 8001` (et `VITE_API_URL=http://localhost:8001`) |
| La simulation s'arrête quand le PC se met en veille | Désactiver la mise en veille pour les commandes longues |

---

## 12. Documentation

| Document | Contenu |
|---|---|
| [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md) | Déroulé de la soutenance, chiffres à citer, questions probables, commandes de démonstration |
| [docs/report/](docs/report/) | Sections du rapport : résultats, ablations, limites |
| [docs/decisions/](docs/decisions/) | Décisions d'architecture (ADR 001 à 011) |
| [docs/EXPERIMENT_JOURNAL.md](docs/EXPERIMENT_JOURNAL.md) | Journal des expériences |
| [docs/FAILURES.md](docs/FAILURES.md) | Échecs analysés et leurs causes |
| [docs/RUN_PLAN.md](docs/RUN_PLAN.md) | Répartition des calculs entre machines, Kaggle et Colab |
| [docs/API_CONTRACT.md](docs/API_CONTRACT.md) | Fichiers de données et API du tableau de bord |
| [docs/design_thinking/](docs/design_thinking/) | Démarche Design Thinking |
| [frontend/README.md](frontend/README.md) | Architecture du tableau de bord |
