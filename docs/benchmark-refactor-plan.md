# Benchmark Platform: Detailed Product and Implementation Plan

**Status:** planning only; no implementation changes are included in this document.

**Purpose:** replace the current fragmented training/model/run experience with one understandable lifecycle: **train a policy → keep a reusable model → benchmark saved models under the same conditions → inspect plots, metrics, and evidence.**

This is a product plan, not a proposal to install MLflow. Keep the existing React/FastAPI/SUMO stack and use MLflow only as a mental model for experiment lineage where it helps.

---

## 1. User goal and design principles

The user should think in terms of **complete traffic-control policies**, not one agent per turn, intersection, or special formula. A model is one learned policy, with its training recipe, weights, supported network/observation shape, and evaluation history attached. A SUMO simulation episode remains a lower-level record, not the primary thing the user has to navigate.

1. **One generalist by default.** Train one parameter-shared policy for all controlled intersections and the selected range of demand/event conditions. Do not present scenario-specific policies as the normal product unless the user explicitly chooses that experiment.
2. **Training and evaluation are different.** Training curves show learning progress; held-out benchmark episodes measure performance. Never label the training reward as benchmark performance.
3. **Reproducibility before verdicts.** Record recipe/config hash, software/runtime versions, network version, random seeds, demand, event conditions, timestep count, checkpoint identity, and metric definitions.
4. **Paired model comparisons.** Models being compared must use the same network, evaluation scenario, demand, SUMO protocol, and seed list. Report each seed and aggregate with uncertainty. A one-seed quick run is a smoke test, not a statistically supported winner.
5. **Saved weights are first-class.** A model registry entry must resolve to usable checkpoint files, not merely a label pointing at a transient run name.
6. **Show the evidence together.** The model, its source training runs, benchmark runs, score plots, and artifacts must be linked in one flow.
7. **Simple by default, detailed on demand.** Keep a readable overview; expose per-seed, per-episode, and hyperparameter details in expandable panels rather than a crowded default table.

### Out of scope for the first delivery

- Installing or hosting MLflow.
- Distributed training or multi-worker orchestration.
- Automatic promotion/deployment of a traffic controller into live operation.
- Claims of statistical significance from a single seed or smoke test.
- Deleting the study's historical ablation evidence; it can remain available separately from the main model workflow.

---

## 2. Current state: what exists and what is missing

This section describes the inspected implementation, not the desired end state.

| Area | Exists now | Gap / consequence |
|---|---|---|
| Training | Training Studio submits a recipe/network/seeds/timestep request; FastAPI queues a job, reports progress and saves checkpoints under `results/checkpoints/<agent>/<network>/seed<seed>.zip`. A training episode CSV and checkpoint sidecar are also written. | The UI mostly exposes network and timestep count, and the default 5,000-step choice is not a meaningful convergence target by itself. Job completion does not create a coherent saved-model card or benchmark report. |
| Shared policy | PPO training uses SuperSuit to map all intersections into vector slots for one shared SB3 policy. | This implementation should be explained clearly in the UI; users should not be led to believe each intersection/turn gets its own policy. |
| Training curves | Exporter reads `results/training/.../episodes.csv` and writes `training/<agent>__<network>.json`; separate training data supports learning curves. | The run registry records only a curves reference, not necessarily the seed-specific path. Very short runs may have just one episode, which does not form an informative curve. |
| Run registry | Exporter merges training seeds and summary-stat evaluation cells into `runs.json`; Runs page presents a flat row table and drawer. | It is a mixture of training-seed rows and pre-aggregated evaluation cells, not a durable registry of individual launched benchmark episodes. Status is exported as finished, live jobs are separate, evaluation seeds may be absent, and many table columns are blank because historical summary rows are aggregates. |
| Model registry | `POST /api/models/promote` writes a named version in `models.json`; UI has “Save as model” and a Models page. | Current promotion points at a run/checkpoint reference; it does not itself copy/package weights into an independently managed, verified artifact. The exported model registry is initially empty and can become stale/static. A version can exist without proving the checkpoint is available. |
| Compare | `POST /api/compare` runs selected method names on shared evaluation seeds and returns paired metric summaries; Compare displays a result table. | Form selects methods, not saved model versions. Learned methods resolve a default checkpoint path, so arbitrary versions cannot be selected. It handles one network, scenario, and demand per job, and there are no model-to-model learning/benchmark plots in the result view. |
| Statistics | Batch analysis already computes paired intervals, p-values, Holm corrections, and effect sizes. | The live comparison uses small seed limits and can create meaningless/overconfident interpretations if UI copy does not strongly distinguish one-seed quick checks from real benchmark batches. |
| Existing Analytics | `AnalyticsPage` renders forest, heatmap, test table, and distributions using exported study comparisons. | These plots use the historical report/export pipeline; they are not automatically the live results of the newly trained model comparison. This is why the benchmark can look stale even after a live job finishes. |
| Persistence | Jobs are stored as JSON under `results/jobs`; training artifacts/checkpoints are on disk; static exports are under `frontend/public/data`. | There are multiple stores with different lifecycles. Live training/compare jobs and benchmark page data are not a single source of truth. Static registry JSON can lag live backend state. |
| Scope naming | Benchmark has Runs, Compare, Models, Train; Live Map is separate. | The tabs are structurally present, but they feel fragmented because users must infer the relationship and move between them manually. |

