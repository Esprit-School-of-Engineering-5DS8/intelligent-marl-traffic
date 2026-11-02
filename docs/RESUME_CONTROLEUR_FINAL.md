# Le contrôleur final de CoTraffic : résumé complet, partie par partie

Pour chaque partie : **ce qu'elle fait**, **le calcul exact**, **comment on est arrivé au
résultat**, et **où se trouve le code**. Les liens pointent vers les fichiers du dépôt (les
numéros de ligne sont ceux de la branche `feat/frontend-pro`). Les chiffres viennent de
`results/combined/` (évaluation finale) et `results/exploration/combined/` (validation).

---

## 0. La vue d'ensemble en un schéma

```
            toutes les 5 s, à chaque feu
 capteurs ──► [1] COOP-FULL (PPO) note chaque phase ──► logits
                                                          │
 compteurs ─► [2] Max-Pressure choisit sa phase ──► +4 sur le logit de cette phase (β = 4)
                                                          │  phase = la plus haute note
 ambulance ─► [3] EV-RULE : ambulance à < 200 m ? ──► oui : sa phase remplace tout
                                                          │
              [4] Bouclier : vert min 10 s, rouge max 90 s, vert max 60 s ──► feu SUMO
```

Depuis le 2 novembre, une cinquième couche, le **LLM stratège**, choisit au-dessus de cette chaîne le mode du réseau toutes les 5 minutes (partie 13 bis, exploratoire). Le chemin pour arriver là :

```
15 variantes ──► classement sur graines de validation 1000, 1001, 1002 ──► H2 β = 4 retenue
      ──► oracle de stratégie (phase B) : pas de place pour un LLM stratège ──► arrêt
      ──► pré-enregistrement figé (commit 2c0dd1d) ──► évaluation unique : 1 265 épisodes,
          graines de test 0 à 4 ──► analyse figée : 36 tests, Holm ──► figures et tableau de bord
```

---

## 1. Le terrain : la simulation et le protocole

**Ce que c'est.** Le trafic est simulé avec SUMO. Chaque feu est un agent qui décide toutes
les 5 s. Trois réseaux :

- `grid4x4` : grille de 16 carrefours (entraînement et évaluation) ;
- `real_district` : quartier réel de Tunis importé d'OpenStreetMap, 7 feux ;
- `grid8x8` : grille de 64 carrefours, **jamais vue à l'entraînement** (généralisation).

**Un épisode d'évaluation** dure 90 min simulées : 15 min de mise en route (non comptées),
60 min mesurées, 15 min pour laisser finir les véhicules partis pendant l'heure mesurée.

**Les temps des feux** (identiques pour tous les contrôleurs) : décision toutes les 5 s,
jaune 3 s, vert minimal 10 s, vert maximal 60 s, rouge maximal 90 s pour une file qui attend.

