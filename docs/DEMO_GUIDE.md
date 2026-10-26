# Guide de démonstration du tableau de bord

Déroulé d'environ 12 minutes pour présenter CoTraffic avec le tableau de bord. Tous les
chiffres cités viennent de `frontend/public/data` (export de `results/`) ; ils
s'affichent à l'écran au moment où on les dit.

## Préparation (10 minutes avant)

```bash
# 1. le tableau de bord (suffit pour toute la démo)
cd frontend
npm run dev                      # http://localhost:5173

# 2. facultatif : le backend (assistant avec le modèle local, lancement de simulations)
cd ..
ollama serve                     # si Ollama n'est pas déjà lancé
uvicorn api.main:app --port 8000
```

Vérifier :

- les quatre replays apparaissent dans **Scénarios** (sinon : `frontend/README.md`,
  section Quick start, environ 20 min d'enregistrement) ;
- navigateur en plein écran (F11), zoom 100 %, thème sombre ;
- en mode backend : Paramètres > Source des données > « Backend en direct », badge vert
  « Flux temps réel connecté » en haut. La première réponse du modèle local peut prendre
  20 à 40 s si la machine calcule autre chose : la poser une fois avant la séance.

## Déroulé

### 1. Vue d'ensemble (2 min)

Grille 4x4, trafic normal, pointe ; COOP-FULL contre FT (feux à temps fixe, Webster).

- Phrase en tête : COOP-FULL réduit l'attente moyenne aux feux de **36,2 %** par rapport à
  FT (58,1 s contre 91,1 s), test apparié significatif après correction de Holm.
- Cartes : trajet 220 s contre 261 s, CO2 4 117 kg contre 4 650 kg (-11,5 %).
- Graphique par contrôleur : montrer les intervalles de confiance. Dire honnêtement que
  **Max-Pressure (MP) fait aussi bien** (55,3 s) : la différence entre COOP-FULL et MP
  n'est pas significative. L'apport des agents est ailleurs : apprentissage sans
  modèle du trafic, coopération, prise en compte des urgences et des piétons.
- Courbe des véhicules arrêtés : la zone grise est l'heure mesurée.
- Bas de page : provenance (1 290 simulations d'évaluation, date d'export).

Changer le réseau pour « Quartier réel (OSM) » : -43,4 % d'attente contre FT (39,0 s
contre 69,0 s), là encore au niveau de MP.

### 2. Carte en direct (3 min), le moment fort

Replay « Grille 4x4 · Véhicules d'urgence · Pointe », côte à côte FT | COOP-FULL, même
demande, même graine SUMO.

