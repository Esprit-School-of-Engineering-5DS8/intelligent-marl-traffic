# LLM team integration plan

Status: proposed
Target branch: `integration`
Source: `origin/feat/llm-team-speed` (Amen), which has **no merge base** with `integration`
so the code must be ported file by file, never merged.

## 1. Goal

Add Amen's `llm_team` controller (Operator + Emergency + Pedestrian roles on top of
Max-Pressure, with a code arbiter and directive layer) as a **fourth runtime controller**
next to `mp`, `llm` and the RL checkpoints, **without** breaking the existing Groq and
Gemini paths.

Deliverables:

- `llm_team` selectable from the dashboard policy, runnable live and in benchmarks.
- Provider choice is a setting: `groq`, `gemini`, or `opencode` (OpenCode Go).
- Mock and replay backends so the team can be developed and tested for free.
- Metrics (calls, tokens, latency, cost, fallbacks) visible in the UI.
- `llm` (single-call) stays as the baseline arm.

## 2. What exists today vs what the port assumes

| Piece | `integration` (ours) | `feat/llm-team-speed` (theirs) | Action |
|---|---|---|---|
| Providers | Groq, Gemini. `LLMResult` has prompt/completion tokens only | adds `OpenCodeGoProvider`, `cached_tokens`, `reasoning_tokens`, thread-local `reasoning_effort`, `provider_available()` | extend ours, keep both old providers |
| `chat_json` signature | `(messages, schema, max_tokens)` | `(messages, schema, max_tokens, effort)` | add optional `effort`, default `None` |
| Registry | `LLM = ("llm",)` | `LLM = ("llm", "llm_team")` | add method + factory branch |
| Policy | `_llm_ready()` no args, groq/gemini only | `_llm_ready(method)`, opencode aware | make it per-method and provider-aware |
| Env | `ev_ids`, `ev_info`, `ped_waiting`, `crossing_owner`, `neighbour_links`, `meas` | needs `ev_states` (new `envs/ev.py`), `meas.waiting`, `ped_wait_sum` | add three things |
| Live wiring | `make_controller(method, checkpoint)` | same shape | no change needed |
| Network names | `tunis` (city-scale), `sf_mission_2x2/3x3` | `real_district`, `grid2x2/3x3` | rename in ported configs |
| Frontend | `usePolicy`/`useUpdatePolicy` exist but **no React consumer**; the vanilla shell reads `/api/policy` | vanilla shell selector + LLM monitor page | build a small React picker + monitor |
| Tests | none for the team | 6 files, ~89 test functions | port and adapt |

## 3. Decisions

1. **Provider layer, not a fork.** Amen's branch forces OpenCode Go. We add OpenCode as a
   third provider and keep `groq` as the default so the feature works on a machine that
   only has `GROQ_API_KEY`. Selection order:
   `COTRAFFIC_LLM_PROVIDER` env → agent YAML `provider` → default `groq`.
2. **Backend is explicit**, not implied: `COTRAFFIC_LLM_BACKEND` = `mock` | `replay` |
   `provider` (default `provider`). Tests and CI run `mock`; no key required.
3. **LLM is a controller, not a training target.** The Training page's "Full LLM" card
   becomes a launcher for a live/evaluation run; it never submits a training job.
4. **Port the team package verbatim where possible**, changing only imports, config
   loading, network names and the client factory. Extra rewrites make future diffs
   against Amen's branch unreadable.
5. **Keep our tracer.** `LLMTracer` / `COTRAFFIC_LLM_TRACE` stays; the team's own call
   logger is additive.
6. **No distillation, no student model, no Monaco** in this pass.

## 4. Phases

Each phase ends with a gate. Do not start the next phase until the gate passes.

### Phase 1 — Provider layer (OpenCode Go + reasoning/cache accounting)

Files:

