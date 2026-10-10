# Ideate: Where do agents + LLMs actually go in this project?

Status: draft for the team, 2026-10-10 (Amen). Not committed.

Purpose: the prof's requirement is "agents must be present" with a hint at
cooperation between agents and other models. This doc (a) pins down what that
requirement is and isn't, (b) states what the repo already gives us to build on,
and (c) lays out the candidate approaches with trade-offs and a recommendation.

---

## 1. What the constraint actually says

Verbatim from Amen: "she just said we need agents to be present, and she hinted at
cooperation between agents and other models."

That is under-specified in the way that matters. Read literally, the project already
satisfies it: `MultiAgentEnv` has one agent per intersection, and the EV priority
module is an agent cooperating with a learned model (the ETA predictor). Read
strictly, it could mean the prof wants **LLM-based agents**, or wants **explicit
inter-agent cooperation** (message passing / negotiation) on top of the existing
per-intersection control.

Three readings, all defensible:

| Reading | What it demands | Risk if we guess wrong |
|---|---|---|
| R1. "Agents" = the MARL agents we already have | Nothing new; the RL setup counts | Prof expected LLMs, we look like we ignored the instruction |
| R2. "LLM agents present" | An LLM must be an active decision-making agent in the loop | Over-build; LLM control is slow and may lose to RL on metrics |
| R3. "Cooperation between agents AND other models" | Agents must talk to each other and to non-agent models (forecasters, RL policies) | Under-build; a lone LLM bolted on the side doesn't show cooperation |

**Action item for the team:** ask the prof one clarifying question with concrete
options, e.g. *"If we keep RL agents as the low-level controllers but add an LLM agent
that coordinates them and works with the forecasting models, is that within scope, or
do you want the LLM itself making the signal decisions?"* Do not build on a guess.

My read of her wording ("cooperation between agents **and other models**") points at
R3: a hybrid where agents cooperate and also collaborate with non-agent models. That
also happens to be the least wasteful option given what's already built.

---

## 2. What the repo already gives us (build on this, don't restart)

Live state, checked 2026-10-10 on branch `amen/ev-priority`:

- **Environment** — `environment/multi_agent_env.py`, a generic multi-agent SUMO
  wrapper ("works with any .sumocfg — 2x2, 3x3, or Monaco"). Each controlled
  traffic light is already an agent (`BaseTrafficAgent.select_action`).