### Important correction about “remove each agent focusing on formula-specific turn”

The training implementation already shares one policy across intersection agents; it does not have a separate neural network per turn. The app has also had legacy ablation recipes/presets, and older registry/export paths can make those look like separate competing “models.” The product should make **one complete policy** the default and keep any ablations clearly marked as research experiments, not the primary training workflow.

---

## 3. Target mental model and information architecture

The principal object should be a **Model**. A model version is backed by immutable weights and training provenance. A **Benchmark** is an evaluation campaign against one or more saved model versions. Individual seed/episode executions are **Runs** belonging to that campaign. A **Training job** is the live operation that creates a model version; it becomes a training record on completion.

```text
Benchmark
├── Overview / Benchmark (default landing)
│   ├── Start a benchmark using saved models
│   ├── Recent campaigns and key result plots
│   └── Clear warnings for smoke tests / incomplete evidence
├── Train
│   ├── Train one shared generalist policy
│   ├── Configure supported demand/events and compute budget
│   └── Live job → checkpoints → register as a model version
├── Models
│   ├── Named models and immutable versions
│   ├── Weights, recipe/config, source training run(s), compatibility
│   └── “Benchmark selected versions” action
└── Runs / Evidence (secondary, advanced)
    ├── Campaign → per-model, per-seed episode records
    ├── Training records and learning curves
    └── Logs, raw metrics, checkpoint/artifact links
```

The current top-level names may remain (Runs · Compare · Models · Train) to avoid unnecessary navigation churn. If retained, their responsibilities must become explicit: **Compare** is a benchmark campaign over saved model versions; **Runs** is supporting evidence/history and should not dominate the default experience.

### Main user journey

1. Open **Train**, select a network and training budget, choose the complete generalist recipe (default), select training seeds, and start.
2. See one job with progress and a visible “shared policy across N intersections” explanation. The system writes checkpoints and episode metrics.
3. On completion, inspect the training curve and checkpoint summary. Save/register a model with a human-readable name. The immutable model version points at verified weights and the exact recipe/hash that produced them.
4. Open **Benchmark** or choose “Benchmark this version.” Select at least two saved models, then choose one or more evaluation scenarios, demand profiles, and shared evaluation seeds.
5. The system creates a campaign and per-model/per-seed runs, all using the same settings. Show live progress and allow cancel/retry without losing finished records.
6. Show a results page with key KPI cards, per-seed results, comparison plots, uncertainty, and a plain-language summary. Mark incomplete or single-seed runs as exploratory, never as a winner verdict.
7. Open any plotted point/row to inspect the exact SUMO episode, model version, seed, config hash, and artifacts.

---

## 4. Domain objects and data contracts

Avoid treating a flattened static export as the operational source of truth. Persist campaign, run, and model-version records in the backend's existing local results store initially (JSON/SQLite choice should follow repo conventions; do not add a database solely for this redesign). Static dashboard exports may remain for historical study summaries, but label them as such and do not mix them with live campaign results.

### 4.1 Model and immutable model version