- `src/cotraffic/llm/providers.py`
  - `LLMResult`: add `cached_tokens: int | None = None`, `reasoning_tokens: int | None = None`.
  - `BaseProvider`: thread-local `reasoning_effort` property, `chat_json(..., effort=None)`;
    pass `effort` to `_complete`.
  - New `OpenCodeGoProvider`: default base URL `https://opencode.ai/zen/go/v1`, key from
    `COTRAFFIC_LLM_API_KEY` / `OPENCODE_API_KEY` / `LLM_API_KEY`, default model
    `deepseek-v4.1-flash`, `reasoning_effort` in the payload, retry once without it on
    HTTP 400, parse `prompt_tokens_details.cached_tokens` and
    `completion_tokens_details.reasoning_tokens`.
  - `make_provider`: accept `opencode` / `opencode-go`; keep `groq` and `gemini` untouched.
  - `provider_available(name) -> (bool, reason)` for the policy layer.
- `.env.example`: document the new variables (see §6).
- `tests/test_llm_providers.py`: port, plus a regression test that Groq and Gemini still
  construct and still return the old `LLMResult` shape with `None` for the new fields.

Gate:

- `pytest tests/test_llm_controller.py tests/test_llm_providers.py -q` green.
- `python -m cotraffic evaluate --experiment quick` still runs with an LLM cell on Groq.

### Phase 2 — Environment support

Files:

- `src/cotraffic/envs/ev.py` (new, copied): `EVState`, `UpcomingTLS`, `read_ev_states(conn, ev_ids)`.
- `src/cotraffic/envs/traffic_env.py`
  - Maintain `self.ev_states` each step from `read_ev_states(conn, self.ev_ids)`
    (`ev_ids` and `ev_info` already exist, so this is additive).
  - Add `self.ped_wait_sum: dict[str, float]` per crossing (accumulated wait), alongside
    the existing `ped_waiting`.
  - Confirm `neighbour_links` shape matches the port's expectation: ours is
    `{tid: {side: (link_id, lanes, phases)}}` and the port reads `link[0]` — compatible.
- `src/cotraffic/envs/observations.py`
  - `Measurements` has no `waiting` map; the port's snapshot reads it. Add
    `self.waiting` filled in `refresh()` from `getLastStepVehicleIDs` +
    `getAccumulatedWaitingTime`, or (cheaper) from the lane's waiting-time getter if the
    libsumo build exposes it. Keep the cost per step bounded; measure before merging.

Gate:

- A script builds phase maps + one snapshot on `sf_mission_3x3` and dumps JSON; no crash
  and < 5 ms per snapshot.
- No `import traci` anywhere under `controllers/llm_team/`.

### Phase 3 — Port the team package

Copy from the source branch into `src/cotraffic/controllers/llm_team/`:
`controller.py`, `supervisor.py`, `arbiter.py`, `directive_layer.py`, `blackboard.py`,
`client.py`, `detector.py`, `schemas.py`, `snapshot.py`, `agent.py`,
`roles/{operator,emergency,pedestrian}.py`, `prompts/*.md`.

Adaptation points:

- `client.py`: keep the `TeamClient` protocol; construct the inner client through our
  `make_provider` so `groq`/`gemini`/`opencode` all work. `backend` mapping:
  `mock` → `MockClient`, `replay` → strict `ReplayClient`, anything else → read-through
  `ReplayClient` over the real provider when a cache path is configured.
- `controller.py`: `config.load_agent("llm_team")` works with our `config` module.
- Remove the OpenCode-only assumptions from defaults; provider comes from config/env.
- Add `configs/agents/llm_team.yaml` with our defaults:
  `provider: groq`, `backend: provider`, per-role token caps, supervisor cadence block,
  pricing block (0 by default).
- Port the six test files; update imports and the `real_district` references.

Gate:

- `pytest tests -q` green (existing 121 + the new team tests).
- `COTRAFFIC_LLM_BACKEND=mock python -m cotraffic evaluate --experiment llm_team_ab_quick --jobs 1 --force`
  completes on `sf_mission_2x2` and `sf_mission_3x3` with 0 API calls.