- **Agents** — `max_pressure.py` (adaptive heuristic), `pedestrian_adaptive.py`,
  `emergency_priority.py` (Amen's: reactive pre-emption + predictive corridor),
  and learned policies in `agents/rl/` (DQN, PPO, replay buffer).
- **Forecasting layer** — `forecasting/` already has trained artifacts:
  `ev_eta.joblib` (arrival-time regression), `ev_red.joblib` (red-arrival
  classifier), `ev_rl_policy.joblib`. `travel_time_model.py` and
  `pedestrian_counter.py` are scaffolded.
- **Baselines** — reference controllers on branch `feature/reference-baselines`:
  fixed-time, actuated, green wave, max-pressure + benchmark suite. Every
  comparison the success criteria need is already there.
- **Teammate branches (all 2026-10-08, teammates moving independently):**
  - `feature/marl-env-standardization` — PettingZoo-compliant `SumoMARLEnv`,
    multi-objective rewards.
  - `feature/monaco-real-scenario` — Phase 3 real-world network (MoST).
  - `feature/multimodal-traffic-demand` — multi-modal infra, demand profiles,
    EV/pedestrian metrics.
  - `qlearning-agents` — a separate Q-learning/DQL tutorial track.
- **Gap:** grep for `llm|gpt|communication|coordinate` across `agents/` and
  `environment/` returns nothing. There is **no LLM anywhere in the codebase yet.**
  The cooperation requirement is currently unmet through the strict readings.

Takeaway: the control substrate and the baselines are done. The LLM piece is a
greenfield addition on top of a working system, not a rewrite.

---

## 3. The approach space

Six candidate ways to bring LLMs/agents into the loop, roughly ordered from
"LLM does the control" to "LLM sits around the control."

### A. LLM as the direct policy (one LLM per intersection)
Give an LLM the intersection state as text and have it output the phase decision.
This is the LLMLight / CoLLMLight line of work.
- Pro: most literal reading of "LLM agents"; decisions come with natural-language
  reasoning, which demos beautifully and aids the report.
- Con: slow (seconds per decision vs SUMO's sub-second steps), token cost, hard to
  beat RL on delay/throughput, and doesn't scale to 9+ intersections in real time.
- Verdict: good for a **single-intersection showcase**, not for the main benchmark.

### B. LLM as coordinator over ML agents (hierarchical)  ← recommended spine
Keep the RL / heuristic agents as low-level controllers. Add an LLM **coordinator
agent** that sees a summarized network state plus events (an ambulance entered,
an incident, a surge) and issues *directives* to the downstream intersection
agents — e.g. sequence a green corridor, rebalance phase timing, raise the
pedestrian-priority weight on one corner. This is the LLM-AG pattern.
- Pro: exploits what each side is good at — RL for fast numeric control, the LLM
  for abstract, cross-intersection reasoning and coordination. Directly evidences
  "cooperation between agents and other models" (the coordinator talks to RL
  agents and to the forecaster). Fits Amen's EV work: the coordinator extends
  pre-emption from one light to a planned corridor.
- Con: needs a clean state-summary interface and a directive schema; LLM latency
  must be off the critical path (decide at event boundaries, not every step).
- Verdict: best fit for the requirement, the existing code, and the report story.

### C. LLM inside the forecasting layer (hybrid reasoning + numbers)
Let the LLM reason over context — incident descriptions, road layout, weather —
to *condition* or *override* the numeric forecasters (ETA, travel time, pedestrian
count). Not the LLM predicting numbers; the LLM adding context the GBM/LSTM can't.
- Pro: strengthens E2/M2/S2 without betting the project on LLM control quality.
- Con: an LLM is a worse point-forecaster than `ev_eta.joblib`; it must add
  context, not replace the model.
- Verdict: strong supporting role, pairs with B.

### D. LLM as operator interface / digital twin (conversational)
An LLM agent that answers the operator's (Karim's) questions in natural language,
generates test scenarios on demand, and explains the system's decisions. This is
the ChatSUMO / AgentSUMO / digital-twin line.
- Pro: maps directly to the Operator persona and the "network-wide visibility"
  success criterion; big, low-risk demo value; no real-time constraint.
- Con: sits *around* the control loop rather than in it — alone it may not satisfy
  "agents present in the control decisions."
- Verdict: excellent companion feature; not sufficient as the only LLM element.

### E. LLM as autonomous heuristic designer (code-generating)
An LLM coding agent evolves interpretable control heuristics (EvolveSignal-style).
- Pro: novel, publishable angle; produces explainable policies.
- Con: research-heavy, long runway, weak fit for a one-semester deliverable.
- Verdict: skip.

### F. Multi-agent LLM pipeline for the whole simulation lifecycle
Several LLM agents cover scenario generation → execution → analysis end to end
(Decoupled Intelligence-style).
- Pro: comprehensive "agents everywhere" story.
- Con: scope creep; overlaps what AgentSUMO already does; little relation to the
  traffic-control objectives the personas demand.
- Verdict: too broad for the current scope.

---

## 4. Recommendation

**Layer B as the spine, with C and D as the two supporting modules.**

```
        ┌──────────────────────────── LLM Coordinator Agent (B) ───────────────────────────┐
        │  sees: summarized network state, events (EV, incident, surge), forecasts (C)       │
        │  does: coordination directives — corridor sequencing, reweighting, phase policy    │
        └───────────────┬───────────────────────────────┬───────────────────────┬──────────┘
                        │ directives                     │ asks                  │ answers
                        ▼                                ▼                       ▼
   Intersection agents (RL / max-pressure / rule)   Forecasting models (C)   Operator LLM (D)
   one per light, fast, numeric control              ev_eta, travel_time      natural-language
                                                        pedestrian_count      visibility + explain
```

Why this shape:
- Satisfies R3 (cooperation between agents and other models) directly and visibly.
- Reuses every teammate's work (env, baselines, forecaster) instead of competing
  with it; the RL/rule agents remain the thing that beats the baseline on metrics.
- Maps to the personas: the coordinator = Operator visibility + EV corridor
  (E1/E2), the operator LLM = Karim, the conditioning = M2/S2.
- Keeps LLM latency off the real-time path — decisions happen at event boundaries,
  the fast loop stays numeric.

Suggested minimal first step (a prototype slice, not the whole thing): pick one
scenario (2x2 grid), have the coordinator agent take over Amen's existing EV
corridor logic — i.e. replace the fixed `EV_ETA_TRIGGER_S` rule with an LLM that
decides *which* downstream lights to pre-empt and *when*, and log its reasoning.
That is a small, demonstrable, self-contained agent that shows cooperation with
the ETA model and the per-light agents, and it plugs straight into code that exists.

---

## 5. Open questions for the team

1. Confirm scope with the prof (R1/R2/R3) before committing.
2. Which LLM — hosted API (latency, cost, needs a key) or a small local model
   (weaker reasoning, offline, no cost)? Affects whether "real-time" is even on
   the table.
3. Who owns the coordinator layer? It cuts across everyone's objectives, so it
   needs a named owner in the Roles section (currently blank).
4. Latency budget: at what simulation step cadence do LLM decisions run? Propose
   event-driven (on EV entry, incident, threshold crossing), not per-step.
5. Which branch is the integration base? Teammates are on four separate branches;
   the LLM layer needs a decided trunk to sit on.

---

## References
- LLMLight — LLMs as traffic signal control agents (ACM SIGKDD 2024).
- CoLLMLight — cooperative LLM agents for TSC (arXiv 2503.11739).
- LLM-AG — LLM agent-guided multi-agent system for adaptive TSC (Springer 2025).
- ChatSUMO / ChatSUMO-Agent — conversational control of SUMO simulations.
- AgentSUMO — LLM-guided agentic framework for traffic simulation (ACM 2025).
- EvolveSignal — LLM coding agent for interpretable fixed-time heuristics (arXiv 2509.03335).
- Survey of LLMs for urban traffic signal control (ScienceDirect, 2026).