```jsonc
{
  "modelId": "generalist-traffic",
  "name": "Generalist traffic controller",
  "description": "One shared PPO policy across all controlled intersections.",
  "versions": [{
    "versionId": "v1-<immutable-id>",
    "version": 1,
    "status": "ready", // training | ready | unavailable | archived
    "algorithm": "ppo",
    "networkFamily": "sf_mission",
    "observationSchemaVersion": 1,
    "trainingRunIds": ["train-..."],
    "recipe": {},
    "recipeHash": "...",
    "trainingSeeds": [41],
    "timestepsPerSeed": 4096,
    "weights": [{"seed": 41, "path": "...", "sha256": "...", "bytes": 0}],
    "createdAt": "...",
    "notes": ""
  }]
}
```

Rules:
- Model name/description can be edited; a registered version's weights/config/provenance cannot be silently overwritten.
- Registering a checkpoint validates that the file exists, loads with the declared algorithm, has the expected observation/action dimensions, and can run on the target network family.
- Keep per-training-seed checkpoints; do not silently collapse multiple seeds into one. Make clear that different seeds are separate learned weights, not ensemble members unless ensemble behavior is deliberately implemented.
- Store a content hash and size for integrity. Never expose private filesystem paths as browser-download URLs without an explicit safe artifact route.
- A new training run creates a new version or an unregistered candidate; it must not overwrite an existing registered version by name.
- Support model compatibility explicitly: a policy trained on one observation schema/network may be incompatible elsewhere.

### 4.2 Training record / job

```jsonc
{
  "runId": "train-...",
  "kind": "training",
  "status": "queued | running | completed | failed | cancelled",
  "modelCandidate": "...",
  "recipeHash": "...",
  "network": "sf_mission_2x2",
  "trainingSeeds": [41],
  "requestedTimestepsPerSeed": 4096,
  "completedTimestepsBySeed": {"41": 4096},
  "createdAt": "...", "startedAt": "...", "endedAt": "...",
  "episodeMetrics": [{"seed":41,"step":2880,"episodeReward":-3589.1,"meanHalting":87.8}],
  "artifacts": {"checkpoints": [], "config": "...", "logs": "..."}
}
```

A checkpoint every N steps is training evidence. It is not automatically a selected “best” model. If checkpoint selection is supported, use a separate validation seed set and record selection metric, all candidate scores, and the selected checkpoint. Do not select on benchmark/evaluation seeds.

### 4.3 Benchmark campaign

```jsonc
{
  "campaignId": "bench-...",
  "name": "Mission medium + emergency, v1 vs v2",
  "status": "queued | running | completed | partial | failed | cancelled",
  "modelVersions": [{"modelId":"...","versionId":"...","seedWeights":[41]}],
  "protocol": {"network":"sf_mission_2x2","demands":["medium"],"scenarios":["normal","emergency"],"evaluationSeeds":[2001,2002,2003],"quick":false},
  "protocolHash": "...",
  "createdAt": "...", "endedAt": "...",
  "runIds": ["eval-..."],
  "summary": {},
  "warnings": []
}
```

Campaign creation snapshots selected model version IDs and all protocol parameters. Editing the model later must not alter an already-running or historical campaign.

### 4.4 Evaluation run (one model × one checkpoint seed × one scenario/demand × one eval seed)

Keep the complete metric row currently returned by `run_episode`, plus identifiers and artifact references. Required identity fields: campaignId, runId, modelId/versionId, checkpoint training seed, evaluation seed, network, scenario/events, demand, quick/full protocol, recipe hash, SUMO/software versions, status and timestamps. Persist partial failures distinctly; do not replace missing metrics with zero.

### 4.5 Metrics vocabulary

Reuse canonical SUMO metrics where available and define the direction/unit in the UI:
- **Primary:** mean waiting time (s), mean travel time (s), throughput (vehicles/hour), unfinished/never-inserted/teleported vehicles.
- **Environmental:** CO₂ total (kg), CO₂ per driven distance when valid.
- **Network health:** mean queue/halting vehicles, insertion backlog.
- **Fairness/reliability:** P95 waiting time and across-seed spread/interval.
- **Special populations:** pedestrian waiting, bus travel/delay, emergency-vehicle delay/stops, only when that event/population exists in the evaluated episode.
- **Operational:** SUMO simulation wall time, decisions, safety conflicts/hard braking when measured, and checkpoint inference cost if collected.

Define a primary KPI before looking at results (recommended: mean waiting time, with throughput and unfinished trips as guardrails). Do not rank using a weighted composite unless its weights are explicit and predeclared.

---

