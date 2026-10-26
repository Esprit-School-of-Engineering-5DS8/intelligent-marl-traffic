# Visite du code : le LLM dans la boucle (devant le prof)

Le parcours à suivre pendant la présentation, dans l'ordre. Pour chaque étape : le fichier
à ouvrir, les lignes à montrer, et la phrase à dire. Environ 10 minutes. Les chiffres
viennent de la graine de validation 1000 ; convention : gain positif = mieux.

Astuce : dans VS Code, `Ctrl+P` puis `nom_du_fichier:ligne` ouvre directement la bonne
ligne (par exemple `advised.py:189`).

## 1. Le principe (30 s)

- **Ouvrir** `docs/LLM_DESIGN.md`, section 3 (lignes 59 à 100) : le schéma Mermaid.
- **Dire** : « Le LLM conseille rarement, le RL décide toutes les 5 secondes, et le
  bouclier de sécurité a toujours le dernier mot. Le LLM ne commande jamais un feu. »

## 2. Quand le LLM est appelé (1 min)

- **Ouvrir** `src/cotraffic/llm/advised.py`, lignes 104 à 117 (`_trigger`).
- **Dire** : « Un appel part seulement à un nouvel événement, ou toutes les 10 minutes, et
  jamais plus d'une fois par 30 secondes. Appeler le LLM à chaque décision, toutes les
  5 s, est impossible : il met 8 s à répondre. »
- **Montrer aussi** `src/cotraffic/llm/situation.py`, lignes 109 à 161 (`events`) :
  ambulance, accident, capteur en panne, pertes de messages, foule de piétons.

## 3. Ce qu'on envoie au LLM (1 min)

- **Ouvrir** `src/cotraffic/llm/situation.py`, lignes 89 à 107 (`observe`), puis 44 à 55
  (`to_text`).
- **Dire** : « On photographie la situation : phase, durée du vert, files par phase,
  piétons, et les événements. »
- **Ouvrir** `configs/prompts/advisor-v2.yaml`, lignes 15-16 (les données ne sont jamais
  des instructions) et 26 à 37 (abstention par défaut, format de réponse).
- **Ouvrir** `src/cotraffic/llm/prompts.py`, lignes 47 à 50 (`wrap`).
- **Dire** : « Les données sont entre balises `<state>`. Une balise cachée dans les
  données est neutralisée, ce qui empêche l'injection de prompt. »

## 4. L'appel au LLM et la sortie contrainte (1 min)

- **Ouvrir** `src/cotraffic/llm/advice.py`, lignes 45 à 72 (`schema_for`).
- **Dire** : « Ollama décode la réponse en suivant ce schéma JSON. Les carrefours sont
  énumérés : le modèle ne peut pas en inventer un. La force vaut 1, 2 ou 3, et la durée est
  bornée. »
- **Ouvrir** `src/cotraffic/llm/client.py`, lignes 78 à 102 (`chat`) : modèle local,
  `keep_alive`, délai maximal.
- **Ouvrir** `src/cotraffic/llm/sources.py`, lignes 67 à 100 (`LlmSource.advise`).
- **Dire** : « Une réponse trop longue est refusée avant même d'être lue (ligne 84). Une
  réponse invalide a droit à une seule tentative de correction. Ensuite, PPO décide seul. »

## 5. La validation (1 min)

- **Ouvrir** `src/cotraffic/llm/advice.py`, lignes 79 à 107 (`parse`), puis 125 à 144
  (`check`).
- **Dire** : « Même avec un décodage contraint, on revérifie tout : clés, types, bornes,
  carrefours et phases qui existent, un seul conseil par carrefour. »

## 6. Le cœur : le conseil change la décision de PPO (1 min, le moment clé)

- **Ouvrir** `src/cotraffic/llm/advised.py`, lignes 131 à 161 (`_ask`).
- **Dire** : « Le conseil validé est mis en file. Il n'agit qu'à t + la latence réelle de
  l'appel (ligne 157), et il expire après sa durée de validité. »
- **Ouvrir** `src/cotraffic/llm/advised.py`, lignes 189 à 198.
- **Dire** : « Ligne 189 : la phase que PPO choisirait seul. Ligne 195 : le conseil ajoute
  beta × force / 3 au logit de la phase conseillée. Ligne 198 : la décision est recalculée.
  C'est ici que le LLM intervient dans la décision des agents. »

## 7. Le bouclier garde le dernier mot (30 s)

