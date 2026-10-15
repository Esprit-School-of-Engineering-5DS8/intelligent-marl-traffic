# Carrefour J6 et passages piétons

Le réseau contient quatre passages piétons aux quatre branches du carrefour
J6. Chacun a son propre flux de personnes dans `Sample.rou.xml` et son propre
agent de demande. Les passages sont générés autour de J6 à partir des trottoirs
définis dans `Sample.edg.xml`.

Pour reconstruire le réseau après modification des sources :

```bash
python SUMOSample/build_network.py
```

Pour lancer le contrôleur Q-learning et les agents piétons :

```bash
python traci6.QL.py
```

Chaque agent piéton attend qu'au moins 2 personnes soient réunies à son
passage, sans délai de secours. Un piéton arrive toutes les 30 secondes à chaque
approche ; le groupe est donc formé après l'arrivée du deuxième piéton.
Le scénario génère maintenant 25 véhicules par itinéraire (300 au total) et le
contrôleur garde chaque mouvement véhicule vert jusqu'à 10 secondes avant de
réévaluer les files, afin de limiter les changements de phase trop fréquents.
Lorsqu'une ou plusieurs files piétonnes sont prêtes dans `traci6.QL.py`, J6
passe par le jaune puis par une courte phase tout rouge avant d'ouvrir en même
temps les passages concernés. Les autres passages restent au rouge. Ce service
groupé évite de répéter plusieurs phases tout rouge à la suite. En mode SUMO statique
(`Sample.sumocfg`), une phase protégée met les véhicules au rouge et les quatre
passages au vert pour éviter que les piétons restent bloqués.

Les passages font 6 mètres de large. Pour appliquer le seuil de groupe et la
coordination à la demande, lancer `traci6.QL.py`.
