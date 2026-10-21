# 📋 Suivi — Hazem Mrad

> **Projet :** Intelligent Multi-Agent Urban Traffic Management  
> **Cours :** Advanced Data Science Project — Esprit School of Engineering (5DS8)  
> **Superviseur :** Islem Maiti  
> **Date du suivi :** 09 Octobre 2026  
> **Rôle :** Simulation & Environment Lead

---

## 🎯 Responsabilités Assignées

Selon la répartition des rôles dans l'équipe, mes objectifs sont :

| Objectif | Description |
|----------|-------------|
| **F1** | Mise en place des scénarios SUMO (2x2 et 3x3) |
| **F2** | Construction du pipeline de données et des baselines de référence |

---

## ✅ Travail Réalisé

### 1. Environnement Multi-Agent (`environment/multi_agent_env.py`)

- Implémentation complète de `SumoMARLEnv`, un environnement MARL compatible **PettingZoo ParallelEnv** et **Gymnasium**.
- Gestion du cycle complet : reset → step → observation → reward → done.
- Prise en charge **multi-modale** : voitures, bus, véhicules d'urgence (EV) et piétons.
- Collecte automatique des **KPIs** à chaque step :
  - `avg_speed_m_s` — vitesse moyenne réseau
  - `total_waiting_time_s` — délai total des véhicules
  - `arrived_vehicles` — débit (throughput)
  - `co2_mg_s` — émissions CO₂
  - `fuel_ml_s` — consommation de carburant
  - `ev_waiting_time_s` — délai spécifique aux véhicules d'urgence
  - `pedestrian_waiting_time_s` — délai piétons
- Implémentation de `SumoTLSController` : contrôle des feux avec application du **minimum green** et gestion des phases de dégagement jaune.

### 2. Scénarios SUMO

#### Phase 1 — Grid 2x2 (`scenarios/grid_2x2/`)
- Réseau de **4 intersections** pour la validation initiale.
- Fichiers de configuration SUMO (`grid2x2.sumocfg`) opérationnels.
- Runner (`runner.py`) fonctionnel avec support des modes : `sumo_default`, `fixed`, `max_pressure`, `custom`.
- Documentation du scénario rédigée (`README.md`).

#### Phase 2 — Grid 3x3 (`scenarios/grid_3x3/`)
- Réseau de **9 intersections** pour le benchmark principal.
- Runner et génération de routes (`generate_routes.py`) implémentés.
- Documentation du scénario rédigée (`README.md`).

#### Phase 3 — Monaco (`scenarios/monaco/`)
- Intégration du scénario **Monaco SUMO Traffic (MoST)** (réseau réel OSM).
- Réseau comprenant 12 intersections signalisées réelles, +1 700 rues, réseau piéton complet.
- Documentation initiale rédigée, simulation planifiée.

### 3. Baselines de Référence (`baselines/`)

Implémentation des 4 contrôleurs de référence servant de comparaison pour le MARL :

| Contrôleur | Fichier | Description |
|-----------|---------|-------------|
| Fixed-Time | `fixed_time.py` | Cycles pré-programmés fixes (60s) |
| Actuated | `actuated.py` | Gap-out / max-out adaptatif |
| Green Wave | `green_wave.py` | Progression arterielle coordonnée (EW) |
| Max-Pressure | `max_pressure.py` | Heuristique de pression de file d'attente (Varaiya, 2013) |

### 4. Évaluation et Benchmark (`evaluation/benchmark_baselines.py`)

- Script de benchmark automatisé comparant les 4 contrôleurs sur les scénarios 2x2, 3x3 et Monaco.
- Génération d'un **scoreboard comparatif** avec tous les KPIs.
- Export automatique des résultats en CSV dans `results/`.

---

## 🔄 Statut des Phases

| Phase | Scénario | Statut |
|-------|----------|--------|
| Phase 1 | Grid 2x2 — validation jouet | 🟡 En cours |
| Phase 2 | Grid 3x3 — benchmark principal | 🟠 En cours |
| Phase 3 | Monaco — cas réel | 🔴 Planifié |

---

## 🚧 Prochaines Étapes

- [ ] Finaliser et tester le runner Monaco avec le scénario MoST complet
- [ ] Lancer les benchmarks de référence sur 2x2 et 3x3 (validation des KPIs)
- [ ] Brancher l'environnement MARL aux agents RL de Bilel (DQN / PPO)
- [ ] Fournir les données de simulation pour les modules prédictifs de Rami
- [ ] Coordonner avec Amen Allah pour l'intégration du corridor EV dans l'environnement

---

## 🧱 Stack Technique Utilisée

- **Simulateur :** Eclipse SUMO ≥ 1.20 (TraCI, sumolib)
- **Framework MARL :** PettingZoo + Gymnasium
- **Langage :** Python 3.10+
- **Analyse :** pandas, numpy

---

*Document rédigé par Hazem Mrad — Suivi PI du 09/10/2026*

---

## 🗺️ Dashboard KEMATARA — Carte 3D Monaco (22 Octobre 2026)

### Travail réalisé

- **Vue 3D de la ville de Monaco** dans le dashboard frontend (`frontend/`) :
  - Remplacement de Leaflet/OSM par **Mapbox GL JS** (`mapbox-gl`, style dark-v11).
  - Bâtiments 3D extrudés (`fill-extrusion`, source `composite/building`) avec LOD : opacité 0 sous zoom 13.
  - Caméra pitch 62° / bearing -28° centrée sur MoST (43.7384, 7.4246) ; brouillard et lumière personnalisés pour l'ambiance crépusculaire.
  - Toggle 3D/2D dans le HUD de la carte (persistance `localStorage` `kematara.mapMode`).
- **Superposition du trafic SUMO** sur la carte 3D :
  - Extraction du réseau MoST réel (`scenarios/monaco/in/most.net.xml`, UTM 32N → WGS84 via pyproj) :
    `python frontend/scripts/extract_monaco_network.py` → `frontend/public/monaco-network.json` (460 arêtes, 12 TLS).
  - Les véhicules démo s'animent sur les géométries réelles des routes (sélection d'itinéraire par marche aléatoire dans le graphe du réseau, ralentissement selon congestion locale, 140 véhicules max).
  - Densité de congestion par arête (q) colorée en heatmap de lignes (teal → amber → rouge) + glow ; files des intersections colorées (J1–J4 ancrés sur les vrais TLS les plus proches).
  - Synchronisé aux boutons Run / Pause / Step / Stop existants (1 step = 1 s).
- **Jeton Mapbox** : panneau de connexion dans la carte, `localStorage` (`kematara.mapboxToken`), `VITE_MAPBOX_TOKEN` dans `frontend/.env`, ou `window.MAPBOX_TOKEN`.
- **Seam TraCI** : `window.KEMATARA.applySimState({step, junctions, vehicles})` prêt à remplacer l'état démo par un bridge Python/TraCI.

### Dépendances

- `npm install mapbox-gl` (leaflet désinstallé)
- `pip install pyproj` (conversion UTM→WGS84)

### Prochaine étape

- [ ] Brancher `applySimState()` sur un service FastAPI + TraCI pour les véhicules temps réel