## 5. User-facing page specifications

### 5.1 Benchmark landing / campaign creation

- Default entry into Benchmark should answer: “Which saved policy performs better under what conditions?”
- Primary action: **New benchmark**.
- Choose 2–8 compatible saved model versions (initial API may cap lower for runtime reasons, but communicate the limit).
- Select a network; supported scenario/event set; demand(s); shared evaluation seed count/list; full vs explicitly labeled smoke test.
- Estimate episode count and approximate runtime from measured local rates, with disclaimer that estimate varies by network and machine.
- If a model is missing/incompatible, explain exactly why and link to Train/Models rather than silently substituting a baseline.
- Recent campaigns show status, model versions, protocol, number of completed/failed episodes, and primary metric; click to results.

### 5.2 Train

- Default recipe: one complete parameter-shared generalist policy; show the actual recipe name/hash and what traffic inputs/reward terms are active.
- Controls: network; training seeds; timesteps or a clearly named budget preset; demand levels; supported scenarios/events; optional advanced PPO/reward/observation controls only if the editor already supports them.
- Explicitly separate training scenarios from benchmark scenarios. A scenario unsupported by a selected network must be disabled/explained, not allowed to crash in the middle of a run.
- One job card per run group; expandable per-seed progress, current episode demand/event, steps/sec, ETA, latest reward/halting, checkpoints, errors, cancel/resume.
- Save candidate as a named model version after completion; allow automatic candidate registration only if the user confirms the name/version behavior.
- Show training curve (episode reward, halting/waiting, throughput if logged) with seed selection and raw point table. One episode should be labeled insufficient for a learning trend.
- Keep deep run formula/turn breakdown out of the primary UI. Hyperparameters may be inspectable as run metadata, not separate agents.

### 5.3 Models

- Model list with human name, latest version, algorithm, compatible networks/schema, training date, training seeds/timesteps, status, source recipe, and latest benchmark summary.
- Version detail includes immutable checkpoint artifacts per training seed, checksum, config/provenance, training curves, validation selection (if any), benchmark history, and notes.
- Actions: rename model, register candidate, compare/benchmark selected versions, download weights via safe authenticated/local route if supported, archive version. Do not offer “promote to live traffic” in this project scope.
- A missing weights file marks version unavailable and disables benchmarking; never present an empty registry as though saving already works.

### 5.4 Compare / benchmark results

- Header: benchmark name/status, exact protocol, selected model versions and evaluation seeds, reproducibility hash, quick/full badge, and warnings.
- **Overview KPI tiles**: primary metric and guardrails; show winner only if evidence criteria pass. Always show n runs/seeds.
- **Main plots (must be results from this campaign):**
  1. Paired per-seed dot/slope plot for the primary metric (each seed is a connected pair across models).
  2. Mean with 95% CI / bootstrap interval plot for primary and selected metrics (avoid CI when n=1; label unavailable).
  3. Scenario × demand heatmap for mean waiting time and configurable metric selector.
  4. Optional time-series queue/waiting curves aggregated across matching runs; show seed traces faintly and model mean clearly.
  5. Training learning curve is separate from benchmark plots, but link to it.
- **Details:** per-seed table; per-episode status; metric definitions; failed/partial run list; hyperparameter/config diff; CSV/JSON export.
- Compare models using identical evaluation conditions. If their training-seed checkpoint selection differs, expose that choice and avoid conflating evaluation-seed variance with training-seed variance. For robust claims, consider crossed evaluation seeds × trained checkpoint seeds.
- Statistical summary: paired differences over shared evaluation seeds; confidence interval and effect size; correct multiple comparisons when testing many models/metrics; note that a small seed count has low power. Never say “significant” at n=1.

### 5.5 Runs / evidence explorer

- Advanced/secondary table, not the primary Benchmark landing.
- Tabs/filters for training jobs, benchmark campaigns, evaluation episodes, failed runs, and historical exported study data.
- Every row links to a parent model version or campaign.
- Individual SUMO episode drawer: model/checkpoint, seed, network/events/demand, metrics, decisions/logs, artifacts and reproduction command.
- Distinguish **historical imported/exported study results** from **new live campaigns** with source badges and separate filters. No mixing in a single unlabelled “finished” list.

---

## 6. Benchmark protocol and evidence standards

### Smoke / short pilot

