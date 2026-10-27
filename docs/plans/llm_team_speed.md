# LLM team port and speed plan

Status: Phase 3 done at `d922480`; Phase 4 next

Base: `integration` at `b908238`  
Working branch: `feat/llm-team-speed`  
Scope: port the three-role LLM team onto the integration backend and make it fast enough for tonight.

## 1. Scope

In scope:

- Port Operator, Emergency and Pedestrian agents.
- Port the supervisor, blackboard, arbiter, directive layer and directive schemas.
- Use the integration backend as the only environment: `CoTrafficEnv`, `Intersection`, safety shield, controller registry, evaluation runner and API.
- Use OpenCode Go only. Default model: `deepseek-v4.1-flash`.
- Speed first: reasoning mode, fewer calls, smaller prompts, parallel roles, metrics.
- Tunisia (`real_district`) first. Monaco is secondary and only a stress test.
- Keep the existing simple `llm` controller as a baseline arm.

Out of scope:

- Distilled student or any distillation work.
- Porting `max_pressure_v2` or the old `environment/` stack.
- RL work.
- Switching to Groq, Gemini or another provider.
- Rebuilding the frontend. Only expose `llm_team` through the existing policy/API contract.

## 2. Source material

Source branch: `feat/llm-agents` at `b83d77c`.

Port from:

- `agents/llm/agent.py`
- `agents/llm/schemas.py`
- `agents/llm/emergency_agent.py`
- `agents/llm/pedestrian_agent.py`
- `agents/llm/prompts/operator.md`
- `agents/llm/prompts/emergency.md`
- `agents/llm/prompts/pedestrian.md`
- `agents/supervisor/supervisor.py`
- `agents/supervisor/blackboard.py`
- `agents/supervisor/arbiter.py`
- `agents/supervisor/directive_layer.py`
- `environment/snapshot.py` as a reference for the snapshot format
- `tests/test_schemas.py`, `tests/test_arbiter.py`, `tests/test_directive_layer.py`, `tests/test_supervisor.py`
- `docs/ideate/llm-agents-plan.md` for the original design
- `docs/test/phase6/` for the original results

Do not port:

- `environment/traffic_light.py`, `environment/multi_agent_env.py`, `environment/topology.py`
- `agents/llm/client.py` as-is; write an adapter for the integration provider layer
- `evaluation/run_experiments.py`
- `agents/max_pressure.py`, `agents/max_pressure_v2.py`
- any scenario runner

The integration equivalent already covers those.

## 3. Locked decisions

- All three roles ship in the first port.
- No student, no distillation, no learned replacement for the LLM roles.
- OpenCode Go is the only LLM provider.
- Default model: `deepseek-v4.1-flash`.
- Reasoning policy: `none` for routine ticks, `low` on conflict, incident or congested ticks.
- Base controller: integration's `MaxPressure` plus the environment shield.
- Focus: grid3x3 and `real_district` (Tunisia). Monaco is a secondary stress test.
- Old `amen-integration-test` branch and stash are deleted. Do not recover them.
- Existing simple `llm` controller stays as the single-call baseline.

## 4. Why the old team was slow

Measured on the recorded Phase 6 runs:

- Monaco output: median 2,938 tokens per call; visible JSON only about 194 tokens.
- Hidden reasoning: about 2,726 tokens per call, 93 percent of output.
- Monaco latency correlation: 0.90 with output tokens, 0.05 with input tokens.
- Monaco calls per seed: 279 to 289 Emergency plus 66 Operator.
- Only 44 to 51 Emergency calls introduced a new `(EV, TLS)` pair, 15 to 18 percent.
- 82 to 85 percent of Emergency calls were redundant refreshes.
- Monaco input: median about 32k tokens per call; blackboard about 20 percent.
- Grid runs with reasoning off: Operator about 2.3 s, Emergency about 7.3 s.

Conclusion: reasoning tokens dominate latency, and schedule persistence plus event coalescing removes most Monaco calls.

## 5. Target architecture