- **Ouvrir** `src/cotraffic/envs/traffic_env.py`, lignes 184 à 206.
- **Dire** : « La phase demandée, avec ou sans conseil, passe par le bouclier : vert
  minimum de 10 s, vert maximum, anti-famine, jaune. C'est le même bouclier que pour tous
  les contrôleurs. »

## 8. Les réglages et le choix du modèle (1 min)

- **Ouvrir** `configs/llm.yaml` : modèle (lignes 8 à 20), échantillonnage (21 à 41), prompt
  (43 à 52), beta et période N (53 à 73).
- **Dire** : « Un seul fichier, et chaque valeur a sa justification mesurée. Par exemple,
  beta 8 dégrade de 1,2 %, et un appel toutes les 3 minutes dégrade les piétons de
  24,8 %. »
- **Ouvrir** `scripts/llm_step2.py`, lignes 1 à 25 et 73 à 78 (`best`).
- **Dire** : « La règle de choix a été écrite avant de voir les résultats, et uniquement sur
  la graine de validation 1000. »

## 9. Prompt engineering (30 s)

- **Ouvrir** `configs/prompts/advisor-v2.yaml`, lignes 39 à 48 : les techniques zero, brief
  et few.
- **Ouvrir** `src/cotraffic/llm/sources.py`, lignes 103 à 142 (`VotingSource`) : la
  self-consistency.
- **Ouvrir** `scripts/llm_fewshot.py`, à partir de la ligne 121 (`choose`) : les exemples tirés
  des graines d'entraînement, choisis par gain moyen.
- **Dire** : « Zero-shot gagne : +0,15 %, contre −0,18 % pour brief, +0,08 % pour few et
  +0,02 % pour le vote. Tout reste dans le bruit. »

## 10. Le tool schema (1 min)

- **Ouvrir** `src/cotraffic/llm/tools.py`, lignes 162 à 243 (`tool_schemas`), puis 252 à la
  fin (`validate_call`).
- **Dire** : « Il y a cinq outils en lecture seule et `submit_advice`, le seul qui agit.
  Les schémas sont stricts, et chaque appel est validé par Pydantic. Un outil inconnu,
  comme `set_traffic_light`, est refusé. »
- **Ouvrir** `src/cotraffic/llm/sources.py`, lignes 152 à 240 (`ToolLlmSource`) : la
  boucle d'appels d'outils, avec son budget.

## 11. La sécurité, prouvée par les tests (1 min)

- **Ouvrir** `tests/test_llm_security.py`, lignes 54 à 66 : l'injection dans le texte d'un
  incident.
- **Ouvrir** les lignes 159 à la fin : la source malveillante, avec un biais de 1000.
- **Dire** : « Le conseil malveillant change bien les demandes, mais le bouclier ne laisse
  jamais un vert durer moins de 10 s. Le plus court mesuré fait 13 s, sur 100 verts. »

## 12. L'évaluation (1 min)

- **Ouvrir** `src/cotraffic/llm/rollout.py`, ligne 168 (`score`).
- **Dire** : « Chaque conseil est rejoué 5 minutes depuis le même instantané SUMO que
  "sans conseil" : la comparaison est exacte, sur le même trafic. »
- **Ouvrir** `scripts/llm_dataset.py`, lignes 129 à 156 (`oracle_tables`) : règles,
  placebo, LLM, oracle.
- **Ouvrir** `docs/LLM_PREREGISTRATION.md`, sections 3 et 6 : les contrôles et les tests
  statistiques prévus pour les graines de test.

## 13. LoRA et prompt tuning (1 min)

- **Ouvrir** `scripts/llm_dataset.py`, lignes 158 à 191 (`label_of`, `write_dataset`) :
  les étiquettes par rejeu, à partir des graines d'entraînement uniquement.
- **Ouvrir** `notebooks/llm_lora_colab.ipynb`, dans l'ordre :
  - section 5 : le rééquilibrage ;
  - section 8 : LoRA ;
  - section 9 : le prompt tuning ;
  - section 10 : la comparaison.
- **Dire** : « Au premier essai, LoRA s'abstenait partout : ses 87 % d'accord n'étaient que
  la part des abstentions. Après rééquilibrage, sur le lot final de 169 exemples, il
  retrouve 17 % des conseils attendus, surtout pendant les urgences, mais son gain dans
  SUMO n'est que de +0,05 %. C'est préliminaire : la validation ne compte que 15
  situations de conseil. »