1. Lecture en ×4 : les véhicules sont colorés par vitesse (vert fluide, orange ralenti,
   rouge à l'arrêt), les points aux lignes d'arrêt sont les feux.
2. Compteurs sous la carte : à la même seconde, FT a nettement plus de véhicules
   arrêtés que COOP-FULL.
3. Panneau Événements : cliquer « ev_1 entre dans le réseau », puis **Suivre le
   véhicule d'urgence**. Sous FT l'ambulance (clignotante) reste prise dans la file ;
   sous COOP-FULL la voie est dégagée.
4. Cliquer un carrefour violet : état de chaque signal et file à moins de 60 m, pour
   les deux contrôleurs.

Chiffres de ce scénario (épisode complet, 5 graines) : retard des véhicules d'urgence
154,7 s avec FT, **73,5 s avec COOP-FULL (-52,5 %, significatif)**.

### 3. Simulation 3D (1 min)

Même replay, même instant (l'horloge est partagée). Glisser pour tourner, molette pour
zoomer, clic droit pour se déplacer ; « Recentrer la vue » si besoin.

### 4. Agents RL (2 min)

- Courbes d'apprentissage de COOP-FULL (PPO, 3 graines) ; changer pour DQN :
  deuxième algorithme, entraîné dans les mêmes conditions.
- Décisions expliquées : carrefour A0, chaque décision avec sa justification ;
  « Décisions corrigées par le bouclier » montre que la sécurité (vert minimum, etc.)
  est garantie par construction, pas apprise.

### 5. Analyse comparative (1 min)

Gain par scénario de COOP-FULL contre FT sur l'attente : tous les points sont à droite de
zéro sauf « Piétons · Pointe », et 16 des 18 gains sont significatifs. Carte des gains : tous les contrôleurs, tous les
scénarios. Tableau des tests : export CSV.

### 6. Urgences et piétons (1 min), les limites assumées

- Urgences, grille, pointe : la règle de préemption **EV-RULE-MP reste meilleure pour les
  ambulances** (38,1 s contre 73,5 s pour COOP-FULL), pour une attente générale
  comparable (56,5 s contre 57,9 s). Sur le quartier réel, COOP-FULL a le plus petit
  retard d'urgence (85,2 s contre 112,6 s pour EV-RULE-MP), mais l'écart avec FT n'y est
  pas significatif après correction.
- Piétons, pointe : COOP-FULL garde une attente piétonne basse (16,6 s) mais l'attente des
  véhicules monte (152 s, contre 91,6 s pour PED-RULE-MP) : graphique « Compromis
  piétons / véhicules ». C'est la principale piste d'amélioration.

### 7. Assistant (2 min)

Ctrl+K depuis n'importe quelle page :

1. « COOP-FULL est-il meilleur que FT sur l'attente en pointe dans le quartier réel ? »
   (réponse chiffrée, intervalle de confiance, p de Holm, fichiers sources) ;
2. « Montre le graphique du CO2 sur la grille » (graphique dans la conversation) ;
3. « Les véhicules d'urgence passent-ils plus vite avec COOP-FULL qu'avec EV-RULE-MP ? »
   (l'assistant répond « moins bien » : il ne flatte pas le modèle) ;
4. en mode backend : « Lance une simulation urgences sur la grille » : l'assistant
   **propose** le lancement, rien ne démarre sans « Confirmer ».

Point à souligner : les chiffres ne sont jamais inventés. Sans backend, la réponse est
calculée dans le navigateur ; avec le modèle local, son texte n'est gardé que si chaque
nombre correspond à un résultat. Aucune clé d'API dans le navigateur.

### 8. Paramètres (30 s)

Langue arabe : toute l'interface passe de droite à gauche. Thème clair. Unités (minutes,
m/s).

## Questions probables

- **Pourquoi pas meilleur que Max-Pressure ?** MP est un contrôleur fort sur grille
  régulière ; nos agents l'égalent sans connaître le modèle du trafic et ajoutent la
  coopération, l'urgence et les piétons dans la récompense. Les tests ne montrent pas de
  différence significative, et nous le disons.
- **D'où viennent les intervalles ?** Bootstrap sur les entraînements (3 graines) et les
  graines de test (5) ; test de Mann-Whitney (rangs, sans hypothèse de loi normale),
  correction de Holm par famille de tests, taille d'effet par le delta de Cliff.
- **Le replay est-il truqué ?** Ce sont deux épisodes d'évaluation ordinaires (même
  demande, même graine), enregistrés par `scripts/record_replay.py` ; les résultats de
  l'épisode complet sont affichés sous la carte.
- **Temps réel ?** En mode backend, l'état du serveur et des simulations arrive par
  WebSocket (reconnexion automatique) ; une simulation lancée depuis Scénarios apparaît
  dans les replays une fois terminée (quelques minutes).

## Plan B

| Problème | Solution |
| --- | --- |
| Backend ou Ollama indisponible | Rester sur « Résultats réels » : toutes les pages et l'assistant fonctionnent sans backend |
| 3D lente ou WebGL absent | Montrer la carte 2D, qui contient la même information |
| Replay manquant | Le choisir dans un autre scénario, ou l'enregistrer la veille (`scripts/record_replay.py`) |
| Écran trop petit | Menu réduit (bouton en bas à gauche), vue d'un seul contrôleur au lieu du côte à côte |

## Démo rapide en commandes (PowerShell)

À lancer depuis `G:\pi5eme\cotraffic`, l'environnement Python activé
(`.venv\Scripts\activate`). Durées mesurées sur notre portable.

### 1. Scénario complet dans SUMO : piétons, ambulances, bus, accident (environ 3 min)

```powershell
python scripts/demo_side_by_side.py --net grid4x4 --scenarios pedestrians emergency buses --follow-incident --quick
```

Deux fenêtres SUMO côte à côte (FT à gauche, COOP-FULL à droite) sur exactement le même
trafic, plus une troisième fenêtre avec le graphique de comparaison en direct. La
simulation avance jusqu'à 1 min avant l'accident et la caméra se place sur la rue
bloquée (véhicule magenta, zone rouge clignotante). Ambulances blanches à croix verte,
bus orange, piétons bleus. Molette pour zoomer, glisser pour se déplacer.

Variante sur le vrai quartier de Tunis (avec trottoirs ajoutés pour la démonstration) :

```powershell
python scripts/demo_side_by_side.py --net real_district_ped --follow-incident --quick
```

### 2. Comparaison avec graphique (environ 3 min)

```powershell
# ambulances : la meilleure règle classique contre l'agent, la caméra suit chaque ambulance
python scripts/demo_side_by_side.py --net grid4x4 --scenarios emergency --left ev_rule_mp --follow-ev --quick

# les mêmes comparaisons, chiffrées sur les 5 graines de test
python -m cotraffic ask "Compare COOP-FULL et MP sur la grille à la pointe" --no-llm --table

# puis le tableau de bord : Vue d'ensemble, puis Analyse comparative (forest plot, carte des gains)
cd frontend
npm run dev
```

### 3. Tests du front : chaque page vérifiée avec les vrais chiffres (environ 4 min)

```powershell
cd frontend
npm test                                              # 26 tests unitaires (Vitest)
$env:SLOWMO = "300"
npx playwright test tests/e2e/pages.spec.ts --headed   # le navigateur visite chaque page sous vos yeux
Remove-Item Env:SLOWMO
npx playwright test                                   # toute la suite : pages, assistant, accessibilité WCAG
npx playwright show-report                            # rapport HTML des tests
```

`pages.spec.ts` lit les fichiers de résultats et vérifie que chaque page affiche les
mêmes nombres (attente de COOP-FULL et de FT, gain apparié, significativité, attente des
piétons, retard des ambulances), que le replay avance, que la 3D s'affiche et que les
minutes s'appliquent partout.

### 4. Assistant en détail (environ 5 min)

```powershell
# a) côté Python : lecture de la question, recherche dans les résultats, rédaction
python -m cotraffic llm-status
python -m cotraffic ask "Quel est le meilleur contrôleur à la pointe sur la grille ?" --no-llm
python -m cotraffic ask "Compare COOP et MP sur le quartier à la pointe"          # rédigé par le modèle local
python -m cotraffic demo-plan "montre une ambulance et un accident sur la grille avec des piétons et des bus, MP contre COOP-FULL" --no-llm
python scripts/check_assistant.py --no-write    # précision de lecture : mots-clés, modèle, combinaison

# b) côté tableau de bord : tests du moteur sans backend, puis scénario complet dans le navigateur
cd frontend
npx vitest run src/features/assistant
$env:SLOWMO = "300"
npx playwright test tests/e2e/assistant.spec.ts --headed
Remove-Item Env:SLOWMO

# c) le backend en streaming (deuxième terminal : uvicorn api.main:app --port 8000)
'{"question": "COOP-FULL est-il meilleur que FT sur l attente en pointe sur la grille ?"}' | Out-File -Encoding ascii q.json
curl.exe -N -X POST http://localhost:8000/api/assistant/chat -H "Content-Type: application/json" --data "@q.json"
```

`assistant.spec.ts` pose sept questions dans l'interface et vérifie :
- la comparaison COOP-FULL / FT avec les chiffres exacts, l'IC, le p de Holm et les fichiers sources ;
- qu'il dit « moins bien » quand l'agent est moins bon (ambulances contre EV-RULE-MP) ;
- le meilleur contrôleur, recalculé à partir des résultats ;
- un graphique dans la conversation ;
- l'ouverture d'un carrefour sur la carte, seulement après un clic ;
- qu'aucune simulation ne démarre sans backend ni confirmation ;
- la réponse en anglais quand l'interface est en anglais.

## Démo LLM : le LLM dans la boucle de décision (environ 15 min)

Le déroulé détaillé, les preuves et les questions probables sont dans
[VALIDATION_LLM.md](VALIDATION_LLM.md). La visite du code, fichier par fichier, est dans
[VISITE_DU_CODE.md](VISITE_DU_CODE.md), et les réponses aux questions dans
[FICHE_QUESTIONS_LLM.md](FICHE_QUESTIONS_LLM.md). Convention : gain positif = mieux.
Tous les chiffres viennent de la graine de validation 1000.

### Préparation (10 minutes avant)

```powershell
cd G:\pi5eme\cotraffic
ollama list                                                  # qwen2.5:3b doit être présent
.venv\Scripts\python -m pytest tests\test_llm_settings.py -q    # réglages cohérents (2 s)
.venv\Scripts\python scripts\llm_demo.py --source rules        # préchauffe SUMO (1 min, sans LLM)
```

Ne lancer aucun autre calcul pendant la séance. Brancher le chargeur : en veille, le PC
interrompt les calculs.

### Commandes, dans l'ordre

| Ordre | Durée | Ce qu'on montre | Commande |
|---|---|---|---|
| 1 | 2 min | **Le LLM change les décisions de PPO, et le bouclier garde le dernier mot** | `.venv\Scripts\python scripts\llm_demo.py` |
| 2 | 1 min | Les réglages justifiés et le choix du modèle | `Get-Content configs\llm.yaml` puis `type results\exploration\llm_benchmark\step2_choice.json` |
| 3 | 1 min | La sécurité : 10 tests adverses, dont l'attaque contre le bouclier | `.venv\Scripts\python -m pytest tests\test_llm_security.py -v` |
| 4 | 30 s | 12 réponses invalides refusées | `.venv\Scripts\python -m pytest tests\test_llm.py -k refused -v` |
| 5 | 30 s | Le tool schema | `.venv\Scripts\python -m pytest tests\test_llm_tools.py -v` |
| 6 | 1 min | Le tool schema avec le vrai LLM (facultatif) | `.venv\Scripts\python scripts\llm_tools_demo.py --kind emergency` |
| 7 | 1 min | Le tableau des résultats de validation | `.venv\Scripts\python scripts\llm_results_table.py` |
| 8 | 30 s | Les épisodes complets (période N) | `type results\exploration\llm_period\period_summary.csv` |

Pendant la démo 1, il faut montrer :
- une ligne `PPO seul -> p0 | avec le conseil -> p1 | bouclier -> p1 (accepté)` : le
  conseil a changé la décision ;
- une ligne `..., corrigé : vert minimum pas encore atteint` : le bouclier a refusé ;
- la ligne « Pour comparaison, le conseiller à règles proposerait » : à l'appel n°4, les
  règles donnent la phase dont l'ambulance a besoin, le LLM l'inverse. C'est l'une des
  raisons de l'absence de gain.

### Plan de secours

| Problème | Que faire |
|---|---|
| Ollama lent (premier appel de plus de 30 s) ou absent | Montrer la sortie enregistrée : `type docs\demo\llm_demo_emergency.txt`. Ou lancer la même démo sans LLM : `.venv\Scripts\python scripts\llm_demo.py --source rules` (même mécanisme, conseils des règles) |
| La démo des outils est trop lente (27 à 50 s par conseil) | `type docs\demo\llm_tools_demo.txt` |
| SUMO ne démarre pas | Les tests de sécurité et d'outils ne lancent pas tous SUMO : les montrer d'abord (lignes 3 à 5), puis la sortie enregistrée de la démo |
| Plus de temps | `--compare` ajoute COOP-FULL seul sur le même épisode : `.venv\Scripts\python scripts\llm_demo.py --scenario incident --compare` (environ 3 min) |
