# Fiche : 15 questions probables sur le LLM dans la boucle

Réponses courtes, pour la validation. Chiffres de la graine de validation 1000 ;
convention : gain positif = mieux (moins d'attente que COOP-FULL seul). Les preuves et les
fichiers sont dans [VALIDATION_LLM.md](VALIDATION_LLM.md).

**1. Pourquoi le LLM n'est-il pas appelé toutes les 5 secondes ?**
- Il met 8 s à répondre en médiane (11,7 s au 95e centile) : il ne peut pas suivre un
  rythme de 5 s.
- Il est donc appelé à chaque nouvel événement, et toutes les 10 minutes, au plus une fois
  par 30 s.
- C'est aussi ce que la mesure conseille : appelé toutes les 3 minutes, il dégrade
  l'attente des piétons de 24,8 %.

**2. Pourquoi ne commande-t-il pas directement le feu ?**
- Un modèle de langage peut se tromper, être lent ou être manipulé.
- Il donne donc un conseil borné, qui modifie le score des phases de PPO. PPO décide, et le
  bouclier de sécurité a le dernier mot.
- Une erreur du LLM ne peut au pire que dégrader un peu le trafic ; elle ne peut jamais
  produire un feu dangereux.

**3. Pourquoi qwen2.5:3b ?**
- Une règle fixée avant les résultats : au moins 95 % de JSON valide, une latence p95 d'au
  plus 20 s, puis le meilleur gain, parmi 8 modèles de 0,5B à 3,8B.
- Son gain (+0,29 %) est dans le bruit ; qwen2.5:0.5b (+0,22 %, deux fois plus rapide)
  serait presque équivalent.
- Le modèle est local : aucune donnée ne sort de la machine.

**4. Pourquoi le gain est-il si faible, et que montre l'oracle ?**
- COOP-FULL gère déjà bien ces situations.
- L'oracle choisit après coup le meilleur conseil de chaque situation parmi tous les
  candidats : il ne gagne que **+1,09 %**.
- Une bonne part de ce gain vient même de la chance : le meilleur candidat est un conseil
  au hasard dans 21 situations sur 63.
- La marge de progrès pour un conseiller, quel qu'il soit, est donc d'environ 1 % ici. Le
  LLM obtient +0,16 %, le placebo +0,09 %, les règles −0,17 %.

**5. Pourquoi LoRA s'abstenait-il au premier essai ?**
- 55 des 63 situations de validation ont pour étiquette l'abstention : répondre « rien »
  partout donne 87 % d'accord.
- Avec des abstentions majoritaires dans l'entraînement et seulement 15 pas
  d'optimisation, LoRA a appris exactement cela.
- **La correction** : rééquilibrer l'entraînement, faire plus de pas, et mesurer le rappel
  des conseils et les faux conseils.
- **Le résultat sur le lot final** (169 exemples) : LoRA retrouve 17 % des conseils
  attendus, avec 12 % de faux conseils. Il conseille surtout pendant les urgences, mais
  son gain dans SUMO reste de +0,05 %.
- **La leçon** : l'accord avec l'étiquette ne prouve rien, seul l'effet dans SUMO compte.

**6. Quelle différence entre LoRA, prompt tuning et prompt engineering ?**
- **Prompt engineering** : on écrit la consigne à la main ; aucun paramètre n'est appris.
- **Prompt tuning** : on apprend 20 vecteurs placés devant la consigne, environ 20 000
  paramètres.
- **LoRA** : on apprend de petites matrices de rang 16 dans chaque couche, environ 8,8
  millions de paramètres pour le 0,5B.
- Dans les trois cas, le modèle de base reste figé.

**7. Comment empêche-t-on un conseil dangereux ?**
- **Ce qui sort du LLM est contrôlé** : sortie contrainte par un schéma JSON, puis lecture
  stricte (clés, types, bornes), puis contrôle contre le réseau (carrefour et phase qui
  existent).
- **Le conseil a un poids limité** : c'est un biais borné, qui expire après 10 à 120 s.
- **Le bouclier passe en dernier** : vert minimum, vert maximum, anti-famine, jaune.
- **Le test d'attaque** : un conseil malveillant avec un biais de 1000 change les demandes,
  mais le vert le plus court reste de 13 s, pour un minimum de 10 s.

**8. À quoi servent le placebo et le conseiller à règles ?**
- **Le placebo** donne des conseils au hasard, de même fréquence et de même force que le
  LLM. Il sépare l'effet du « bon conseil » de l'effet d'une simple perturbation.
- **Le conseiller à règles** applique les mêmes principes que le prompt, mais écrits à la
  main. Il dit si le LLM apporte plus qu'une heuristique.
- Sur la validation : LLM +0,16 %, placebo +0,09 %, règles −0,17 %. Aucune différence nette.

**9. Comment la latence est-elle prise en compte ?**
- Le conseil n'agit qu'à t + la latence réelle mesurée de son appel, comme si la
  simulation tournait en temps réel.
- Le placebo et les règles, qui répondent instantanément, sont retardés de la latence
  médiane du LLM (8,2 s) pour une comparaison juste.
- Une analyse avec un délai nul, mesuré et doublé est pré-enregistrée.

**10. Pourquoi beta = 4 ?**
- La marge médiane de PPO entre ses deux phases vaut 3,3.
- Avec beta 2, un conseil fort ne renverse que 27 % des décisions ; avec beta 4, 63 %.
- Avec beta 8, il en renverse 92 % et dégrade l'attente de 1,2 %. beta 4 est le plus fort
  biais qui ne dégrade pas en moyenne.

**11. Comment évitez-vous de régler sur les données de test ?**
- Tous les choix sont faits sur la seule graine de validation 1000, et les exemples sur les
  graines d'entraînement 100001 à 100003.
- Les scripts refusent les graines de test 0 à 4.
- Les règles de choix ont été écrites avant les résultats, et l'évaluation sur les graines
  de test est pré-enregistrée (`docs/LLM_PREREGISTRATION.md`).

**12. Pourquoi le few-shot et le vote n'aident-ils pas ?**
- **Le few-shot** : les exemples apprennent surtout au modèle à s'abstenir (40 %
  d'abstentions). Comme COOP-FULL est déjà bon, se taire ne gagne rien (+0,08 %).
- **Le vote** sur 3 réponses : il ne change presque rien (+0,02 %) et triple la latence
  (24,6 s au 95e centile).

**13. À quoi sert le tool schema, et pourquoi n'est-il pas retenu ?**
- Le modèle peut lire la situation avec 5 outils en lecture seule (état d'un carrefour,
  voisins, événements, route d'une ambulance, véhicules qui arrivent), puis appeler
  `submit_advice`, le seul outil qui agit.
- Tout est validé : schémas stricts et Pydantic.
- Il fonctionne, mais le modèle lit les carrefours dans l'ordre au lieu de suivre
  l'ambulance, et un conseil prend 27 à 50 s. Il n'est donc pas retenu.

**14. Pourquoi un modèle local plutôt qu'un grand modèle en ligne ?**
- C'est une contrainte du projet : aucune donnée ne sort, et il n'y a pas de clé d'API.
- C'est aussi réaliste pour un contrôleur de carrefour : le service ne doit pas dépendre
  d'une connexion.
- Le prix est la latence (8 s sur la puce graphique intégrée) et la qualité limitée des
  petits modèles. Un modèle plus grand est l'une des pistes.

**15. Vos résultats sont-ils significatifs, et que reste-t-il à faire ?**
- Non, pas encore. Les écarts de validation (±0,3 % sur les situations, ±3 % sur un
  épisode) sont du même ordre que le bruit : une même configuration varie déjà de 0,15
  point entre deux réglages de contexte.
- LoRA et prompt tuning sont préliminaires (+0,05 % et −0,09 % dans SUMO) : la validation
  ne compte que 15 situations étiquetées « conseil » dans le lot final, et 8 dans le lot
  préliminaire.
- La suite est l'évaluation pré-enregistrée sur les graines de test 0 à 4 : 15 runs par
  scénario, avec placebo, règles et oracle, et des tests de Mann-Whitney corrigés par Holm.
  Elle demande environ 24 à 28 h de calcul.
