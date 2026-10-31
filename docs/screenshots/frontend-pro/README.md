# Tableau de bord « frontend-pro » : captures d'écran

Branche `feat/frontend-pro`, en français, thèmes sombre et clair, 1440 px de large, pleine
page. Les chiffres affichés sont ceux des fichiers exportés depuis les résultats
(`scripts/dashboard_combined.py`, `scripts/combined_figures.py`).

| Fichier | Page |
|---|---|
| `01-accueil-*.png` | Accueil : le message, les trois chiffres clés, la rigueur, les quatre couches |
| `02-controleur-final-*.png` | Contrôleur final, onglet Résultats : forest plot, compromis, ambulances, bilan, tableau final, démo |
| `03-controleur-final-ablation-*.png` | Contrôleur final, onglet Ablation : couches, autres variantes, choix sur la validation |
| `04-robustesse-*.png` | Robustesse et généralisation, et la tentative grande ville arrêtée (F-016) |
| `05-palette-ctrl-k-*.png` | La palette de commandes (Ctrl+K) |

Lancer le tableau de bord :

```
cd frontend
npm install
npm run dev          # http://localhost:5173
```

Régénérer les données des pages après une nouvelle analyse :

```
python scripts/dashboard_combined.py
```
