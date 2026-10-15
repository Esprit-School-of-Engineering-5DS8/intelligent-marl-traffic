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

Chaque passage est contrôlé par son propre agent Q-learning. À chaque décision,
l'agent choisit entre attendre et demander le passage, selon sa file et son
temps d'attente ainsi que les files, le feu actif et la présence d'un véhicule
d'urgence communiqués par le contrôleur véhicule. La politique de chaque
passage est sauvegardée dans `traci6_qtable_v3.json` avec celle du feu véhicule.
Un garde-fou demande automatiquement le passage après 60 secondes d'attente
pour éviter qu'une politique encore en apprentissage ne bloque les piétons.
Un piéton arrive toutes les 30 secondes à chaque approche.
Le scénario génère 25 véhicules par itinéraire (300 au total) sur 10 minutes.
Le contrôleur garde chaque mouvement
au vert au moins 10 secondes. Si la file du
mouvement choisi reste importante, il peut prolonger le vert jusqu'à 10 secondes
supplémentaires, avec une durée totale plafonnée à 20 secondes. Si la file est
résorbée après les 10 premières secondes, il réévalue immédiatement les
mouvements. La récompense pénalise davantage la file véhicule la plus longue
afin que le contrôleur RL traite mieux les voies saturées.
Les demandes piétonnes sont renvoyées au contrôleur véhicule, qui inclut aussi
la pression piétonne dans son état et sa récompense. Lorsqu'une ou plusieurs
demandes sont retenues et qu'aucun véhicule d'urgence n'approche, J6 passe par
le jaune puis par une courte phase tout rouge avant d'ouvrir en même temps les
passages concernés. Les autres passages restent au rouge. Une urgence conserve
la priorité et retarde le service piéton jusqu'à ce que la voie soit libre.
Au début d'une phase piétonne, l'agent mémorise les personnes déjà en attente ;
les arrivées suivantes attendent la prochaine phase afin que le feu ne reste
pas bloqué au vert piéton. Les phases piétonnes sont espacées d'au moins
30 secondes pour laisser le trafic véhicule circuler ; après 60 secondes
d'attente, la politique demande automatiquement le passage.
En mode SUMO statique (`Sample.sumocfg`), une phase protégée met les véhicules
au rouge et les quatre passages au vert.

Les passages font 6 mètres de large. Pour appliquer l'apprentissage et la
coordination multi-agent, lancer `traci6.QL.py`.