```
CoTrafficEnv (SUMO, shield, Intersection)
        |
        +-- MaxPressure (base action)
        |
        +-- LLMTeamController.act(env, obs)
                |
                +-- Supervisor (cadence, events, blackboard)
                |      +-- Operator
                |      +-- Emergency
                |      +-- Pedestrian
                |
                +-- Arbiter (validate, clip, resolve)
                +-- DirectiveLayer (active windows, bias, hold, preempt, serve_ped)
                |
                +-- requested phase actions
                        |
                    CoTrafficEnv shield
```

The LLM layer only proposes typed directives. It never touches TraCI. The environment shield remains the last safety layer.

## 6. Source to target map

| Source | Target |
|---|---|
| `agents/llm/agent.py` | `src/cotraffic/controllers/llm_team/agent.py` |
| `agents/llm/schemas.py` | `src/cotraffic/controllers/llm_team/schemas.py` |
| `agents/llm/emergency_agent.py` | `src/cotraffic/controllers/llm_team/roles/emergency.py` |
| `agents/llm/pedestrian_agent.py` | `src/cotraffic/controllers/llm_team/roles/pedestrian.py` |
| Operator role from `agents/llm/agent.py` plus prompts | `src/cotraffic/controllers/llm_team/roles/operator.py` |
| `agents/supervisor/*` | `src/cotraffic/controllers/llm_team/` |
| `environment/snapshot.py` | `src/cotraffic/controllers/llm_team/snapshot.py`, adapted to `CoTrafficEnv` |
| `agents/llm/client.py` | adapter over `src/cotraffic/llm/providers.py` |
| prompts | `src/cotraffic/controllers/llm_team/prompts/` |

## 7. Integration-specific adaptation

The old directive layer assumes grouped axis actions (`NS` and `EW` groups, with `group_phases` and `Group` state). Integration uses one action per green phase from `Intersection.green_states`, and `MaxPressure` uses `phase_pressures`.

Required adaptation:

- Build a per-TLS `state` dict for the supervisor from `env.intersections`, `env.meas`, `env.ev_ids`, `env.ev_info`, `env.ped_waiting` and `env.crossing_owner`.
- Resolve `NS` or `EW` plus an optional `phase_index` to an integration phase index.
- Use `phase_for(inter, link_index)` from `src/cotraffic/controllers/ev_preemption.py` for the exact EV approach phase.
- Use `approaching()` from the same module for EV distance and link.
- Use `longest_waits()` from `src/cotraffic/controllers/pedestrian_rule.py` for pedestrian requests.
- Return requested phase actions. Do not implement min green, yellow or starvation in the controller. The environment shield and `Intersection` already do that.
- Do not hardcode grid size, TLS IDs or "3x3" in prompts. Pass the network name and TLS list in the user message.
- Instantiate all three roles, but skip Emergency when no EV is active and skip Pedestrian when no pedestrian is waiting.
- `needs_observations = False` for `LLMTeamController`; it reads the environment directly.

## 8. Speed plan

### 8.1 Reasoning mode

- Add `reasoning_effort` to the OpenCode Go provider.
- Routine Operator and Pedestrian ticks: `reasoning_effort: "none"`.
- Emergency, conflict, incident and congested ticks: `reasoning_effort: "low"`.
- Parse `completion_tokens_details.reasoning_tokens` when the provider returns it.
- If the Go proxy ignores `reasoning_effort`, test the DeepSeek `thinking` toggle or a non-reasoning Go model. Do not change provider.

### 8.2 Schedule persistence and event coalescing

- Persist the Emergency schedule per `(EV, TLS)`.
- Do not re-plan an existing window on every tick.
- Call Emergency only when:
  - a new EV enters the relevant horizon,
  - a new `(EV, TLS)` pair appears,
  - a conflict appears,
  - the corridor changes,
  - an incident affects the corridor.
- Compute releases and extensions in code.
- Debounce EV events. Target: 3 to 5 s.
- Target: no more than 50 calls per seed on Tunisia and Monaco.

### 8.3 Prompt compaction

- Deduplicate blackboard messages. The old snapshot and context both carried them.
- Cap active blackboard messages and alerts.
- Hot-EV filter: only EVs within a 25 to 60 s ETA horizon.
- Per EV, include only the next 2 to 3 TLS.
- Operator prompt: EV summary plus affected corridors.
- Emergency prompt: detailed corridor view.
- Compact keys where possible.
- Target: no more than 8k input tokens per call.