- Quick episodes (`quick=true`) are for checking wiring and plotting only.
- May use one evaluation seed and a reduced episode duration.
- Label **Smoke test — not a model ranking**; suppress winner/verdict/significance language and confidence intervals.
- Preserve and show complete episode metrics, but do not mix into the official full benchmark aggregate.

### Development benchmark

- Same network and protocol, at least 3 shared evaluation seeds; suitable for debugging and preliminary iteration, still limited evidence.
- Use paired differences, show each point, and avoid strong significance claims.

### Reportable comparison

- Full configured SUMO warmup/measure/cooldown protocol, supported scenario × demand matrix, at least 10 shared evaluation seeds as a practical initial target (final sample size should be chosen based on variance/power and compute budget).
- Prefer multiple independently trained checkpoint seeds and cross each against the same evaluation seeds when compute allows. Report both sources of uncertainty.
- Predeclare primary metric, evaluation protocol, exclusions, and model versions before running.
- Keep seeds grouped/paired; bootstrap the paired delta by evaluation seed or use an appropriate paired method. Do not apply unpaired Mann–Whitney as if seeds were paired, and verify current stats helper semantics before claiming a paired p-value.
- Correct multiple comparisons across the planned family of models/metrics; provide effect size and interval, not only p-value.
- Include throughput, unfinished and teleport counts as guardrails, so lower waits cannot hide dropped/uncompleted trips.

---

## 7. Backend and storage design

### 7.1 Establish the authoritative operational store

1. Inventory the current job JSON, training folders, selected checkpoint copies, static `runs.json`, static `models.json`, `results/raw`, and `results/tmp` lifecycle.
2. Define one storage module/repository interface for models, training records, campaigns and episode runs.
3. Start with durable project-local files if consistent with current app/deployment mode; use atomic temp-write + replace, schema versioning, locking, and recovery on malformed/incomplete records. If concurrent API processes are a supported deployment, choose SQLite rather than claiming a process-local lock is sufficient.
4. Treat `frontend/public/data/*.json` as exports/read-only historical data, not mutable production state. Do not have API routes mutate files inside public assets as the long-term registry.
5. Provide a migration/import step for existing jobs/checkpoints/runs; preserve source IDs and mark inferred or incomplete metadata. Do not delete any current artifacts.

### 7.2 Model APIs

Suggested interfaces (adapt to existing route naming/conventions):
- `GET /api/models`: model and version summaries, available status, pagination/filtering if needed.
- `GET /api/models/{modelId}/versions/{versionId}`: full provenance/artifact metadata.
- `POST /api/models`: create named model or register a validated completed training candidate/version.
- `PATCH /api/models/{modelId}`: edit descriptive metadata only.
- `POST /api/models/{modelId}/versions/{versionId}/archive`: archive without deleting weights.
- `GET /api/models/{modelId}/versions/{versionId}/weights/{trainingSeed}`: safe download/stream if appropriate; path containment and existence checks required.

Existing `POST /api/models/promote` should be migrated/renamed or given compatibility behavior; its current name implies baseline promotion but currently registers a named version. Establish distinct API operations and labels so users cannot confuse registration, version selection, and promotion.

### 7.3 Training APIs and job durability

- Retain current `POST /api/train`, jobs listing/SSE/cancel while extending request/result records with persisted episode series, current seed, checkpoint inventory, config hash and terminal status.
- A completed job should create an immutable **training run** record and a validated model candidate, but require explicit registration/confirmation for the stable named version unless a clear auto-register option is chosen.
- Ensure resume behavior is explicit and recipe-hash checked; a changed recipe cannot silently append to old weights.
- Ensure cancellation preserves completed seed checkpoints and marks partial seeds accurately.
- Avoid swallowing persistence errors; surface them in job status and logs.

### 7.4 Benchmark APIs / worker

- Add a campaign endpoint accepting `modelVersionIds`, network, scenarios/events, demands, shared evaluation seeds, full/quick mode, and primary metric.
- Validate model existence, checksum, algorithm, observation/action compatibility, network support, scenario support, and seed limits before enqueue.
- Expand deterministic task plan: model version × training checkpoint seed × scenario × demand × eval seed.
- Persist each episode as it completes. On error/cancel, campaign becomes partial/cancelled with completed evidence retained.
- Compute summary only from successful, comparable tasks; do not coerce missing values to zero.
- Add campaign list/detail/SSE endpoints; do not overload the old method-name `POST /api/compare` indefinitely.
- Keep old compare endpoint for compatibility while front-end migrates; remove only after no callers and documented data migration.