- Axis mapping check: for every controlled TLS on `sf_mission_3x3`, `tunis` and `monaco`,
  print phase → axis and confirm each green phase resolves to `NS` or `EW` and every EV
  approach link maps to a valid phase. This is the main correctness risk in the port.

### Phase 4 — Configs and experiment cells

- `configs/experiments/llm_team_ab.yaml`, `llm_team_ab_quick.yaml`,
  `llm_team_speed.yaml`, `llm_team_tunisia.yaml`: replace `real_district` with `tunis`
  and `grid2x2/3x3` with `sf_mission_2x2/sf_mission_3x3` where those are scenario ids.
- Keep `methods: [mp, llm, llm_team]` so the single-call baseline is always in the same
  cell (paired comparison).
- `llm_team_tunisia.yaml`: seeds `[0,1,2]`, medium demand, `normal`/`emergency`/`incident`.

Gate: `python -m cotraffic evaluate --experiment llm_team_ab_quick --jobs 1` resolves all
cells (mock run).

### Phase 5 — Registry, policy, API

- `src/cotraffic/controllers/registry.py`: `LLM = ("llm", "llm_team")` + factory branch.
- `api/policy.py`:
  - `LABELS["llm_team"] = "LLM team"`.
  - `_llm_ready(method)`: `llm_team` checks the configured provider (groq/gemini/opencode)
    and short-circuits to ready when the backend is `mock`/`replay`.
  - `availability()` passes the method; a missing key still yields `available=True` with
    the existing "falls back to Max-Pressure" warning.
  - Catalog entries gain `provider` and `backend` so the UI can label the cost model.
- `api/simulation.py`: no structural change; confirm `make_controller("llm_team")` builds
  and that the live cap (`COTRAFFIC_LLM_MAX_CALLS`, default 80) is applied.

Gate:

- `GET /api/policy` lists `llm_team` with provider/backend.
- `PUT /api/policy {"method":"llm_team","network":"sf_mission_3x3"}` → 200.
- `POST /api/simulation/start` with that policy produces `calls`/`fallbacks` in
  `/api/simulation/state` and stops cleanly.

### Phase 6 — Frontend

- `frontend/src/shared/api/policy.ts`: add `provider`/`backend` to the schema.
- New policy picker component (React; nothing consumes `usePolicy` today) used by the
  Live Map and the Training page: method list, availability badge, paid-call
  confirmation for `llm`/`llm_team`, and a calls/cap badge during a run.
- Training page: replace the disabled "Full LLM" card with a launcher that starts a live
  or benchmark run with `method: llm_team` instead of a training job.
- Benchmark: render the team metrics columns from the exported rows (calls, fallbacks,
  retries, tokens in/out/cached/reasoning, latency, cost).

Gate: `npx tsc --noEmit` clean for touched files, `npm run build` passes, and a mock live
run can be started/stopped from the UI.

### Phase 7 — Evaluation and reporting

Run order (no shortcuts):

1. Mock matrix on all SF cells.
2. One real seed per provider (`groq`, then `opencode`), inspecting calls/tokens/fallbacks.
3. Strict replay of that seed; the KPI row must match exactly.
4. Three seeds per cell for the report.
5. `--jobs 1` for every LLM run; never two SUMO batches at once.

Report table: `mp`, `llm`, `llm_team` × scenario × metric, with seed count and intervals.
Include the peak-demand cell **even though it is negative**.

Honest framing to use in the report: the team is a large improvement over our single-call
`llm` (their Tunisia numbers: 119 s vs 109 s travel time), roughly equal to Max-Pressure at
medium demand, and **worse than Max-Pressure at peak** (182 s vs 167 s travel, EV delay
136 s vs 104 s). Its genuine win is safety: 0 collisions and 0 teleports across their nine
runs where `mp` and `llm` each had one collision and one teleport.

## 5. File map

Add:

```
src/cotraffic/controllers/llm_team/           (12 modules + 3 prompts)
src/cotraffic/envs/ev.py
configs/agents/llm_team.yaml
configs/experiments/llm_team_ab.yaml
configs/experiments/llm_team_ab_quick.yaml
configs/experiments/llm_team_speed.yaml
configs/experiments/llm_team_tunisia.yaml
tests/test_llm_providers.py
tests/test_llm_team_{schemas,arbiter,directive_layer,supervisor,controller,roles}.py
frontend/src/features/<policy picker component>
```

Modify:

```
src/cotraffic/llm/providers.py
src/cotraffic/envs/traffic_env.py
src/cotraffic/envs/observations.py
src/cotraffic/controllers/registry.py
api/policy.py
api/simulation.py            (only if the live cap needs plumbing)
frontend/src/shared/api/policy.ts
frontend/src/features/training/TrainingPage.tsx
frontend/src/features/analytics/...   (team metric columns)
.env.example
tests/test_llm_controller.py          (no behaviour change expected)
```

## 6. Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `COTRAFFIC_LLM_PROVIDER` | `groq` \| `gemini` \| `opencode` | `groq` |
| `COTRAFFIC_LLM_MODEL` | model id for the chosen provider | provider default |
| `COTRAFFIC_LLM_BACKEND` | `provider` \| `mock` \| `replay` | `provider` |
| `COTRAFFIC_LLM_API_KEY` / `OPENCODE_API_KEY` | OpenCode Go key | — |
| `COTRAFFIC_LLM_BASE_URL` | OpenCode-compatible base URL | `https://opencode.ai/zen/go/v1` |
| `COTRAFFIC_LLM_MAX_CALLS` | per-episode / live call cap | 80 for live, 0 (unlimited) in eval |
| `COTRAFFIC_LLM_TIMEOUT`, `..._ATTEMPTS` | already used by our controller | 30 s, 2 |
| `GROQ_API_KEY`, `GEMINI_API_KEY` | unchanged | — |
| `COTRAFFIC_LLM_TRACE` | our tracer, unchanged | on |

## 7. Risks

| Risk | Mitigation |
|---|---|
| No merge base: a `git merge` would be meaningless | port by file, keep the package close to the source so diffs stay reviewable |
| Axis/phase mapping (`NS`/`EW` + `phase_index`) is the main correctness risk, especially Tunis with 6-phase junctions | Phase 3 gate script that prints every phase's axis; refuse to run a network where a green phase has no axis |
| `Measurements.waiting` does not exist yet and can be expensive per step | measure the cost; if too slow, derive waits only for lanes on controlled approaches |
| Parallel role calls + provider state | providers must use thread-local `reasoning_effort`; replay cache needs the existing lock (it has one) |
| Gemini has no `reasoning_effort` | pass `effort` only to opencode/groq; Gemini ignores it |
| Prompt changes invalidate the replay cache | bump `CACHE_VERSION` whenever a prompt or schema changes |
| Cost blow-up | mock by default in tests, live cap 80 calls, one real seed before any batch, `--jobs 1` |
| Our `tunis` is not their `real_district` | re-run the axis check and calibrate demand before comparing numbers with their report |

## 8. Effort

| Phase | Estimate |
|---|---|
| 1 provider layer | 0.5 day |
| 2 env support | 1 day |
| 3 port + tests | 1.5–2 days |
| 4 configs | 0.5 day |
| 5 registry/policy/API | 0.5 day |
| 6 frontend | 1 day |
| 7 evaluation | 1 day + API budget |

Total: roughly 5–6 focused days, plus paid runs.

## 9. Definition of done

- `llm_team` runs on `sf_mission_2x2`, `sf_mission_3x3` and `tunis` with all three
  providers selectable and mock/replay working without a key.
- `pytest tests -q` green, including the ported team tests.
- Dashboard can select, start, watch and stop an `llm_team` live run; the LLM monitor
  shows calls, tokens, latency, fallbacks and cost.
- A results table exists with `mp`, `llm`, `llm_team` on paired seeds, including the
  peak-demand cell and its negative result.
- `llm` (single-call) still works on Groq and Gemini, unchanged.
