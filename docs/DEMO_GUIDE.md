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
  graines de test (5) ; tests de Wilcoxon appariés, correction de Holm par famille.
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