### 7.5 Security and artifact safety

- Treat all requested IDs, model names, run IDs and artifact paths as untrusted input.
- Normalize and verify paths remain under configured artifact roots; reject traversal/symlink escapes.
- Use content hashes; avoid serving pickle/zip as executable content inline. Set safe content disposition and MIME type for downloads.
- Do not expose the user's machine filesystem through API paths.
- Bound campaign size, episodes, seeds and concurrent jobs; return a clear estimate/validation error rather than exhausting disk/CPU.

---

## 8. Frontend implementation design

### Data flow

- React Query owns API server state: models, jobs, campaigns, campaign detail, run detail.
- SSE updates jobs/campaign progress and invalidates or updates the relevant caches on terminal status.
- Existing static source mode remains supported for historical reports and read-only demo. Add explicit source/status badges; no static-source write controls.
- Add typed Zod schemas for new API entities and validate IDs/statuses/artifacts.
- Keep route deep-links: model version detail, campaign result, individual run; preserve selection across Runs → Compare only where it remains useful.

### Plotting

- Reuse the existing ECharts/ChartCard infrastructure, but feed it campaign-specific live API data, not old `comparisons.json`.
- Add reusable builders only for the specified plots (paired dots/slopes, CI, heatmap and optional timeseries). Include accessible table alternatives and CSV/JSON export.
- Ensure plot titles encode metric/unit, n, demand/scenario/network; no visual implication of precision beyond the actual seed count.

### UI migration

- Keep navigation names initially to control scope: Runs · Compare · Models · Train.
- Change Compare to select registered model versions, not arbitrary catalog methods. Preserve a clearly separated “Controller study” only if historical analysis still needs it.
- Make Benchmark landing campaign-focused (either use Compare as landing initially or add a compact campaign summary; avoid adding a separate tab before the flow works).
- Move legacy study charts into Analytics/Study Results and label their provenance. Do not delete the statistical dashboard.
- Rename Runs description/table headers so training run, campaign, and episode have distinct meanings.
- Delete/remove the “Save as model” path only after a verified replacement flow exists; avoid UI that promises usable model storage when only a registry pointer is saved.

---

## 9. Migration and compatibility

1. Capture a baseline of API shapes and existing files before changing behavior.
2. Add versioned schemas and readers for existing `results/jobs/*.json`, training folders, checkpoint sidecars, exported runs and model JSON.
3. Import legacy training checkpoints as versions only when the file exists and loads; otherwise record an unavailable legacy candidate with explicit reason.
4. Import static evaluation summary rows as `historical` evidence, preserving their aggregated nature and n/CI; never fabricate per-seed rows from means.
5. Keep existing Analytics and report exports working during rollout.
6. If new campaign APIs ship behind the scenes first, keep old compare/job API responses backward compatible until the frontend has migrated.
7. Provide rollback-safe migration: create new store alongside current, verify counts/hashes, then switch reads; retain old artifacts as source of truth until acceptance.

---

## 10. Phased delivery and acceptance criteria

### Phase 0 — Product/data contract and baseline (planning prerequisite)

- Agree on primary KPI, supported benchmark network/scenario matrix, model seed semantics, and what qualifies as “reportable.”
- Verify SUMO scenario support per network (e.g. incident config must exist before offering incident training/evaluation on that network).
- Write schema/API contracts and fixture examples; record current counts and file/artifact locations.

**Done when:** contract distinguishes model version, training job/run, campaign and episode; historical vs live data are identifiable; no unsupported scenario can enter a job silently.

### Phase 1 — Make training produce a trustworthy saved candidate

- Add/verify training-run persistence and checkpoint inventory; seed-level progress; curve endpoints/data.
- Validate candidate checkpoint format, checksum, algorithm and observation/action schema.
- Add explicit “Register model version” workflow and show weights/path availability; keep one shared generalist recipe primary.
- Make training history a secondary detail with a compact learning plot.

**Acceptance:** start a two-seed short training; monitor progress; cancel a separate short run and confirm partial state; finish a run; restart API and confirm job/model candidate/artifacts remain; register candidate; reload page and confirm version and weights verify; a missing/corrupted checkpoint is surfaced as unavailable rather than “saved.”

