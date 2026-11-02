# Tableau de bord « frontend-pro » : captures d'écran

Branche `feat/frontend-pro`, en français, thèmes sombre et clair, 1440 px de large. Les
chiffres affichés sont ceux des fichiers exportés depuis les résultats
(`scripts/dashboard_combined.py`, `scripts/combined_figures.py`).

Le groupe « Présentation » de la barre latérale suit l'ordre de la soutenance : une page par
question, la réponse en une phrase en haut, le détail replié pour les experts.

| Fichier | Page |
|---|---|
| `01-accueil-*.png` | Accueil : le message, les trois chiffres clés, la rigueur, le parcours |
| `02-comment-ca-marche-*.png` | Les cinq couches d'une décision (le LLM en tête) et le démonstrateur « Qui décide ? » |
| `03-resultats-*.png` | Les résultats : le compromis, les 36 tests en carrés, les ambulances, le détail replié |
| `04-resultats-ablation-*.png` | L'ablation : les couches, les autres variantes, le choix sur la validation |
| `05-llm-dans-la-boucle-*.png` | Le LLM stratège : ses garde-fous, un épisode vu par lui, ses raisons, son effet |
| `06-robustesse-*.png` | Capteurs bruités, pertes de messages, bus, grille 8x8 |
| `07-grandes-villes-*.png` | Paris et Barcelone : plans des réseaux et tous les contrôleurs (exploratoire) |
| `08-simulation-3d-*.png`, `09-simulation-3d-zoom-*.png` | La ville 3D : immeubles, arbres, trottoirs, feux sur poteaux, voitures |
| `10-palette-ctrl-k-*.png` | La palette de commandes (Ctrl+K) |
| `11-resume-technique-*.png` | Le résumé technique : chaque partie, ses calculs et les extraits du vrai code |

Lancer le tableau de bord :

```
cd frontend
npm install
npm run dev          # http://localhost:5173
```

Régénérer les données des pages après une nouvelle analyse :

```
python scripts/dashboard_combined.py
python scripts/export_guide.py      # le résumé technique et ses extraits de code
```