**Code.**
- Tous ces nombres : [configs/protocol.yaml](../configs/protocol.yaml) (lignes 5-10 pour les
  temps des feux, 23-27 pour l'épisode).
- L'environnement (un agent par feu, une décision toutes les 5 s) :
  [src/cotraffic/envs/traffic_env.py](../src/cotraffic/envs/traffic_env.py), méthode `step`
  ligne 180.
- Les graines : [src/cotraffic/seeds.py](../src/cotraffic/seeds.py) : test = 0 à 999,
  validation = 1000 à 1999. **Rien n'a jamais été réglé sur une graine de test.**

---

## 2. Couche 1 : COOP-FULL, l'agent appris

### Ce qu'il fait
Un réseau de neurones regarde la situation d'un carrefour et donne une **note (logit) à
chaque phase** : 2 phases sur la grille (nord-sud, est-ouest), jusqu'à 3 dans le quartier
réel. Seul, il choisirait la phase de plus haute note.

### Ce qu'il voit (l'observation)
Un vecteur de nombres entre 0 et 1, fait de blocs :

| Bloc | Contenu | Taille sur la grille |
|---|---|---|
| voies | par voie d'arrivée : file, densité, vitesse | 4 côtés × 2 voies × 3 = 24 |
| phase | phase actuelle, file et pression servies par chaque phase, temps écoulé, vert minimal atteint | 3 × 2 + 2 = 8 |
| voisins | message de chaque voisin amont : sa file vers nous, s'il nous envoie du trafic, sa plus forte pression | 4 × 3 = 12 |
| urgences | ambulance qui arrive et sa proximité, par côté et par phase | 4 × 2 + 2 = 10 |
| piétons | piétons qui attendent, par passage | 4 |
| bus | bus pondérés par leur occupation, par côté | 4 |

Total : **62 valeurs** sur la grille (78 dans le quartier réel, qui a 3 voies par côté et 3
phases). Les cases manquantes sont remplies de zéros, pour qu'un même réseau serve à tous
les carrefours.

### Ce qu'il apprend à faire (la récompense)
À chaque décision, pour chaque feu :

```
r = − ΔAttente / n_attente  − 0,5 × CO2 / n_CO2  − 2,0 × AttenteAmbulances / n_amb
    − 0,5 × AttentePiétons / n_piétons            (puis bornée entre −5 et +5)
```

- **ΔAttente** : augmentation de l'attente des véhicules sur les voies d'arrivée **depuis
  leur entrée sur ces voies** (on ne punit pas l'agent pour un bouchon causé ailleurs),
  pondérée par le nombre de personnes (un bus compte plus qu'une voiture).
- Les constantes `n_*` mettent chaque terme à l'échelle 1, à partir de simulations de
  référence.
- Le poids 2,0 sur les ambulances explique pourquoi COOP-FULL les sert bien.

### Comment il a été entraîné
- **PPO** avec **partage des paramètres** : un seul réseau pour tous les carrefours.
- Deux couches cachées de 64 neurones ; 500 000 décisions d'agent par entraînement.
- Demandes variées (faible, moyenne, pointe, profil d'heure de pointe), avec ambulances,
  piétons et bus dans chaque épisode.
- **3 entraînements indépendants** (modèles t1, t2, t3) par réseau ; pour chacun, le
  meilleur des 4 derniers points de sauvegarde, choisi sur la graine de validation 1000.

### Code
- Observation : [src/cotraffic/envs/observations.py](../src/cotraffic/envs/observations.py),
  `block_sizes` lignes 75-90.
- Récompense : [src/cotraffic/envs/rewards.py](../src/cotraffic/envs/rewards.py), formule
  lignes 1-17, calcul `raw_terms` lignes 92-135, combinaison `combine` lignes 137-147.
- Configuration de COOP-FULL : [configs/agents/coop_full.yaml](../configs/agents/coop_full.yaml)
  (poids 0,5 / 2,0 / 0,5), héritée de [coop.yaml](../configs/agents/coop.yaml) (voisins)
  et de [base.yaml](../configs/agents/base.yaml) (PPO, 500 000 pas).
- Entraînement : [src/cotraffic/training/train.py](../src/cotraffic/training/train.py),
  `train` ligne 121 ; sélection : [src/cotraffic/training/select.py](../src/cotraffic/training/select.py).

---

## 3. Couche 2 : Max-Pressure et le biais β = 4

### Max-Pressure seul
Pour chaque phase, on calcule sa **pression** :

```
pression(phase) = somme, sur ses mouvements au vert, de
                  (véhicules sur la voie d'arrivée − véhicules sur la voie de sortie)
```

Max-Pressure choisit la phase de plus forte pression (en cas d'égalité, il garde la phase
actuelle). L'idée : vider en priorité là où ça s'accumule, sans envoyer de voitures dans une
rue déjà pleine.

> **Exemple inventé pour expliquer.** Phase nord-sud : N→S (8 en arrivée, 2 en sortie) et
> S→N (6, 1) : pression = (8 − 2) + (6 − 1) = **11**. Phase est-ouest : E→O (3, 0) et
> O→E (4, 3) : pression = 3 + 1 = **4**. Max-Pressure choisit nord-sud.

### Le biais : comment COOP-FULL et Max-Pressure sont combinés
Les notes de COOP-FULL sont des **logits normalisés**, c'est-à-dire le logarithme de la
probabilité qu'il donne à chaque phase. On **ajoute 4 à la note de la phase de
Max-Pressure**, puis on prend la plus haute note.

Ajouter 4 à un logarithme revient à **multiplier la probabilité par e⁴ ≈ 54,6**. Donc :

> COOP-FULL ne garde sa phase contre celle de Max-Pressure que s'il la juge **plus de
> 54,6 fois plus probable**. Avec 2 phases, cela veut dire qu'il en est sûr à **plus de
> 98,2 %** (car p > 54,6 × (1 − p) ⇔ p > 54,6 / 55,6).

> **Exemple chiffré.** COOP-FULL : nord-sud 70 %, est-ouest 30 % ; Max-Pressure préfère
> est-ouest. Notes : ln 0,70 = −0,36 et ln 0,30 = −1,20 + 4 = **2,80** → **est-ouest gagne**.
> Si COOP-FULL donnait 99 % à nord-sud : ln 0,99 = −0,01 contre ln 0,01 + 4 = −0,61 →
> **nord-sud reste**.

**En une phrase pour le jury :** Max-Pressure décide par défaut ; l'agent appris ne le
contredit que quand il est presque certain d'avoir raison.

### Pourquoi β = 4 et pas un autre
β = 1, 2, 4 et 8 ont été essayés sur les graines de validation (partie 7). β = 4 est premier
ou à égalité avec le premier sur les trois graines ; β = 8 (pousser encore plus vers
Max-Pressure) est 5ᵉ, 5ᵉ et 6ᵉ.

### Code
- Pression et Max-Pressure : [src/cotraffic/controllers/classical.py](../src/cotraffic/controllers/classical.py),
  `phase_pressure` lignes 37-50, `MaxPressure.act` lignes 62-68.
- Le biais : [src/cotraffic/controllers/hybrid.py](../src/cotraffic/controllers/hybrid.py),
  lignes 262-264 (les logits de COOP-FULL) et **lignes 274-277** :
  `row[int(mp[a])] += self.mp_beta` puis `phase = row.argmax()`.

---

## 4. Couche 3 : la priorité aux ambulances (EV-RULE)

### Ce qu'elle fait
À chaque décision, pour chaque feu, on regarde les ambulances dont **ce feu est le prochain**
sur leur route. Si l'une est à **moins de 200 m**, on demande la phase qui lui donne le vert
(un vert protégé si possible). Cette demande **remplace** la phase choisie par les couches 1
et 2. Si plusieurs ambulances approchent du même feu, la plus proche compte.

### Code
- Le guide utilisé par la candidate : [src/cotraffic/controllers/combined.py](../src/cotraffic/controllers/combined.py),
  `EvRuleGuide` lignes 69-88.
- Les ambulances proches et la bonne phase :
  [src/cotraffic/controllers/ev_preemption.py](../src/cotraffic/controllers/ev_preemption.py),
  `approaching` lignes 33-43 (via `getNextTLS` de SUMO), `phase_for` lignes 46-50.
- Le remplacement dans la candidate : [hybrid.py](../src/cotraffic/controllers/hybrid.py),
  lignes 255-257 (les demandes) et 279-280 (elles passent en dernier, donc l'emportent).
- La distance de 200 m : [configs/protocol.yaml](../configs/protocol.yaml), ligne 20.

---

## 5. Couche 4 : le bouclier de sécurité

### Ce qu'il fait
Il reçoit la phase demandée et renvoie celle qui sera vraiment appliquée. Ses règles, dans
cet ordre :

1. **action invalide** (phase qui n'existe pas à ce carrefour) : on garde la phase actuelle ;
2. **vert minimal** : une phase ne peut pas être coupée avant 10 s ;
3. **anti-famine** : un mouvement qui a de la demande et attend au rouge depuis plus de 90 s
   est servi en priorité ;
4. **vert maximal** : une phase n'est pas prolongée au-delà de 60 s si une autre phase a de
   la demande.

Le jaune (3 s) est toujours inséré par le modèle du carrefour, jamais par la politique :
**aucune suite de décisions ne peut produire un feu dangereux**. Le bouclier s'applique à
tous les contrôleurs de la même façon (Max-Pressure aussi), ce qui rend la comparaison juste.

### Code
- [src/cotraffic/envs/shield.py](../src/cotraffic/envs/shield.py), `apply_shield`
  lignes 84-138 (logique pure, testée exhaustivement).
- Appliqué à chaque décision : [traffic_env.py](../src/cotraffic/envs/traffic_env.py), ligne 190.

---

## 6. Une décision complète, ligne par ligne

`HybridPolicy.act` dans [hybrid.py](../src/cotraffic/controllers/hybrid.py#L248-L284) :

| Étape | Lignes | Ce qui se passe |
|---|---|---|
| 1 | 251-253 | Max-Pressure calcule sa phase pour chaque feu (car β > 0) |
| 2 | 254-257 | les demandes des ambulances sont relevées |
| 3 | 259-264 | COOP-FULL calcule ses logits pour tous les feux d'un coup |
| 4 | 265 | on retient ce que COOP-FULL aurait choisi seul (pour les statistiques) |
| 5 | 274-277 | +4 sur la phase de Max-Pressure, puis la plus haute note |
| 6 | 279-280 | une demande d'ambulance remplace le résultat |
| 7 | 281-283 | on compte qui a décidé (coop, mix, ev) et la phase est envoyée |
| 8 | traffic_env.py 190 | le bouclier a le dernier mot |

La candidate est construite ainsi dans [src/cotraffic/controllers/registry.py](../src/cotraffic/controllers/registry.py),
lignes 69-77 : `HybridPolicy(base COOP-FULL, mp_beta=4, ev_guide=EvRuleGuide())`. C'est la
méthode `hybrid_h2` (constante `CANDIDATE`, ligne 17).

---

## 7. Comment la candidate a été choisie (validation)

### Les variantes essayées (15)
- **COOP-FULL seul**, et **V1** = COOP-FULL + EV-RULE ;
- V1 + notre règle piétons (PED-RULE), et V1 + les règles piétons de notre coéquipier ;
- **H1** : chaque feu passe en Max-Pressure quand son voisinage est congestionné, sinon
  COOP-FULL (seuils : quantiles 50, 75, 90 et 95 % de la congestion) ;
- **H2** : le biais de la partie 3, avec β = 1, 2, 4 et 8 ;
- **H3** : H2 β = 4, et Max-Pressure **partout** quand la file d'attente à l'entrée du réseau
  dépasse un seuil (quantiles 75, 90 et 95 %).

Les seuils de H1 et H3 viennent eux aussi de la graine de validation.

### La règle de classement, fixée avant les résultats
Dans chaque case (réseau × scénario × demande, 14 cases) et pour le temps de trajet et
l'attente, on compare la variante à la **meilleure référence** de la case (MP, EV-RULE-MP,
COOP-FULL, TEAM-RULES, et PED-RULE-MP avec piétons) :

```
écart = (variante − meilleure référence) / meilleure référence      (positif = pire)
  ≥ « meilleure ou égale » : écart moyen des 3 modèles ≤ 1 %
  ✗ « pire »               : écart moyen > 3 %, ou les 3 modèles pires de plus de 1 %
  ? « incertaine »         : sinon
```

Une case est « ≥ » si les deux mesures le sont, « ✗ » si l'une l'est. Classement : le plus
de cases « ≥ », puis le moins de « ✗ », puis le retard des ambulances, puis l'attente des
piétons.

### Le résultat

| Variante | Graine 1000 | Graine 1001 | Graine 1002 |
|---|---|---|---|
| **H2 β = 4** | 3ᵉ (≥ 7, ? 2, ✗ 5), à égalité de cases avec les deux premières | **1ʳᵉ** (≥ 7, ? 3, ✗ 4) | **1ʳᵉ** (≥ 10, ? 1, ✗ 3) |
| H3 (q90) | 1ʳᵉ (mêmes cases, départagée par les ambulances) | 3ᵉ | 2ᵉ |
| H2 β = 8 | 5ᵉ | 5ᵉ | 6ᵉ |
| COOP-FULL seul | 12ᵉ | 8ᵉ | 9ᵉ |

H3 a presque partout **les mêmes épisodes** que H2 (sa bascule se déclenche rarement) et fait
moins bien là où elle s'en écarte. La règle de choix retient donc la plus simple : **H2 β = 4**.

### Code
- [scripts/hybrid_rank.py](../scripts/hybrid_rank.py) : règles lignes 1-20,
  `best_reference` lignes 91-98, `classify` lignes 101-107 (les seuils 1 % et 3 %).
- Résultats : [results/exploration/combined/rank_s1000.md](../results/exploration/combined/rank_s1000.md),
  `rank_s1001.md`, `rank_s1002.md`.
- Les variantes sont construites dans [scripts/combined_eval.py](../scripts/combined_eval.py),
  lignes 181-197.

---

## 8. Phase B : l'oracle de stratégie (faut-il un LLM stratège ?)

### L'idée
Avant de construire un LLM qui choisirait la stratégie du réseau toutes les 5 minutes, on a
mesuré **ce que rapporterait un choix parfait** : un « oracle » qui connaît le futur.

### Le calcul
- Toutes les 5 min, on essaie chacun des trois modes (COOP-FULL, Max-Pressure partout,
  la meilleure hybride), en rejouant l'épisode **depuis le début** avec le plan déjà choisi,
  puis le mode sur la fenêtre, puis 5 min de COOP-FULL pour tous.
- On garde le mode de **coût** le plus bas :

```
coût = véhicules-secondes d'attente + 10 × secondes d'arrêt des ambulances
       + personnes-secondes d'attente des piétons
```

- Un **placebo** joue des plans tirés au hasard : la part du gain que le hasard seul donne.

### La règle de décision, fixée à l'avance
Une case « passe » si l'oracle bat **à la fois** la meilleure hybride fixe **et** le meilleur
placebo de **plus de 3 %** (sur le trajet ou l'attente). Il fallait au moins **4 cases sur 14**
pour continuer.

**Résultat : 3 sur 14 → arrêt.** Il n'y avait pas assez de place pour un LLM stratège ; on
ne l'a pas construit.

**Limite connue, dite dans le rapport :** le coût ne comptait pas les voitures bloquées à
l'entrée du réseau. Dans les cas saturés, l'oracle sous-estime ce qu'une stratégie pourrait
gagner.

### Code
- [scripts/strategy_oracle.py](../scripts/strategy_oracle.py) : principe lignes 1-24, poids
  10 des ambulances ligne 50, coût ligne 81.
- [scripts/oracle_report.py](../scripts/oracle_report.py) : marge de 3 % ligne 35, critère
  ligne 81, seuil de 4 cases ligne 103.
- Résultat : [results/exploration/combined/oracle_s1000.md](../results/exploration/combined/oracle_s1000.md).

---

## 9. Le pré-enregistrement et l'évaluation unique

### Ce qui a été figé avant toute graine de test
Contrôleurs, situations, graines, mesures, tests et règles de décision, dans
[docs/COMBINED_PREREGISTRATION.md](COMBINED_PREREGISTRATION.md), figé au commit **2c0dd1d**.

**Le script refuse de démarrer** si un seul fichier figé (le code `src/cotraffic`, les
`configs`, les scripts d'évaluation et d'analyse, les seuils de H1 et H3) a changé depuis ce
commit.

### Le plan de l'évaluation
- **18 situations** : 14 principales (grille : normal, urgences, incident, piétons ; quartier
  réel : normal, urgences, incident ; chaque fois en demande moyenne et en pointe), 3 de robustesse (capteurs bruités, pertes de messages
  30 %, bus), 1 de généralisation (grid8x8 sans réentraînement).
- **Graines de test 0 à 4** ; les contrôleurs appris avec leurs **3 modèles**.
- **1 265 épisodes** au total (dont 5 pour la variante LLM, jouée en dernier, seule). Chaque
  épisode enregistre le commit du code (2c0dd1d pour les 1 265).

### Code
- [scripts/combined_final.py](../scripts/combined_final.py) : graines ligne 36, modèles
  ligne 37, fichiers figés lignes 38-47, plan lignes 48-62, vérification `frozen_since`
  lignes 103-112.

---

## 10. Les mesures

Calculées à partir des sorties de SUMO, sur les véhicules **partis pendant l'heure mesurée** :

- **Temps de trajet** = arrivée − départ **prévu** (l'attente pour entrer dans le réseau
  compte). Un véhicule téléporté par SUMO (bouchon) reçoit **+300 s** : un bouchon caché ne
  doit jamais avantager une méthode. Un véhicule pas arrivé compte jusqu'à la fin.
- **Attente** = temps à moins de 0,1 m/s + retard d'insertion.
- **Retard des ambulances** = temps perdu par rapport à la vitesse libre, moyenne des
  ambulances de l'épisode (3 à 5 par épisode).

### Code
- [src/cotraffic/evaluation/metrics.py](../src/cotraffic/evaluation/metrics.py) :
  définitions lignes 1-30, trajet lignes 241-244, attente lignes 246-248, retard des
  ambulances ligne 306. Pénalité de 300 s : [protocol.yaml](../configs/protocol.yaml), ligne 27.

---

## 11. Les statistiques : du résultat brut au verdict

### a. La référence de chaque comparaison
Dans chaque situation et pour chaque mesure, on prend **la meilleure** des références
(MP, EV-RULE-MP, COOP-FULL, TEAM-RULES, et PED-RULE-MP avec piétons). C'est la comparaison
la plus exigeante possible.

### b. Le gain
```
gain (%) = 100 × (moyenne référence − moyenne candidate) / moyenne référence
           positif = la candidate fait mieux
```

### c. L'intervalle de confiance (bootstrap croisé)
On a un tableau de 3 modèles × 5 graines. On le **rééchantillonne 10 000 fois** : à chaque
tirage, on tire au hasard (avec remise) les modèles **et** les graines, et on recalcule le
gain. L'intervalle à 95 % va du 2,5ᵉ au 97,5ᵉ pourcentile des 10 000 gains. Quand la
référence est COOP-FULL, les tirages sont **appariés par modèle** (la candidate est construite
sur les mêmes modèles).

### d. Les p-valeurs
```
p (non-infériorité) = (1 + nombre de tirages où le gain ≤ −2 %) / (1 + 10 000)
p (supériorité)     = (1 + nombre de tirages où le gain ≤ 0)    / (1 + 10 000)
```

### e. La correction de Holm (36 tests à la fois)
Faire 36 tests augmente le risque d'une « victoire » due au hasard. Holm trie les p du plus
petit au plus grand et multiplie le k-ième par (36 − k + 1), en gardant l'ordre croissant.
Un test passe si sa p corrigée est **< 0,025**.

### f. Le verdict
- **Prouvée meilleure** : passe le test de supériorité (famille « hybrid-sup ») ;
- **Prouvée non inférieure** : passe le test de non-infériorité à −2 % (famille « hybrid ») ;
- sinon : **vraie perte** si **tout** l'intervalle est sous 0 (« au-delà de −2 % » s'il est
  aussi sous −2 %) ; **trop large pour conclure** dans les autres cas.

### Trois exemples réels

| Situation | Référence | Moyennes (réf. / cand.) | Gain | IC à 95 % | p Holm | Verdict |
|---|---|---|---|---|---|---|
| grille, capteurs bruités, pointe, attente | COOP-FULL | 68,23 s / 58,60 s | 100 × (68,23 − 58,60) / 68,23 = **+14,1 %** | [+3,3 ; +34,0] | 0,0036 (sup. : 0,019) | **prouvée meilleure** |
| grille, normal, pointe, trajet | MP | 210,18 s / 213,59 s | **−1,6 %** | [−3,4 ; −0,2] | 1 | **vraie perte** (tout l'IC < 0) |
| quartier réel, normal, pointe, attente | MP | 36,20 s / 40,22 s | **−11,1 %** | [−32,1 ; +7,9] | 1 | **trop large pour conclure** |

Dans le premier exemple, aucun des 10 000 tirages n'est sous −2 % : p = 1 / 10 001 ≈ 0,0001,
et la p corrigée vaut 36 × 0,0001 = 0,0036 < 0,025.

### Code
- [scripts/combined_analysis.py](../scripts/combined_analysis.py) : marge, α et nombre de
  tirages ligne 47 ; tableau modèles × graines `table` lignes 86-97 ; gain et bootstrap
  `gain_draws` lignes 100-121 ; meilleure référence et p `compare` lignes 124-165 (p ligne
  158) ; Holm et verdicts `with_holm` lignes 168-187.
- Holm : [src/cotraffic/analysis/stats.py](../src/cotraffic/analysis/stats.py), lignes 120-133.
- Sortie complète : [results/combined/analysis.md](../results/combined/analysis.md).

---

## 12. Les résultats et leur calcul

### a. Les 36 tests
**15 prouvées non inférieures, dont 6 meilleures ; 5 vraies pertes ; 16 trop larges.**

- Meilleure : l'attente en demande moyenne sur la grille (normal, incident, piétons, bus :
  +2 à +3 %) et, sous capteurs bruités, le trajet (+6,1 %) et l'attente (+14,1 %).
- Vraies pertes, toutes contre MP : le trajet en pointe sur la grille (normal −1,6 %,
  urgences −1,2 %, pertes de messages −1,7 %) et grid8x8 (trajet −2,1 %, attente −1,5 %).
- Trop larges : surtout le quartier réel en pointe ; deux cas ont une estimation nettement
  défavorable (quartier réel en pointe, grille avec piétons en pointe).

### b. Le compromis : « 12,2 % contre 35 à 99 % »
Pour chacun des 5 critères et chacune de ses cases :

```
écart(contrôleur) = 100 × (sa moyenne − meilleure des 5) / meilleure des 5
écart du critère   = moyenne de ces écarts sur les cases du critère
pire écart         = le plus grand de ses 5 écarts
```

| Contrôleur | Trajet | Attente | Ambulances | Piétons | Capteurs bruités | **Pire écart** |
|---|---|---|---|---|---|---|
| **Candidate** | +1,4 % | **+2,7 %** (meilleure) | +12,2 % | +9,4 % | **0 %** (meilleure) | **12,2 %** |
| EV-RULE-MP | +0,6 % | +4,9 % | **+8,4 %** (meilleure) | +26,8 % | +34,8 % | 34,8 % |
| TEAM-RULES | +2,6 % | +9,8 % | +19,8 % | +26,4 % | +34,8 % | 34,8 % |
| COOP-FULL | +3,9 % | +8,0 % | +51,5 % | **0 %** (meilleure) | +11,5 % | 51,5 % |
| MP | **+0,4 %** (meilleure) | +4,5 % | +99,1 % | +26,8 % | +34,8 % | 99,1 % |

Lecture : chacun des autres a un critère où il décroche (MP sur les ambulances, EV-RULE-MP et
TEAM-RULES sous capteurs bruités, COOP-FULL sur les ambulances) ; **la candidate n'en a pas**.

Code : [scripts/combined_figures.py](../scripts/combined_figures.py), `criteria`
lignes 217-240, `compromis` lignes 242-295.

### c. Les ambulances : « 71 trajets sur 72 »
Pour chaque ambulance (même identifiant, même graine, donc même trafic des deux côtés) :
`gain = retard avec MP − retard avec la candidate`, pour les 3 modèles. On compte les gains
positifs : **71 sur 72** à l'heure de pointe (24 ambulances × 3 modèles), 53 s gagnées en
médiane ; 68 sur 72 en demande moyenne.

Retard moyen : **44 s** contre **106 s** avec MP en pointe (23 s contre 52 s en demande
moyenne) ; la meilleure règle dédiée, EV-RULE-MP, fait 38 s et 21 s. C'est une mesure
**secondaire** (pas de test de Holm).

Code : [combined_figures.py](../scripts/combined_figures.py), `ambulance_counts`
lignes 426-446, `ambulances` lignes 297-334.

### d. L'ablation : ce que chaque couche apporte
On compare chaque couche à COOP-FULL seul, sur les mêmes graines (sans test) :

- **+ préemption (V1)** : presque rien sur le trafic (entre −0,9 et +0,7 % selon la case) ;
  elle sert les ambulances ;
- **+ biais Max-Pressure (la candidate)** : c'est **lui qui apporte le gain**, surtout là où
  COOP-FULL s'engorge : grille avec piétons en pointe, **+17,8 %** de trajet et **+35,4 %**
  d'attente ; capteurs bruités +6,1 % et +14,1 % ;
- **+ bascule sur saturation (H3)** : quasi identique à la candidate.

Code : [combined_analysis.py](../scripts/combined_analysis.py), `ablation` lignes 213-234.

---

## 13. Le conseiller LLM (testé à part, pas dans la candidate)

### Comment il fonctionne
- Le modèle local **qwen2.5:3b** (Ollama) reçoit un résumé de la situation (files,
  événements) quand un **nouvel événement** arrive ou **toutes les 10 min**, jamais deux fois
  en moins de 30 s.
- Sa réponse JSON est vérifiée (carrefours et phases existants) ; un conseil ne devient actif
  qu'après la **latence réelle** de l'appel.
- Un conseil ajoute `β × poids` (au plus 4) au logit de la phase conseillée, **avant** le
  biais Max-Pressure. Ensuite, comme toujours : ambulance, puis bouclier.

### Le résultat (grille, urgences, pointe, 5 graines de test, modèle t1)
- Techniquement tout marche : 13,8 appels par épisode, **100 % de réponses valides**, aucun
  repli, environ 7,9 s par réponse.
- Mais il fait **un peu moins bien** que la candidate seule : trajet −1,4 % [−2,4 ; −0,7],
  attente −2,9 % [−5,1 ; −1,4], ambulances 48,8 s contre 40,4 s.

Avec l'oracle (partie 8), c'est un **résultat négatif mesuré** : on le dit tel quel.

### Code
- [src/cotraffic/llm/advised.py](../src/cotraffic/llm/advised.py) : principe lignes 1-11,
  paramètres `AdvisorConfig` lignes 39-45, déclencheurs `_trigger` ligne 104,
  biais `bias_logits` lignes 228-256.
- Branchement dans la candidate : [hybrid.py](../src/cotraffic/controllers/hybrid.py),
  lignes 266-267.
- Réglages justifiés : [configs/llm.yaml](../configs/llm.yaml).
- Journal de chaque appel : `results/combined/calls/*.jsonl`.

---

## 13 bis. Le LLM dans la boucle de décision : le « LLM stratège » (ajouté après l'évaluation)

### Ce qu'il fait
Une cinquième couche, **au-dessus** des quatre de la candidate. Toutes les **5 minutes**, le LLM
local (qwen2.5:3b) lit un résumé du réseau et choisit le **mode** de tout le réseau pour les
5 minutes suivantes, parmi trois modes déjà validés :

| Mode | Ce qui décide les phases | Quand le choisir (consigne du prompt) |
|---|---|---|
| **équilibre** | la candidate (COOP-FULL + biais β = 4) | par défaut |
| **fluidité** | Max-Pressure à chaque feu | quand la file à l'entrée du réseau grandit (saturation) |
| **agent seul** | COOP-FULL sans biais (β = 0) | peu de véhicules arrêtés et une foule de piétons |

Dans les trois modes, **la priorité ambulance et le bouclier restent actifs** : le LLM ne
commande jamais un feu directement.

### Ce qu'il lit (exemple réel, graine de validation)
```
t=600s of 2700s; current mode: equilibre (since t=0s)
network: 16 junctions, 472 vehicles, 93 halted (5 min ago: 78)
vehicles waiting to enter the network: 2 (5 min ago: 0)
halted per junction: mean 5.8, max 11 at D1; junctions with >= 10 halted: 1 of 16
pedestrians waiting: 0
events: none
```
Réponse imposée par un schéma JSON : `{"mode": "equilibre", "reason": "..."}`.

### Les garde-fous (le calcul exact)
1. **Trois modes seulement** : le schéma JSON n'accepte que `equilibre`, `fluidite` ou `agent`.
2. **Réponse invalide** : une seconde tentative, puis le mode actuel est gardé.
3. **Latence honnête** : la décision ne s'applique qu'à `t + latence réelle` (environ 7 s).
4. **Serveur absent ou délai dépassé** : le mode actuel est gardé, l'épisode continue.
5. **Sécurité** : EV-RULE puis le bouclier, après le mode, comme pour la candidate.

### Pourquoi à ce niveau
Le LLM met plusieurs secondes à répondre : il ne peut pas décider une phase toutes les 5 s.
Le premier essai (le conseiller de phases, partie 13) faisait un peu moins bien. Le rôle de
stratège est celui dont l'**oracle** (partie 8) a mesuré le plafond, avec **les mêmes trois
modes et la même fenêtre de 5 minutes** : on peut donc comparer le LLM au choix parfait et au
hasard.

### Comment on l'a évalué
- **Graine de validation 1000**, les 14 cases principales : comparé à la candidate seule (même
  modèle t1), à l'oracle et au placebo.
- Puis **graines de test**, les 18 situations, modèle t1, contre les épisodes de la candidate
  de l'évaluation finale (mêmes graines). **Exploratoire** : ajouté après le pré-enregistrement,
  qui reste la référence.
- Gain = (candidate − avec LLM) / candidate ; intervalle à 95 % par bootstrap sur les épisodes
  appariés.

### Résultat sur la graine de validation
Dans 10 cases sur 14, le LLM garde « équilibre » : les épisodes sont **identiques** à ceux de la
candidate (la simulation est déterministe). Dans les 4 cases où il intervient, le trafic
s'améliore à chaque fois. Par exemple, sur le quartier réel avec incident en pointe : trajet
+3,0 %, attente +14,0 %. Seul bémol : sur le quartier réel avec urgences en pointe, le retard
des ambulances augmente de 4,4 % (une seule graine).

### Résultat sur les graines de test (exploratoire)
**90 épisodes** : les 18 situations, 5 graines de test, modèle t1. Chacun est comparé à
l'épisode de la candidate seule sur la même graine. **1 746 appels, 100 % de réponses
valides, 7,1 s de réponse en médiane.**

- **Effet moyen nul, non démontré** : trajet +0,2 % [−0,4 ; +1,1], attente +0,6 % [−1,3 ;
  +3,4], ambulances +4,3 % [−0,3 ; +10,5]. Tous les intervalles contiennent 0.
- **9 situations sur 18 identiques** : le LLM y garde toujours « équilibre ».
- **Il aide là où la candidate était faible** :
  - grille avec piétons en pointe : trajet +3,1 %, attente +7,2 % ;
  - quartier réel avec urgences en pointe : attente +4,7 %, ambulances +9,0 %.
- **Il se trompe parfois** :
  - capteurs bruités : attente −2,7 %, car il choisit « fluidité » alors que Max-Pressure
    souffre justement des capteurs bruités ;
  - quartier réel avec incident en pointe : attente −7,2 %.

**En une phrase pour le jury :** le LLM est vraiment dans la boucle de décision ; il ne coûte
rien en moyenne, il aide là où la candidate souffrait (piétons en pointe), il se trompe dans
d'autres cas, et la sécurité ne dépend jamais de lui.

Détail : page « Le LLM dans la boucle » du tableau de bord, `results/llm_loop/report.md`.

### Limite à dire
Ses justifications ne sont pas toujours exactes. Il écrit parfois « peu de véhicules arrêtés »
alors qu'il y en a 195 : c'est un modèle de 3 milliards de paramètres. C'est justement pour cela
qu'il ne choisit qu'entre des modes validés, et que la sécurité reste hors de son contrôle.

### Code
- [src/cotraffic/llm/strategist.py](../src/cotraffic/llm/strategist.py) : les trois modes
  ligne 36, ce que le LLM lit `network_state` ligne 87 et `state_text` ligne 112, l'appel et
  les garde-fous `_ask` lignes 168-202 (latence ligne 199), le mode appliqué au réseau
  `modes` ligne 204, la politique `LlmStrategyPolicy.act` ligne 229 (β = 4 en équilibre,
  0 sinon).
- Le prompt : [configs/prompts/strategist-v1.yaml](../configs/prompts/strategist-v1.yaml).
- L'étude : [scripts/llm_loop.py](../scripts/llm_loop.py) ; les journaux de chaque appel :
  `results/llm_loop/calls/*.jsonl`.
- Tests : [tests/test_strategist.py](../tests/test_strategist.py).

---

## 14. Robustesse, généralisation et grande ville

| Situation | Ce qu'on perturbe | Trajet | Attente |
|---|---|---|---|
| Capteurs bruités | bruit de 2 véhicules sur chaque comptage, 20 % des détecteurs à 0 | +6,1 % **prouvée meilleure** | +14,1 % **prouvée meilleure** |
| Pertes de messages | 30 % des messages des voisins perdus | −1,7 % vraie perte | −1,0 % trop large |
| Bus | un bus toutes les 5 min par ligne et par sens | −0,9 % prouvée non inférieure | +2,0 % **prouvée meilleure** |
| grid8x8 | 64 feux, modèles entraînés sur 16 | −2,1 % vraie perte | −1,5 % vraie perte |

Pourquoi les capteurs bruités sont la plus grande victoire : Max-Pressure ne voit que ce qui
est détecté, donc il se trompe quand les détecteurs mentent (255 s de trajet contre 218 s pour
la candidate) ; l'agent seul aussi (232 s). La combinaison résiste le mieux.

**La grande ville n'est pas testée** : à Barcelone, le réseau importé se bloque sous tous les
contrôleurs, temps fixe compris ; à Paris, Max-Pressure s'effondre là où le temps fixe
fonctionne. Un test y mesurerait ces défaillances, pas la qualité du contrôle. Arrêté avant
toute graine de test : [docs/FAILURES.md](FAILURES.md), F-016.

Code : les perturbations dans [configs/scenarios/](../configs/scenarios/) ; la tentative
dans [scripts/bigcity.py](../scripts/bigcity.py).

---

## 15. Le tableau de bord : d'où viennent les chiffres affichés

- [scripts/dashboard_combined.py](../scripts/dashboard_combined.py) relit les résultats avec
  les fonctions figées de l'analyse et écrit `frontend/public/data/combined/` : `study`,
  `cells`, `tests`, `layers`, `validation`, `bilan`, `bigcity`.
- [scripts/combined_figures.py](../scripts/combined_figures.py) écrit
  `frontend/public/data/final_controller.json` (compromis, ambulances, démo).
- Chaque fichier est vérifié par un schéma Zod :
  [frontend/src/shared/schemas/combined.ts](../frontend/src/shared/schemas/combined.ts).
- Les phrases des pages sont construites autour de ces nombres, jamais écrites à la main :
  [frontend/src/features/combined/claims.ts](../frontend/src/features/combined/claims.ts) ;
  un test vérifie qu'ils correspondent à l'analyse figée
  ([claims.test.ts](../frontend/src/features/combined/claims.test.ts)).
- Les pages : [accueil](../frontend/src/features/home/HomePage.tsx),
  [contrôleur final](../frontend/src/features/final-controller/FinalControllerPage.tsx)
  (forest plot : [ForestPlot.tsx](../frontend/src/features/final-controller/ForestPlot.tsx)),
  [robustesse](../frontend/src/features/robustness/RobustnessPage.tsx).

---

## 16. Antisèche pour la validation (10 phrases)

1. Aucun contrôleur n'est le meilleur partout ; le nôtre est **le meilleur compromis** :
   pire écart de 12,2 % contre 35 à 99 % pour les autres.
2. Il a 4 couches : l'agent PPO propose, Max-Pressure corrige avec un bonus de 4, l'ambulance
   passe avant tout, le bouclier garantit la sécurité.
3. Le bonus de 4 multiplie par 55 la probabilité de la phase de Max-Pressure : l'agent ne le
   contredit que s'il est sûr à plus de 98 %.
4. On l'a choisi parmi 15 variantes, **sur des graines de validation seulement**.
5. Tout a été **figé avant le test** (commit 2c0dd1d), et le script refusait de tourner si un
   fichier changeait.
6. Une seule évaluation : 1 265 épisodes, graines 0 à 4, 3 modèles, 18 situations.
7. 36 tests de non-infériorité avec Holm : 15 passent dont 6 meilleurs ; 5 vraies pertes,
   petites ; 16 trop larges.
8. Ambulances : 71 trajets sur 72 plus rapides qu'avec Max-Pressure à l'heure de pointe.
9. Le LLM : un oracle a montré qu'un choix parfait de stratégie rapportait trop peu ; le
   conseiller testé fait un peu moins bien. Il n'est pas dans la décision.
10. Ce qu'on ne prétend pas : être meilleur partout, ni généraliser à une grande ville.