### Phase 2 — Benchmark campaigns use saved versions and shared conditions

- New campaign schema/task planner; select compatible model versions.
- Shared seeds across versions, scenario/demand matrix, full vs smoke protocol, preflight validation/estimate.
- Per-episode persistence, progress, cancel/retry, partial failure handling; metric summaries with provenance.

**Acceptance:** run two model versions on the same 2+ evaluation seeds in quick mode; task matrix is complete and every pair has identical conditions; rerun one failed episode without duplicating completed records; restarting API retains campaign and results; no method fallback or missing checkpoint is silently substituted.

### Phase 3 — Campaign result plots and honest comparison

- Build paired per-seed plot, metric interval plot (hidden/unavailable for n=1), scenario-demand heatmap, per-seed detail table, config diff and export.
- Publish deterministic statistic interpretation, with uncertainty, multiple-comparison correction, and guardrails.
- Clearly badge smoke/development/reportable evidence levels.

**Acceptance:** fixtures for n=1, n=2, failed/partial campaign and several scenarios render without misleading CIs or winner labels; plotted values match raw run records; export round-trips all metric/identity fields.

### Phase 4 — Models as the central reusable library

- Model/version detail and lineage, compatibility, checksum validation, benchmark history, archive and safe downloads if desired.
- “Benchmark selected versions” and links to source training run/campaign; model registry updates reflect live API state (not stale static JSON).

**Acceptance:** register versions from different training runs; each can be selected and benchmarked; model detail traces to exact checkpoint, recipe hash, training seed and all campaigns; unavailable weights block execution and explain why.

### Phase 5 — Clean up navigation and retire fragmented views

- Promote campaign workflow as Benchmark default; demote run-level details to Evidence; separate historical Controller Study/Analytics.
- Remove duplicate method-vs-model compare entry points only after migration and usage checks.
- Keep exports/report generation, legacy reads, and user data intact.

**Acceptance:** a new user can train, save, select two versions, launch paired evaluation, understand plots, and find evidence without navigating a formula-specific agent list; existing historical report pages and API consumers continue to work.

### Cross-cutting quality gates

- Backend unit tests for schema validation, task expansion, path safety, model loading/checksum, persistence/recovery, paired aggregation and failure states.
- Frontend typecheck/build and focused component tests for loading/empty/error/partial/n=1 states.
- End-to-end test on local SUMO for train→register→campaign→plots on a tiny supported network/protocol; no broad tests unless required by repository instructions.
- Verify performance by counting and timing SUMO episodes; never claim speed improvements without measurement.
- Manual acceptance uses the same seeds/config and checks raw CSV/JSON against charts.

---

## 11. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Full SUMO matrix is slow | Start with explicit smoke/dev presets; show episode count/runtime estimate; queue bounded work; persist partial progress. Never disguise smoke as final benchmark. |
| Multiple trained seeds create ambiguous model | Model version may reference a set of seed checkpoints; selector clearly chooses one seed or evaluates all, and report distinguishes within-training-seed from eval-seed uncertainty. |
| Static exports appear stale | Historical/static source badge; live campaign data uses API store and query invalidation; no campaign result is read from old `comparisons.json`. |
| Mixed network observation shapes | Preflight model compatibility; require explicit compatible network family/schema. Train separate network-specific versions only when dimensions/geometry require; still one shared policy over intersections within each network. |
| Unsupported scenario metadata causes run crashes | Validate network × scenario compatibility before queueing and in the episode builder. |
| Statistical overclaim | Primary metric predeclared, seed-level paired points, minimum evidence badge, no inference at n=1, guardrail metrics and transparent intervals. |
| Checkpoint loss or overwritten files | Immutable version paths, atomic copy, checksums, no overwrite, backup/migration verification. |
| Process-local locking fails with multiple workers | Single-process constraint documented or transactional SQLite/locking for multi-process; do not rely on threading.Lock alone. |
| Artifacts cannot be downloaded safely | Safe root containment, checksum, safe disposition, explicit local-only status if not served. |

---

## 12. Decisions to confirm before implementation

Recommended defaults are marked **(recommended)**; these are product choices, not blockers to this plan:

1. **Primary score:** mean waiting time, with throughput and unfinished/teleported vehicles as guardrails. (recommended)
2. **Default benchmark network:** San Francisco Mission 2×2 initially for fast reproducible iterations; allow other compatible networks. (recommended)
3. **Training seeds:** default one for smoke, offer multiple for meaningful training variability. Persist each seed checkpoint. (recommended)
4. **Evaluation seeds:** smoke = 1; development = 3; reportable target = 10 shared seeds, to be revised based on variance/power and runtime. (recommended)
5. **Model checkpoint policy:** keep every training seed's final checkpoint; optionally retain intermediate checkpoints per existing cadence. No silent best-checkpoint choice without held-out validation. (recommended)
6. **Model naming:** user supplies a display name; stable generated model/version IDs; one model may have many immutable versions. (recommended)
7. **Live traffic promotion:** out of scope; “register/save” means reusable benchmark artifact only. (recommended)
8. **Research ablations:** preserve in historical study views, remove from default model/training navigation. (recommended)

---

## 13. Immediate next implementation slice

The first code delivery should be deliberately narrow and end-to-end:

1. Make training completion produce a persistent training run record and verified model candidate from the existing copied checkpoint, without changing PPO behavior.
2. Add `GET models`/version detail from the operational backend store; stop treating `frontend/public/data/models.json` as mutable authoritative registry.
3. Build the saved-model selection benchmark request for two versions on one supported San Francisco network, one demand/scenario and at least two shared evaluation seeds; persist each episode and campaign result.
4. Render paired per-seed mean-waiting-time plot + per-seed table, with smoke/development evidence badge and no significance claim below the agreed seed threshold.
5. Keep the existing historical analytics intact and explicitly label its data provenance.

**Do not start by rewriting every tab.** Ship this vertical slice, verify the lifecycle in SUMO, then expand scenario/demand matrices and richer plots based on the working data contract.

---

## 14. Existing architecture notes (for implementation planning)

- Training core: `src/cotraffic/training/train.py`; parameter-shared PPO via PettingZoo/SuperSuit/SB3; checkpoints and `episodes.csv` under `results/training/<recipe>/<network>/seed<seed>/`.
- Selected/copied checkpoints and sidecars: `results/checkpoints/<recipe>/<network>/seed<seed>.zip`; API training copies the final checkpoint here in `api/jobs.py`.
- Recipe registry/config: `configs/recipes/`; `src/cotraffic/recipes.py` loads and normalizes them; `configs/recipes/generalist.yaml` is the flagship full-budget profile.
- Job API/state: `api/jobs.py`, `api/routes/jobs.py`, `results/jobs/*.json`; one sequential worker; current types are training and method-based compare.
- Model registry: `api/routes/models.py`; currently mutates `frontend/public/data/models.json`; current promote operation registers a run pointer and version metadata, not a content-addressed artifact store.
- Static exporter: `scripts/export_dashboard_data.py`; emits historical summary/comparison/training JSON and a mixed training/evaluation `runs.json` from files.
- Frontend: `frontend/src/features/{training,runs,models,analytics}/`; tab mounting in `frontend/src/shell/benchmark-mount.jsx`; queries/schemas under `frontend/src/shared/`.
- Existing charts: `frontend/src/shared/charts/` (ECharts wrappers/builders); current `AnalyticsPage` uses static study comparisons while `FreshCompare` handles live method-based A/B jobs.
- Live comparison backend: `JobRunner.submit_compare` and `_run_compare` in `api/jobs.py`; up to five methods/seeds, one network/scenario/demand per job, uses default checkpoint lookup for learned method IDs.

## 15. Appendix: why the current flat Runs table looks stale/fragmented

The screenshot's rows correspond to exported aggregates and training seeds, not a single current campaign. The exporter groups summary data by method/network/scenario/demand and puts aggregate metric means in a row, so an individual eval seed is not necessarily represented. Training jobs are stored separately in `results/jobs` and the training folders. The Models page reads `models.json`, which starts empty and is only filled by the API's run-promotion action. The live Compare flow writes result rows in quick/full output directories and keeps its structured paired result on the job record; it does not automatically transform that result into the old static `comparisons.json` chart data. Consequently the Benchmark tabs can show a stale-looking historical table next to live job state, even though both are functioning according to different stores.

The target fixes this by separating source types and making a saved model version → benchmark campaign → seed-level episode runs → campaign plots a persisted, traceable chain.
