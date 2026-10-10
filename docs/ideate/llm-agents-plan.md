# LLM Agents for Intelligent MARL Traffic: Approach & Implementation Plan

> Suggested location in the repo: `docs/ideate/llm-agents-plan.md` (fits the *Ideate: approach shortlist, chosen direction* deliverable).
> Branch: `feat/llm-agents`. Status: Phases 0–1 implemented and committed.

---

## HANDOFF — session state (2026-10-10)

**Progress**

| Phase | Status | Commit |
|---|---|---|
| 0 — foundation & honest baselines | ✅ done | `4dd053c` |
| 1 — S1/S2/S3 scenarios + rule-based EV pre-emption (A3) | ✅ done | `26371b6` |
| 2 — LLM plumbing, DirectiveLayer, arbiter | next | — |

**Decisions taken while implementing (beyond this plan)**

- Additive strategy: `runner.py` untouched; canonical modules are new files under `environment/` (`topology.py`, `traffic_light.py`, `ev.py`, `incidents.py`, `_bootstrap.py`).
- Max-pressure lane groups come from the TLS program (`topology.action_for_link`), never lane-ID strings; phase durations pinned after every `setPhase`.
- Peak demand (S1) = separate seeded route file `grid3x3.peak.rou.xml` (2400 veh, seed 42), not SUMO `--scale` (which would also duplicate EVs).
- Scenario registry in `evaluation/scenarios.py`; A3 arm name is `ev_priority` (= max_pressure + `agents/ev_preemption.py`).
- A3 implemented fresh with topology link→phase mapping; Amen's `agents/emergency_priority.py` heuristics not used. His ETA predictor (`forecasting/ev_arrival_predictor.py` + joblib artifacts on `origin/amen/ev-priority`) is deferred to Phase 4.
- A3 trigger horizon is **25 s, not the plan's 20 s**: the base policy can commit to the opposite phase just before the EV enters a 20 s window; 25 s covers in-flight transition + min_green + yellow. A 5-step grace window also keeps the preemption alive while the EV crosses a junction (it disappears from EV sensing on internal lanes).
- Incident S3: edge `A1A0` (busiest interior edge, 308 veh at peak), 300 s starting at t=1200; incident config disables teleporting (`time-to-teleport -1`), otherwise SUMO removes the queue after 180 s.
- Civilian KPIs exclude `ev_*` and `incident_*` ids; EV KPIs (`ev_count`, mean/max duration, waiting) are separate columns.
- `--seeds 0` = no explicit `--seed` (reproduces the plan's sanity table); use `--seeds 1,2,3` for real runs.

**Verified numbers (`results/` is gitignored)**

- S0 exact reproduction: sumo_default 132.09 / fixed 87.96 / max_pressure 11.45 s mean step wait.
- S1 peak: 27.75 ± 0.81 s step wait, 2369 ± 1.5 of 2400 arrive.
- S2 single diagonal EV: EV travel 100.0 ± 3.5 s (A2) vs **64.3 ± 9.2 s (A3)**; dual overlapping EVs: 72.3 ± 2.6 s vs **55.3 ± 5.8 s**; civilian cost ≤ ~5%.
- S3: A3 bit-identical to A2 (no EVs) — no-regression check.

**Known gaps / warnings for the next session**

- While an EV is queued at rank-1, distance/speed ETA to rank-2 explodes → the corridor preempts late; one seed still shows one stop. Phase 4's ETA model should fix this.
- A3 must migrate onto the Phase 2 `DirectiveLayer` (Appendix B) without losing `begin_step()` semantics (grace window) and the 25 s horizon.
- `MultiAgentEnv.build_agents()` pins phases and disables SUMO's timer — never call it for `sumo_default`.
- Run parallel experiments with distinct ports (`run_experiments` assigns them automatically).

**Verification**

```bash
~/.venvs/sumo/bin/python -m pytest tests/ -q     # 30 passed
~/.venvs/sumo/bin/python evaluation/run_experiments.py --scenario grid_3x3_ev,grid_3x3_ev2 \
    --arms max_pressure,ev_priority --seeds 1,2,3 --steps 3600 --jobs 4
```

---

## 0. TL;DR

- The professor wants **LLM agents** in the project. We add them as a **slow "brain" layer** on top of the existing **fast signal controllers**. We do not replace the controllers.
- **Fast layer (every 1 s):** max-pressure now, DQN later. Handles normal traffic. Already has min-green and yellow safety.
- **Slow layer (every ~30 s + on events):** three LLM agents (**Operator, Emergency, Pedestrian**) that read a compact snapshot of the grid and emit small, typed **directives**.
- **Arbiter (plain code, not an LLM):** validates directives, resolves conflicts (EV > pedestrian > flow), enforces guardrails, and falls back to the fast layer on bad or late output.
- **Agents interact** through a shared **blackboard** (typed JSON messages). Every message and decision is logged.
- We prove value with **scenarios where LLMs should help** (EV, incident, pedestrian surge, peak demand), against **fixed-time, max-pressure and rule-based EV pre-emption**. Where the LLM doesn't help, we report that honestly.
- **Before any of this:** the max-pressure baseline in the repo is buggy (section 5). Fix it first, or every comparison is meaningless.

---

## 1. Context & goal

**Project:** SUMO + TraCI, one controller per intersection (2x2 and 3x3 grids, Monaco planned), binary action (NS green / EW green).

**Charter scope this plan serves:**

| Charter item | LLM-layer component |
|---|---|
| Operator persona (Karim): network-wide visibility, early incident detection | Operator agent |
| E1/E2: emergency green corridor, EV detection & ETA | Emergency agent (+ rule-based baseline) |
| S1/S2: pedestrian-adaptive crossings | Pedestrian agent |
| F3: inter-agent communication & cooperation | Blackboard + arbiter |
| Mehdi's frustration: "unclear traffic decisions" | Operator agent's logged explanations |
| Open question: reward / objective trade-offs | Priority order in arbiter; optional LLM-set weights later |

**Constraints that shape the design:**
- 1 s steps x 9 intersections = ~32,000 decisions per run, so an LLM cannot sit in the fast loop (cost, wall-clock time).
- SUMO only advances when we call `simulationStep()`, so LLM latency does not break the simulation. It only costs wall-clock time.
- Safety must never depend on LLM output.

---

## 2. Research summary

Summaries come from abstracts and search snippets. **Read the papers before citing numbers.** Numbers are author-reported on different benchmarks and will not transfer to our grid.

| Work | Idea | What we take | Caveat |
|---|---|---|---|
| **LLMLight** (KDD 2025) | One LLM per intersection; traffic state verbalized to text; LLM picks the phase. Also a fine-tuned backbone (LightGPT). | Verbalized observation format; "pure LLM per intersection" as an experimental arm. | Per-step calls are costly. Fine-tuning is out of our scope. |
| **CoLLMLight** (ICLR 2026) | Cooperating LLM agents; slow reasoning runs **asynchronously**, guidance is **cached** and used by real-time decisions. | Core of our two-speed idea. Neighbor context in the prompt. | Their fine-tuned small models are out of scope. |
| **LA-Light** | LLM uses **perception and decision tools**; evaluated in **SUMO**; works without extra training. | Tool-style design (stretch goal); SUMO evaluation precedent. | Single-intersection focus. |
| **iLLM-TSC** | RL decides, LLM **checks and corrects** the decision; targets rare events (EVs) and degraded communication. | "Fast policy + LLM override on rare events" pattern. Arbiter as the checker. | Authors report ~17.5% lower waiting time under degraded communication (their setup). |
| **REG-TSC** | Distributed LLM agents with RAG for emergency vehicles; notes LLMs **hallucinate in emergencies**, adds a reviewer step. | Guardrails + reviewer logic for EV decisions. Always compare with a rule-based baseline. | Large reported EV-wait reduction is on their benchmarks. |
| **TrafficGen** | Multi-agent LLM orchestration (LangGraph) for emergency corridor pre-emption; proof of concept. | Corridor-planning as a multi-agent task. | Page not fetchable; seen only via snippet. |
| **LLM-driven reward weights** (Choi & Lim, JIPS 2025) | LLM adjusts RL reward weights in real time. | Optional later: LLM tunes DQN reward weights. | Single intersection, D3QN. |
| **SIGMA**, **multi-objective RLAIF** | LLM turns operator instructions into rewards; LLM preferences for multi-objective RL. | Future work. | Not needed for MVP. |

**Takeaways:**
1. The strongest systems keep the LLM **out of the 1 s loop** and use it for rare events and coordination.
2. LLMs need **guardrails** in emergencies (hallucination risk).
3. Nothing I found combines operator + emergency + pedestrian agents on SUMO. That combination is our angle. I did not do an exhaustive search.

---

## 3. Approach: a two-speed system

**Principles**
1. **LLMs advise, code decides.** The LLM never touches TraCI. It only emits typed directives.
2. **Everything expires.** Every directive has a TTL (default 30 s). Stale directives are the main failure mode.
3. **Safe by construction.** Min-green, yellow, starvation caps and pedestrian clearance live in code.
4. **Always a fallback.** Invalid JSON, timeout, or no response means the fast layer continues unchanged.
5. **Measure against honest baselines**, including a rule-based EV pre-emption. The LLM must earn its place.
6. **Reproducible.** Temperature 0, fixed seeds, record/replay of LLM responses.

---

## 4. Architecture

```
                 SLOW LAYER  (LLM, every ~30 s sim-time + on events)
  ┌──────────────────────────────────────────────────────────────┐
  │  Operator agent     Emergency agent     Pedestrian agent     │
  │  (grid-wide)        (per active EV)     (per crossing)       │
  │        │                  │                   │              │
  │        └──────── BLACKBOARD (typed messages) ─┘              │
  └───────────────────────────┬──────────────────────────────────┘
                              │ proposed directives (JSON)
                              ▼
                  ┌───────────────────────┐
                  │  ARBITER  (plain code) │  validate, clip, resolve conflicts
                  │  EV > ped > hold > bias│  starvation guard, role permissions
                  └───────────┬───────────┘
                              │ active directives (with TTL)
                              ▼
                 FAST LAYER  (every 1 s)
  ┌──────────────────────────────────────────────────────────────┐
  │  base policy (max-pressure → DQN)  →  DirectiveLayer         │
  │  → TrafficLightAgent.step_control (min-green, yellow)        │
  │  → TraCI                                                     │
  └──────────────────────────────────────────────────────────────┘
```

### 4.1 Main loop

```python
for t in range(horizon):
    states = env.get_states()
    if supervisor.should_run(t, states):        # periodic tick OR event trigger
        supervisor.run(t, states)               # snapshot -> agents -> arbiter -> active directives
    actions = {}
    for tls, s in states.items():
        base = policy[tls].select_action(s)     # 0 = NS, 1 = EW
        actions[tls] = directive_layer.apply(tls, s, base, t)   # may override, never unsafe
    env.apply_actions(actions)                  # step_control enforces min-green/yellow
    env.step()
```

**Triggers for the slow layer**
- Periodic: every `delta_s = 30` sim-seconds (Operator).
- EV present in the network: Emergency agent re-plans every 10 s while the EV is active.
- Incident alert raised by the detector code: immediate Operator run.
- Pedestrian queue above a threshold: Pedestrian agent run (after the pedestrian scenario exists).

### 4.2 Observation snapshot (what agents see)

Compact JSON, not raw lane IDs. Compute NS/EW groups from the TLS program (section 5), not from ID strings.

```json
{
  "t": 420,
  "intersections": {
    "B1": {"phase": "NS", "time_in_phase_s": 18, "queue": {"ns": 7, "ew": 2},
           "wait_s": {"ns": 61, "ew": 9}, "ped_waiting": {"ns": 0, "ew": 0},
           "neighbors": {"N": "B2", "S": "B0", "E": "C1", "W": "A1"}}
  },
  "alerts": [{"kind": "spillback", "edge": "B2B1", "since_s": 40}],
  "evs": [{"id": "ev0", "edge": "left1A1", "speed": 13.9,
           "next_tls": [{"tls": "A1", "dist_m": 62, "eta_s": 6},
                        {"tls": "B1", "dist_m": 262, "eta_s": 24}]}],
  "blackboard": [{"from": "emergency", "type": "ev_corridor", "tls": ["A1", "B1"], "until": 450}]
}
```

- ETA = distance / current speed from `traci.vehicle.getNextTLS` (verified). A regression ETA model can replace it later (E2).
- Target size: ~600-1,000 tokens for the 9-intersection grid.

### 4.3 Directive contract (the only thing LLMs can emit)

| Type | Allowed from | Meaning | Params (starting values) | Fast-layer effect |
|---|---|---|---|---|
| `bias` | Operator | Soft preference for a direction | `ns`, `ew` in [0.5, 2.0]; `ttl_s` <= 60 | Scales the queue score used by the base policy |
| `hold` | Operator | Keep current green a bit longer | `phase`, `extra_green_s` <= 20; `ttl_s` | Blocks switching away until extra time elapses (total green cap 45 s) |
| `preempt` | Emergency | Hard priority for an EV | `phase`, `start_in_s`, `hold_s` <= 40, `ev` | Forces phase through normal yellow transition; overrides everything |
| `serve_ped` | Pedestrian | Guarantee a pedestrian window | `phase`, `min_green_s` | Ensures the crossing-green phase runs at least that long |

Output envelope (all agents):

```json
{"agent": "operator", "t": 420,
 "directives": [{"tls": "B1", "type": "bias", "ns": 1.5, "ew": 1.0, "ttl_s": 30},
                {"tls": "B2", "type": "hold", "phase": "NS", "extra_green_s": 15, "ttl_s": 20}],
 "alerts": [{"kind": "spillback", "where": "B2B1", "severity": "medium"}],
 "explanation": "Southbound queue on B2->B1 is growing; favoring NS at B1, extending NS green at B2."}
```

`{"directives": []}` is always valid. Doing nothing is a fine answer.

### 4.4 Arbiter rules

1. **Schema validation:** unknown TLS IDs, unknown types and wrong role (for example the Operator emitting `preempt`) are rejected.
2. **Clip** numeric params to the allowed ranges.
3. **Priority:** `preempt` > `serve_ped` > `hold` > `bias`. Two `preempt`s on the same TLS: earliest ETA wins.
4. **Starvation guard:** no approach stays red longer than `max_red_s = 90` because of directives (EV pre-emption may extend this, capped at 60 s).
5. **Pre-emption lead time:** switching takes up to `remaining min_green + yellow` (about 13 s with the repo defaults). The Emergency agent must request at least ~15 s before the EV's ETA when the TLS is in the opposite phase. The arbiter warns when the lead is too short.
6. **Failure handling:** invalid output, timeout (default 20 s wall) or a rejected directive means that item is dropped, logged, and the fast layer continues. Failure rates are KPIs.
7. **Feedback:** accepted/rejected/clipped results are posted to the blackboard so agents see what happened last tick.

### 4.5 The agents

| Agent | Trigger | Input | Output | Notes |
|---|---|---|---|---|
| **Operator** | every 30 s + alerts | Whole-grid snapshot + blackboard | `bias`/`hold` directives, `alerts`, `explanation` | Detection of incidents is done by **code** (halted-time and queue-growth thresholds). The LLM interprets alerts, coordinates neighbors and explains. |
| **Emergency** | EV exists; replan every 10 s | EV list with ETAs, queues on the corridor, incidents on the blackboard | `preempt` corridor plan | **A rule-based pre-emption also exists** (baseline and fallback). The LLM must beat or match it. Its added value is conflicts: two EVs, EV + incident, EV + pedestrian window. |
| **Pedestrian** | ped queue above threshold | Pedestrian counts per crossing, vehicle queues | `serve_ped` | Needs the pedestrian scenario (section 6). Optional for the MVP. |

**Inter-agent communication (v1):** a shared blackboard of typed messages (`ev_corridor`, `incident`, `ped_surge`, `arbiter_result`). Each agent's prompt includes the active messages. Example: the Operator sees an active EV corridor and does not bias against it. The Emergency agent sees a blocked edge and avoids planning through it. Direct neighbor-to-neighbor LLM chatter is a stretch goal.

### 4.6 LLM client layer

One interface, several backends:

```python
class LLMClient(Protocol):
    def complete(self, system: str, user: str, schema: dict) -> dict: ...
```

- `OpenAICompatClient`: any OpenAI-style endpoint (hosted APIs, Ollama, vLLM, LM Studio). Base URL, model and key come from environment variables, **never committed**.
- `AnthropicClient` (optional).
- `MockLLM`: deterministic rule-based stand-in. Lets the whole pipeline run and be tested offline.
- `ReplayLLM`: cache keyed by hash of (model, system, user). Reruns of the same seed are free and bit-identical. Record first, then replay for plots.
- Settings: temperature 0, JSON-only output, one retry on invalid JSON, then fallback.
- Small local models (about 7-8B) are often unreliable at JSON. Use the provider's JSON/schema mode if available, validate everything, and expect a higher failure rate.
- **Log every call** to JSONL: `t, agent, prompt_hash, tokens_in/out, latency, raw_response, parsed, arbiter_outcome`.

**Cost/time estimate (rough):** Operator ~120 calls per 3,600 s run, plus ~10-20 EV calls, so ~130 calls. At 2-5 s per call that is about 4-11 min per run (the simulation itself takes ~23 s). With ~2-3k input tokens per call, 3 seeds x 4 scenarios x ~130 calls is ~1,600 calls (~4M input tokens). Plan for 3 seeds first.

---

## 5. Current state of the repo & verified findings

Checked by running the repo's code in a sandbox with SUMO 1.28 (`pip install eclipse-sumo traci sumolib`). Your README asks for SUMO >= 1.20.

### 5.1 What exists
- Implemented: `sumo_default`, `fixed`, `max_pressure` in `scenarios/grid_3x3/runner.py` (contains its own `TrafficLightAgent`, which has min-green 10 s and yellow 3 s, and its own `MultiAgentEnvironment`).
- `environment/multi_agent_env.py` has **no** agent classes and no `get_states`/`apply_actions`, so runner and environment are duplicated.
- Stubs (TODO only): `agents/rl/*` (DQN, PPO, replay buffer), `agents/emergency_priority.py`, `agents/pedestrian_adaptive.py`, `forecasting/*`, `evaluation/*`. `custom` mode just calls max-pressure.
- Demand: `grid3x3.rou.xml` has 1,200 vehicles (cars and buses) over 3,600 s. Light: nearly all vehicles arrive. No EVs, pedestrians or incidents.
- Network: 9 TLS, 4 phases each (0 = NS green, 1 = NS yellow, 2 = EW green, 3 = EW yellow), 8 incoming lanes and 20 signal links per intersection. No sidewalks or crossings.

### 5.2 Gotchas that change the plan

**A. The max-pressure lane classification is wrong.**
Both versions decide NS vs EW by substring-matching lane IDs. Compared with the real lane geometry: `agents/max_pressure.py` misclassifies **30 of 72** incoming lanes, and `runner.py` misclassifies **10 of 72**.
Fix: derive the groups from the TLS program. Lanes whose links are green in phase 0 are NS; the rest are EW.

```python
st = traci.trafficlight.getAllProgramLogics(tls)[0].phases[0].state   # phase 0 = NS green
links = traci.trafficlight.getControlledLinks(tls)
ns_lanes = {l[0][0] for i, l in enumerate(links) if l and st[i] in "Gg"}
```

**B. SUMO's built-in program silently overrides the agents.**
`setPhase` keeps SUMO's own timer (42 s for greens). Held phases get switched to yellow by SUMO itself. In a 1,500 s run I measured **197 steps** where SUMO was in yellow while the agent believed it was green, next to 633 agent-initiated switches. This also breaks any `hold` or `preempt` semantics.
Fix: after every `setPhase`, call `setPhaseDuration(tls, 100000)` for green phases (3 for yellow), and set the initial phase explicitly at start.

**Impact on the baseline (3,600 s, single seed, `total_waiting_time_s` averaged over steps; sanity numbers, not results):**

| Controller | Arrived | Mean speed (m/s) | Mean step waiting (s) |
|---|---|---|---|
| `sumo_default` | 1180 | 7.41 | 132.09 |
| `fixed` | 1177 | 7.23 | 87.96 |
| `max_pressure` (as in repo) | 1182 | 8.36 | 42.75 |
| `max_pressure`, correct NS/EW groups | 1182 | 8.56 | 27.38 |
| `max_pressure`, correct groups + phase-duration fix | 1183 | 9.02 | **11.45** |

The corrected baseline is ~3.7x better than the one in the repo. If the LLM layer is compared against the buggy version it will look much better than it is. Also: with light demand there is little room to improve, so S0 is a "no regression" test, and we need higher-demand scenarios.

**C. Pedestrians change the traffic-light programs.**
Generating the grid with `--sidewalks.guess true --crossings.guess true` gives sidewalks (120 pedestrian lanes), 36 crossing edges, and TLS programs with **6 phases and 24 links** (greens at 0 and 3, a 5 s pedestrian-clearance phase after each green, yellows at 2 and 5). The repo's hard-coded `green_phases = [0, 2]` and `yellow = {0: 1, 2: 3}` break. Discover phases from the program, and make transitions go green, clearance, yellow, target. Today's switch logic jumps straight to yellow, which would cut off pedestrians mid-crossing. **Keep the pedestrian scenario as a separate scenario folder** so the baseline net is untouched.

**D. SUMO details verified**
- An EV is a `vType` with `vClass="emergency"`. `traci.vehicle.getNextTLS(id)` returns upcoming TLS, distance and state, which is enough for ETAs.
- `--tripinfo-output` gives per-vehicle `duration`, `waitingTime`, `timeLoss` (EV included) and `<personinfo>` records for pedestrians.
- Pedestrians need an explicit `<vType vClass="pedestrian">`. **Vehicles and persons must be time-sorted within a route file.** Put persons in their own `.rou.xml` and list both in `route-files` (`a.rou.xml,b.rou.xml`), otherwise persons silently fail to spawn.
- Not verified: incident injection (see section 6).

---

## 6. Scenarios, arms, KPIs

### Scenarios

| ID | Scenario | Notes |
|---|---|---|
| S0 | Normal demand (existing 1,200 veh/h) | Regression check |
| S1 | Peak demand | Raise demand until corrected max-pressure shows real queues; start at about 2x and calibrate |
| S2 | EV run(s) | 1 EV across the grid (diagonal route) in peak demand; then 2 overlapping EVs |
| S3 | Incident | Block an interior edge for ~300 s. Suggested: stop a vehicle in each lane via `traci.vehicle.setStop`. **Validate first.** |
| S4 | Pedestrian surge | Separate net with crossings (5.2-C); `personFlow` bursts at 1-2 intersections |

Use `generate_routes.py`-style seeded generation. Run each scenario with 3 seeds (5 if time allows). Run runs as separate processes (one TraCI connection per process).

### Arms

| Arm | Description |
|---|---|
| A0 | `sumo_default` |
| A1 | `fixed` |
| A2 | `max_pressure` (corrected) |
| A3 | A2 + **rule-based EV pre-emption** (the E1 baseline) |
| A4 | A2 + **LLM team** (main system) |
| A5 | *Optional:* pure per-intersection LLM (LLMLight style), decisions every ~10 s, one call for all 9 intersections, 1 seed, shorter horizon |
| A6 | *Optional, if DQN exists:* DQN, and DQN + LLM team |

### KPIs

- **Vehicles (from tripinfo):** mean `waitingTime` and `timeLoss` per vehicle, throughput, mean speed, CO2/fuel (existing metrics).
- **EV:** travel time, waiting time, stops; extra delay imposed on civilian vehicles during the EV window.
- **Incident:** time-to-detect (injection to alert), recovery time (queues back to baseline), total delay.
- **Pedestrians:** mean and 95th percentile wait, % crossings completed before phase end.
- **LLM operations:** calls/run, tokens, latency, invalid-output rate, fallback rate, directive acceptance/clip/reject rate.
- Report mean +/- std over seeds. Do not report single runs.

### Hypotheses (what "success" means)

| | Hypothesis |
|---|---|
| H1 (S0) | No regression: A4 within noise (about 5%) of A2 |
| H2 (S2) | A4 lowers EV travel time vs A2, and is at least as good as A3 |
| H3 (S3) | A4 shortens recovery / lowers delay vs A2 |
| H4 (S4) | Pedestrian wait goes down without more than about 5% extra vehicle delay |
| H5 | Explanations make decisions auditable (qualitative: a few annotated examples in the report) |

Null results are fine for the report as long as they are measured honestly. "LLM matches the rule-based baseline but adds explainability and handles X" is a valid finding.

---

## 7. Implementation plan

Effort: S = a few hours, M = about a day, L = multiple days. Each phase ends with a runnable command and acceptance criteria.

### Phase 0: Foundation & honest baselines (M) — ✅ done (`4dd053c`)
Tasks:
1. Branch `feat/llm-agents`. Do **not** edit teammates' stubs (`emergency_priority.py`, `pedestrian_adaptive.py`, `agents/rl/*`); add new files instead.
2. Move `TrafficLightAgent` into `environment/` (for example `environment/traffic_light.py`), add `get_states()`/`apply_actions()` to `MultiAgentEnv`. Keep `runner.py` working (thin it later).
3. `environment/topology.py`: NS/EW lane groups from the TLS program, neighbor map, phase discovery (no hard-coded indices).
4. Apply fixes 5.2-A and 5.2-B (including `setPhaseDuration`).
5. `evaluation/metrics.py`: parse tripinfo; `--seed` and `--tripinfo-output` plumbing.
6. `evaluation/run_experiments.py` skeleton: scenario x arm x seeds, `--jobs N`.

Done when: A0/A1/A2 run via `run_experiments` and reproduce the table in 5.2 (A2 about 11 s mean step waiting, single seed), and results land in `results/` as CSV.

### Phase 1: Scenarios + rule-based EV baseline (M) — ✅ done (`26371b6`)
Tasks: EV vType and EV generation in `generate_routes.py` (seeded, configurable depart/route); peak-demand option; incident injector (validate with a quick test); rule-based EV pre-emption (A3), coordinating with the owner of `agents/emergency_priority.py`.
Done when: S1/S2/S3 run for A2 and A3, and EV travel time is measured. A3 beats A2 on EV time.

### Phase 2: LLM plumbing, directive layer, arbiter (L)
Tasks:
1. `agents/llm/client.py` (`OpenAICompat`, `Mock`, `Replay`), `schemas.py`, JSONL call logger.
2. `agents/supervisor/blackboard.py`, `arbiter.py`, `supervisor.py`, `DirectiveLayer`.
3. `environment/snapshot.py` (state to compact JSON).
4. Wire into the main loop (4.1) with `MockLLM`.
5. Unit tests (`pytest`, no SUMO needed for arbiter/schema): clipping, role permissions, priority, starvation guard, TTL expiry, fallback.

Done when: a full S0 run with `MockLLM` completes, produces a decision log, and A4-with-empty-directives equals A2 exactly.

### Phase 3: Operator agent, real LLM (M)
Tasks: system prompt + 2-3 few-shot examples; alert detector (code); run S0, S1, S3 with the real LLM; record to `ReplayLLM` cache; inspect logs and fix prompt problems.
Done when: invalid-output rate is under about 5%, no S0 regression (H1), and S3 results are available.

### Phase 4: Emergency agent (M-L)
Tasks: prompt with ETA table and lead-time rule; corridor plan to `preempt` directives; compare with A3 on S2 (one and two EVs, EV + incident).
Done when: H2 is measured (win, tie or loss is reported), and the corridor logs are readable.

### Phase 5: Pedestrian agent (L, optional)
Tasks: build the separate crossing scenario (5.2-C); transition logic with pedestrian clearance; pedestrian metrics from tripinfo; agent + `serve_ped`.
Done when: H4 is measured on S4.

### Phase 6: Evaluation, extras, report (M-L)
Tasks: full grid (arms x scenarios x seeds) from the replay cache; plots in `evaluation/visualize_metrics.py`; optional A5 pure-LLM arm and A6 DQN integration; annotated decision-log excerpts for the demo; update README and the Ideate/Test docs.

### MVP = Phases 0-4
If time is short, stop after Phase 4. Phase 5 and the pure-LLM arm are bonus.

---

## 8. Proposed layout

```
agents/
  llm/
    client.py            # LLMClient, OpenAICompat, Mock, Replay
    schemas.py           # directive + envelope validation
    prompts/             # operator.md, emergency.md, pedestrian.md
    operator_agent.py
    emergency_agent.py
    pedestrian_agent.py
    pure_llm_agent.py    # optional (A5)
  supervisor/
    blackboard.py
    arbiter.py
    directive_layer.py
    supervisor.py
environment/
  multi_agent_env.py     # + get_states / apply_actions
  traffic_light.py       # TrafficLightAgent moved from runner.py
  topology.py            # NS/EW groups, neighbors, phase discovery
  snapshot.py            # state -> compact JSON
evaluation/
  run_experiments.py
  metrics.py             # tripinfo parsing
  visualize_metrics.py
scenarios/
  grid_3x3/              # + EV / peak / incident variants
  grid_3x3_ped/          # separate net with crossings
tests/                   # arbiter, schemas, topology, mock-supervisor smoke
docs/ideate/llm-agents-plan.md
```

---

## 9. Working agreements (for the coding agent / opencode)

- Work phase by phase. Prompt example: *"Implement Phase 0 of docs/ideate/llm-agents-plan.md; stop when the acceptance criteria are met and show me the commands to verify."*
- All LLM calls go through `LLMClient`. No vendor SDK calls scattered in agent code.
- No TraCI calls in `agents/llm/*`. LLM output only becomes directives; only `DirectiveLayer`/`env` touch TraCI.
- No API keys in the repo. Use environment variables; add `.env` to `.gitignore`.
- Every phase must leave `./run.sh --scenario grid_3x3 --mode max_pressure` working.
- New behavior needs a test with `MockLLM`; the arbiter and schema code must be testable without SUMO.
- Keep all tunables (`delta_s`, TTLs, caps, `max_red_s`, timeouts) in one config file or dataclass.
- Avoid touching teammates' stub files; ask them before changing shared files.

---

## 10. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Baseline bugs inflate LLM gains | Phase 0 first; report the corrected baseline |
| LLM latency / cost | Slow layer only; batch all intersections in one call; replay cache; start with 3 seeds |
| Invalid or unsafe LLM output | Schema + arbiter + TTL + fallback; safety lives in code |
| EV hallucination | Rule-based baseline A3 as fallback and comparison; reviewer logic in arbiter |
| Non-determinism | Temperature 0, fixed seeds, record/replay |
| Light demand hides effects | S1 peak scenarios; S0 only as regression |
| Pedestrian net breaks phase assumptions | Separate scenario; phase discovery; clearance transitions |
| Small local models fail at JSON | JSON/schema mode, retry once, track failure rate; use a stronger model for final runs if possible |
| Merge conflicts with teammates | Add files, don't edit stubs; small PRs; talk to owners of E1/S1 |
| LLM doesn't beat baselines | Report honestly; position as explainability + rare-event handling |

---

## 11. Open decisions (team)

1. **LLM provider and budget** (hosted API vs local model). This decides seeds and how big the pure-LLM arm can be.
2. **Slow-layer interval** (30 s proposed) and caps (TTL, `max_red_s`, hold limit). Tune after baselines.
3. **Pedestrian scope:** include Phase 5 or leave as future work?
4. **DQN timeline:** will it exist in time for A6, or is the fast layer max-pressure only?
5. **Who owns what:** align with the owners of `emergency_priority.py` (E1/E2) and `pedestrian_adaptive.py` (S1/S2).
6. Monaco: out of scope for this plan; the design is network-agnostic only if topology and phase discovery are used.

---

## 12. References

1. Lai et al. **LLMLight: Large Language Models as Traffic Signal Control Agents.** KDD 2025. arXiv:2312.16044. Code: github.com/usail-hkust/LLMTSCS
2. Yuan et al. **CoLLMLight: Cooperative Large Language Model Agents for Network-Wide Traffic Signal Control.** ICLR 2026. arXiv:2503.11739
3. Wang et al. **LLM-Assisted Light (LA-Light).** arXiv:2403.08337. Code: github.com/Traffic-Alpha/LLM-Assisted-Light
4. Pang et al. **iLLM-TSC: Integration reinforcement learning and large language model for traffic signal control policy improvement.** arXiv:2407.06025. Code: github.com/Traffic-Alpha/iLLM-TSC
5. Li et al. **REG-TSC: RAG-enhanced distributed LLM agents with emergency response for generalizable TSC.** arXiv:2510.26242
6. **TrafficGen: a multi-agent LLM orchestration for smart mobility and emergency corridor pre-emption.** PMC13627399 (seen via snippet only)
7. Choi & Lim. **Optimizing Traffic Signal Control Using LLM-Driven Reward Weight Adjustment in Reinforcement Learning.** JIPS 21(1), 2025. doi:10.3745/JIPS.04.0334
8. **SIGMA** (LLM interface turning operator instructions into reward functions). arXiv:2608.18263 (seen via snippet only)
9. Zhao, Cahill, Dusparic. **Balancing Multiple Objectives in Urban Traffic Control with RL from AI Feedback.** arXiv:2602.20728

---

## Appendix A: Operator system prompt skeleton

```
You are the Operator agent for a 3x3 grid of traffic signals. Each tick you receive a
JSON snapshot. Your job: reduce congestion network-wide and flag problems early.

Rules:
- You can only output directives of type "bias" or "hold". Nothing else.
- Never starve a direction: do not favor one direction for more than 60 s.
- If an EV corridor is active on the blackboard, do not bias against it.
- Prefer doing nothing over weak or speculative changes: {"directives": []} is valid.
- Output ONLY JSON matching this schema: <schema>. Keep "explanation" to 1-2 sentences.

Example input: <snapshot with a growing queue on B2->B1>
Example output: <envelope with a bias at B1, a hold at B2, and a spillback alert>
```

## Appendix B: Rule-based EV pre-emption (baseline A3)

For each EV, for each of its next 3 traffic lights: if ETA <= 20 s and the TLS is not already green for the EV's approach, issue `preempt(phase=EV approach, start_in_s=max(0, ETA - 15), hold_s=ETA + 8)`. Release after the EV passes the stop line. Runs through the same `DirectiveLayer`, so A3 and A4 share the safety and arbitration code.