### 8.4 Parallel roles

- When more than one role is due at the same tick, run the calls concurrently with `ThreadPoolExecutor`, max 2 or 3 workers.
- Apply results in a fixed order: Operator, Emergency, Pedestrian.
- Protect the replay cache with a lock.
- Keep `--jobs 1` for LLM experiments. Parallelize roles inside a run, not runs.

### 8.5 Output and caching

- Strict JSON schema.
- Per-role `max_tokens`: Operator 300, Pedestrian 300, Emergency 500.
- Keep the system prompt byte-stable for prefix caching.
- Version replay caches after prompt changes.

### 8.6 Metrics

Add per-role metrics to `LLMTeamController.metrics()`:

- calls
- latency mean, p50, p90
- tokens in, out, reasoning, cached
- retries
- fallbacks
- skipped calls
- wall time
- estimated cost

The evaluation runner already merges `controller.metrics()` into the result row.

## 9. Phases and acceptance

### Phase 0: setup

Done in this branch:

- clean branch from `integration`
- old stash and old branch removed
- this plan committed

### Phase 1: port core (done at `ad5a8b3`)

- Add the `llm_team` package, OpenCode Go provider, Mock and Replay providers.
- Register `llm_team`.
- Add config and tests.
- Adapt the snapshot and action mapping.

Acceptance:

- `pytest tests -q` passes.
- A mock run on grid2x2 and grid3x3 completes with no API calls.
- `llm_team` is selectable through the registry and API policy.
- No TraCI in the LLM package.

Evidence recorded on `ad5a8b3`:

- `pytest tests -q`: 108 passed.
- `llm_team_ab_quick` with `COTRAFFIC_LLM_BACKEND=mock`: 4 of 4 runs passed, grid2x2 and grid3x3, 0 API calls.
- Extra mock smoke runs completed for `emergency` and `pedestrians` on grid3x3.
- `llm_team` is in `METHODS`, the API catalog and the registry.
- The package has no `import traci` or `from traci`.

Phase 1 deviations and additions:

- Added `src/cotraffic/envs/ev.py` and `env.ev_states` so per-EV corridors stay out of the LLM package.
- Added lane waiting time to `Measurements` and pedestrian wait sums to `CoTrafficEnv`.
- Ported `detector.py` for supervisor alerts.
- Added `llm_team_ab_quick.yaml`, `tests/conftest.py` and `tests/test_llm_team_roles.py`.
- `requirements-dev.txt` now uses `httpx2` for the Starlette TestClient.
- The local `~/.venvs/sumo` install is not editable, so CLI runs need `PYTHONPATH=src`.

Phase 1 speed baseline (mock, 600 s quick episodes):

- grid3x3 normal: 20 Operator calls.
- grid3x3 emergency: 69 calls, 29 Emergency.
- grid3x3 pedestrians: 159 calls, 113 Pedestrian. This is the main Phase 2 coalescing target.

### Phase 2: speed (done)

Delivered:

- Emergency schedule persistence per `(EV, TLS)`; `EmergencyAgent.maintain()` extends, shrinks and releases windows in code between LLM calls.
- Event-driven Emergency cadence with a 60 s safety replan; `(EV, TLS)` changes and conflicting EV phases trigger off-cadence calls.
- Pedestrian event coalescing: threshold crossings only, 20 s global gap, 30 s per-TLS gap.
- Operator congestion is decoupled from pedestrian waits and blackboard agent alerts.
- Prompt compaction: one blackboard copy, capped messages and alerts, hot-EV filter (60 s horizon), three TLS per EV, role-specific snapshot views.
- Parallel role calls with `ThreadPoolExecutor` and fixed apply order Operator, Emergency, Pedestrian.
- Thread-local provider usage so concurrent calls cannot misattribute tokens.
- Per-role and aggregate latency mean/p50/p90, skipped calls, code updates, releases, wall time and estimated cost in `metrics()`.
- Replay cache version bumped to 2 after the prompt changes.

Phase 2 evidence:

- `pytest tests -q`: 119 passed.
- `ruff check` on the LLM team and provider files: clean.
- `llm_team_ab_quick` with the mock backend: 4 of 4 runs passed, 20 calls on grid2x2 and grid3x3 normal.
- Mock `llm_team_speed`, grid3x3, seed 0, 600 s episodes:
  - normal: 20 Operator calls, 0 fallbacks.
  - incident: 20 Operator calls, 0 fallbacks.
  - emergency: 42 calls, 28 Operator and 14 Emergency, 44 code updates, 14 releases, 0 fallbacks.
  - pedestrians: 48 calls, 21 Operator and 27 Pedestrian, 0 fallbacks.
  - Every grid3x3 cell is at or below the 50-call target.
- Mock KPIs:
  - normal and incident match Max-Pressure exactly.
  - emergency EV travel time 110.3 s to 81.3 s and EV delay 42.8 s to 13.7 s; mean car travel time 118.8 s to 120.0 s.
  - pedestrians mean wait 20.2 s to 13.8 s and p95 wait 120 s to 91 s; mean car travel time 123.6 s to 124.2 s.
- One real grid3x3 normal seed with `COTRAFFIC_LLM_MAX_CALLS=60`:
  - 21 Operator calls, 0 retries, 0 fallbacks, 0 reasoning tokens.
  - 45,840 input tokens, about 2.2k per call; 1,448 output tokens; 14,336 cached tokens.
  - Wall time 43.6 s; latency mean 1.99 s, p50 2.01 s, p90 2.60 s.
- Strict replay of that seed: same 21 calls and token totals, 0 fallbacks, 1.5 s simulation wall.

Deviations from the first draft:

- `pedestrian_interval_s` is 60, not 30, to meet the call target; threshold events still fire at 20 s of wait.
- `congested_delta_s` is 20, not 15.
- `ev_eta_thresholds` is empty by default; the schedule is maintained in code instead of replanning on ETA steps.
- Pricing defaults to 0, so `llm_team_estimated_cost_usd` reports 0 until the `pricing` block is filled.

Phase 2 acceptance: met.

Phase 2 preflight:

- Verify the OpenCode key in `.env`.
- The controller reads `COTRAFFIC_LLM_MAX_CALLS` and `COTRAFFIC_LLM_TIMEOUT`; the legacy `LLM_MAX_CALLS` and `LLM_TIMEOUT_S` names are not read yet.
- Start with mock, then one tiny real call, then one real seed.
- Inspect the decision log and metrics before running more seeds.

### Phase 3: Tunisia (done)

- Run `real_district` normal, emergency and incident.
- Compare `max_pressure`, simple `llm` and `llm_team`.

Acceptance:

- Runs complete without crashes.
- Wall time target: under 5 minutes per seed fresh.
- Replay under 10 seconds.
- Report honest metrics.

Phase 3 evidence:

- Config: `configs/experiments/llm_team_tunisia.yaml`, seeds 0 to 2, medium demand,
  normal, emergency and incident, `ssm: true`.
- `real_district` built with 7 signalised TLS. All green phases map to a valid NS or
  EW axis and every EV approach link resolves to a valid phase. One junction has 3
  green phases and is handled as two NS groups plus one EW group.
- `pytest tests -q`: 121 passed at `d922480`.
- Full mock matrix: 18 runs for `mp` and `llm_team`, 0 failed, 91 to 110 team calls
  per full episode.
- Real matrix: 27 runs, 0 failed. Team results were frozen at `9336ec8-dirty` after
  the `max_tokens` change; the committed config is `d4a7038` and matches the run.
  All simple `llm` runs are at `d922480`.

Team totals across 9 runs:

- 869 calls, 843 Operator and 26 Emergency, 4 fallbacks and 8 retries.
- 1,789,277 input tokens, 68,622 output tokens, 1,277,440 cached and 13,260
  reasoning tokens.
- Fresh wall time 158.8 to 215.4 s per run. One emergency seed reused probe cache and
  reports 16.0 s; its separate fresh probe took 223.4 s. Both are below 5 minutes.
- Strict replay: 8.0 to 9.1 s per run, 76.3 s for all 9 runs. Calls, tokens and every
  KPI match the fresh rows exactly. The 4 original provider failures reproduce as
  strict replay cache misses, so replay also has 4 fallbacks.

Simple `llm` totals across 9 runs:

- 1,620 calls, 1,620 successful, 1 partial decision, 0 fallbacks.
- 1,493,458 prompt tokens and 30,805 completion tokens.
- Fresh wall time 264.0 to 277.5 s per run.

Mean KPIs over 3 seeds:

| scenario | method | travel s | wait s | throughput/h | EV travel s | EV delay s |
|---|---|---:|---:|---:|---:|---:|
| normal | mp | 109.27 | 8.86 | 3719 | | |
| normal | llm | 119.42 | 16.36 | 3721 | | |
| normal | llm_team | 109.01 | 8.65 | 3720 | | |
| emergency | mp | 109.46 | 9.01 | 3723 | 91.57 | 22.36 |
| emergency | llm | 118.27 | 15.40 | 3732 | 98.12 | 28.71 |
| emergency | llm_team | 108.90 | 8.61 | 3728 | 90.99 | 21.87 |
| incident | mp | 109.18 | 8.97 | 3719 | | |
| incident | llm | 119.52 | 16.45 | 3718 | | |
| incident | llm_team | 108.77 | 8.65 | 3719 | | |

Findings:

- `llm_team` matches or slightly beats Max-Pressure on all three scenarios. The gain is
  small and not robust. It wins all 3 normal seeds and 2 of 3 incident seeds. The
  emergency EV delay is 15.05 s against 23.11 s on seed 0, then 21.61 s against
  17.33 s on seed 1 and 28.94 s against 26.65 s on seed 2.
- No paired comparison is statistically significant with 3 seeds. Treat these as
  exploratory differences, not confirmed effects.
- Simple `llm` is consistently worse than Max-Pressure on travel time and waiting time.
  Its throughput is unchanged, so the extra delay is not from lost demand.
- Safety: `llm_team` had 0 collisions and 0 teleports in all 9 runs. `mp` and simple
  `llm` each recorded one collision and one teleport in one normal and one emergency
  run.
- The team's 4 fallbacks are on low-effort emergency ticks. Raising `max_tokens` from
  300/500/300 to 600/900/500 cut failures from 13 to 4. Further reruns were stopped to
  avoid more paid calls, so the frozen v2 rows keep those 4 fallbacks.
- Simple `llm` needed a separate fix: it now requests `reasoning_effort: none` and
  validates phases against each intersection's real phase count instead of the padded
  action space. Before the fix it produced empty or truncated responses on 7 of 23
  calls.

Phase 3 acceptance: met, with the 4 team fallbacks and the replay cache misses
reported above.

### Phase 4: Monaco stress test

- One seed only.
- Check calls, input tokens, wall time and fallbacks.

Acceptance:

- Target: under 10 minutes per seed fresh, no more than 50 calls, no more than 8k input tokens per call.
- If the target is missed, record the bottleneck instead of hiding it.

Phase 3 measured 91 to 110 team calls per full `real_district` episode, so Monaco
will likely miss the 50-call target unless the cadence or event coalescing changes.
Record the miss or reduce calls before the run.

### Phase 5: expose

- Add `llm_team` to the API policy catalog and labels.
- Add the metrics to the evaluation export.
- Keep the frontend work minimal until the backend is stable.

## 10. Files

Add:

```
src/cotraffic/controllers/llm_team/
  __init__.py
  controller.py
  snapshot.py
  supervisor.py
  blackboard.py
  arbiter.py
  directive_layer.py
  detector.py
  schemas.py
  agent.py
  client.py
  roles/__init__.py
  roles/operator.py
  roles/emergency.py
  roles/pedestrian.py
  prompts/operator.md
  prompts/emergency.md
  prompts/pedestrian.md
src/cotraffic/envs/ev.py
configs/agents/llm_team.yaml
configs/experiments/llm_team_ab.yaml
configs/experiments/llm_team_ab_quick.yaml
configs/experiments/llm_team_speed.yaml
configs/experiments/llm_team_tunisia.yaml
tests/conftest.py
tests/test_llm_team_schemas.py
tests/test_llm_team_arbiter.py
tests/test_llm_team_directive_layer.py
tests/test_llm_team_supervisor.py
tests/test_llm_team_controller.py
tests/test_llm_team_roles.py
```

Modify:

```
src/cotraffic/llm/providers.py
src/cotraffic/controllers/llm.py
src/cotraffic/controllers/registry.py
src/cotraffic/envs/observations.py
src/cotraffic/envs/traffic_env.py
configs/agents/llm.yaml
api/policy.py
configs/dashboard_policy.yaml
requirements-dev.txt
.env.example
tests/test_llm_controller.py
```

## 11. Runbook

The local venv is not editable, so prefix CLI commands with `PYTHONPATH=src`.

```bash
PYTHONPATH=src ~/.venvs/sumo/bin/python -m pytest tests -q
```

Mock run:

```bash
PYTHONPATH=src COTRAFFIC_LLM_BACKEND=mock \
~/.venvs/sumo/bin/python -m cotraffic evaluate \
  --experiment llm_team_ab_quick --jobs 1 --force
```

Mock speed matrix (normal, emergency, incident, pedestrians):

```bash
PYTHONPATH=src COTRAFFIC_LLM_BACKEND=mock \
~/.venvs/sumo/bin/python -m cotraffic evaluate \
  --experiment llm_team_speed --jobs 1 --force
```

One real seed, with a hard call guard:

```bash
PYTHONPATH=src \
COTRAFFIC_LLM_BACKEND=opencode \
COTRAFFIC_LLM_PROVIDER=opencode \
COTRAFFIC_LLM_BASE_URL=https://opencode.ai/zen/go/v1 \
COTRAFFIC_LLM_MODEL=deepseek-v4.1-flash \
COTRAFFIC_LLM_MAX_CALLS=60 \
~/.venvs/sumo/bin/python -m cotraffic evaluate \
  --experiment llm_team_ab_quick --jobs 1
```

Strict replay:

```bash
PYTHONPATH=src COTRAFFIC_LLM_BACKEND=replay \
~/.venvs/sumo/bin/python -m cotraffic evaluate \
  --experiment llm_team_ab_quick --jobs 1
```

Legacy `.env` note: the OpenCode provider reads `LLM_API_KEY`, `LLM_BASE_URL`,
`LLM_MODEL` and `LLM_EXTRA_HEADERS` when the `COTRAFFIC_LLM_*` names are absent.
The controller does not yet read legacy `LLM_MAX_CALLS` or `LLM_TIMEOUT_S`;
use the `COTRAFFIC_*` names for those.

Rules:

- API key stays in `.env` and is never committed.
- Mock and replay first. Never start a paid batch blind.
- One real seed, inspect the log, then replay.
- Only then run 2 or 3 seeds.
- Do not run two SUMO batches concurrently.
- Use `--jobs 1` for any LLM run.

## 12. Risks

- The Go proxy may drop `reasoning_effort`. Verify with usage counters.
- Schedule persistence can keep stale windows. The reviewer and shield must bound it.
- Prompt pruning can change decisions. Version the caches.
- Action mapping between axis groups and integration phase indices is the main correctness risk.
- Parallel role calls can hit rate limits. Keep workers configurable.
- `real_district` does not support pedestrians. Do not run pedestrian scenarios there.
- Old caches are invalid after prompt or model changes.

## 13. Fresh session start

Read this file first. Phase 3 is done; implement Phase 4 only.

Start from `d922480` on `feat/llm-team-speed`. Do not redo Phases 1 to 3.

Rules:

- All three roles.
- No student.
- No MP v2 port.
- No provider other than OpenCode Go.
- Use integration's environment, shield, registry and metrics.
- Keep code compact and comments limited.
- No em dashes in code, docs or commit messages.
- Mock and replay before any real seed.
- Use `--jobs 1` for every LLM run.
- Do not run two SUMO batches concurrently.
- Run `pytest tests -q` and the mock matrix before spending tokens.
- One real seed, inspect calls/tokens/fallbacks, then replay.

Phase 4 first steps:

1. Run Monaco on one seed with `llm_team` and a call guard, using `--jobs 1`.
2. Mock and replay first. Do not start a paid Monaco run blind.
3. Check fresh wall time, calls, input tokens per call and fallbacks.
4. Target: under 10 minutes fresh, no more than 50 calls, no more than 8k input
   tokens per call. Phase 3 measured 91 to 110 calls per full episode, so expect the
   call target to need a cadence change or an honest miss.
5. Record the bottleneck and commit only after tests and mock pass.
