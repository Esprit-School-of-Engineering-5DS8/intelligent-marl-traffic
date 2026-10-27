# Handoff — Training Studio

Last updated: 2026-10-27

## Objective

Finish the Training Studio slice of the KEMETRA benchmark redesign: a real backend training queue with SSE progress, reachable from the Scenarios page with `Entraîner ici`.

Guardrails:

- Preserve the accepted KEMETRA light/green shell.
- Do not reintroduce the CoTraffic React entry.
- Keep `/api/catalog` as the source of networks, recipes and trainability.
- Treat a non-trainable recipe as “network only” prefill, not an error.
- Backend allows only one active training job.

## Current State

Training Studio is implemented and **runtime-smoke-tested** (2026-10-27). See the ticked items below.

### Implemented

- `frontend/src/shared/api/jobs.ts`
  - Zod `Job` schema.
  - `useJobs` polling.
  - `useStartTraining`, `useCancelJob`.
  - `useJobStream` via SSE, updating the React Query cache.
- `frontend/src/features/training/TrainingPage.tsx`
  - Network/recipe/seed/timesteps form.
  - Launch training, queue list, progress bar, reward/halting/ETA, cancel.
- `frontend/src/features/training/store.ts`
  - Shared prefill store for `Entraîner ici`.
- `frontend/src/features/scenarios/CatalogScenariosPage.tsx`
  - `Entraîner` button on each scenario card.
  - Prefills the selected network and recipe when trainable.
- `frontend/index.html`
  - New `Entraînement` benchmark sub-tab.
- `frontend/src/shell/benchmark-mount.jsx`
  - Registers the `training` page.
- `frontend/src/shell/app.js`
  - `sumo:open-training` event routes to the training tab.
- `en.json`, `fr.json`, `ar.json`
  - Training and catalog-train translations.
- `npx vite build` passes.

### Not Verified

- No browser UI test: `agent-browser` is blocked by local Application Control.
- No real training job has been submitted from the new page yet.
- SSE streaming through the Vite proxy has not been exercised from the UI.

## Next Steps

### 1. Close the Training Slice

- [x] Fix sidebar state when opening training from a scenario card:

  ```js
  document.addEventListener('sumo:open-training', () => {
    setBenchmarkNavOpen(true);
    document.querySelector('#benchmarkSubnav [data-benchmark-tab="training"]')?.click();
  });
  ```

- [x] Submit a short real job:
  - `recipe_id`: `coop`
  - `network`: `grid2x2`
  - `seeds`: `[1]`
  - `timesteps`: `500`, `1000`, `4000`, `5000`, `6000` (all completed with a checkpoint; `40 000` done; `100 000` cancelled)
- [x] Verify:
  - `POST /api/train` returns `202` with `queued`.
  - `GET /api/jobs` shows it.
  - `GET /api/jobs/{id}/events` streams progress.
  - `POST /api/jobs/{id}/cancel` works (verified from `running` and from `queued`).
  - Checkpoint appears under `checkpoint_path` (results/checkpoints/coop/<network>/seed1.zip + sidecar).
- [x] Verify a second training launch is disabled while one is active (`400` with the blocking job name in `detail`).
- [x] Verify the SSE completion state: progress reaches 100%, status becomes `done` or `cancelled`.
- [x] FR labels verified in the browser. EN/AR label spot-check pending.

**Bug found & fixed during smoke**: a cancelled job used to persist `step = totalSteps` and a `checkpoint_path` copied from the interrupted seed, showing "100 000 / 100 000 pas · Checkpoint: seed1.zip" for work it never did. `api/jobs.py::_run_training` now skips publishing checkpoint/progress for a cancelled seed (verified: cancelled job → `0 / 100 000`, no checkpoint line). Backend was restarted without `--reload` to pick the fix up.

### 2. Manual UI Smoke

- [x] Scenarios → `Entraîner` → correct network/recipe prefilled (Grille 2x2 + Cooperative PPO).
- [x] Submit → notice "Entraînement COOP lancé sur Grille 2x2." → queue updates within a second.
- [x] Refresh page; recent jobs still load from `/api/jobs` (records persist in results/jobs).
- [x] Duplicate launch shows a readable `400` error (tested at API level).
- [x] Cancel updates the row without a stuck spinner (states queued/running/done/cancelled all render).
- [ ] Switch to another benchmark tab and back (partially verified via reload → Entraînement).

### 3. Decisions To Settle

- [ ] Should a baseline controller selection fall back to `coop`, or pick an overlay-matched recipe?
  - Current behavior: non-trainable method → first trainable recipe.
- [ ] Keep single-seed quick training, or support multi-seed in the same job?
  - Backend supports `seeds: list[int]`; UI currently sends one seed.
- [ ] Keep `5000` default timesteps, or use recipe-specific quick defaults?
- [ ] Should the queue show only `kind: "train"`, or also comparison jobs?
  - Current page filters to training only.

### 4. Next Feature Blocks

- [ ] Comparison page: real paired A/B submissions via `/api/compare`, live job progress, delta output.
- [ ] Agents page: replace static analytics with real job/run data.
- [ ] LLM trace viewer: read `results/telemetry/<run_id>/llm_calls.jsonl`.
- [ ] Retire or rewire static `ScenariosPage.tsx` once catalog/launch/training flows cover it.

### 5. Verification and Cleanup

- [x] `npx vite build` (passes, chunk-size warning only)
- [x] `pytest tests/test_benchmark_redesign.py tests/test_policy_api.py -q` → 11 passed
- [ ] `npx tsc --noEmit` is still blocked by missing test dependencies:
  - `vitest`
  - `@testing-library/react`
  - `@testing-library/user-event`
- [ ] Review git state before committing. The worktree is large: ~154 modified tracked files plus new backend/frontend files.
- [ ] Do not commit until explicitly requested.

## Quick API Commands

```powershell
$body = @{
  recipe_id = 'coop'
  network = 'grid2x2'
  seeds = @(1)
  timesteps = 500
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/api/train `
  -ContentType 'application/json' `
  -Body $body
```

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/jobs
curl.exe -N http://127.0.0.1:8000/api/jobs/<job-id>/events
```

## Key Files

- `frontend/src/shared/api/jobs.ts`
- `frontend/src/features/training/TrainingPage.tsx`
- `frontend/src/features/training/store.ts`
- `frontend/src/features/scenarios/CatalogScenariosPage.tsx`
- `frontend/src/shell/benchmark-mount.jsx`
- `frontend/src/shell/app.js`
- `frontend/index.html`
- `frontend/src/shared/i18n/locales/en.json`
- `frontend/src/shared/i18n/locales/fr.json`
- `frontend/src/shared/i18n/locales/ar.json`
- `api/routes/jobs.py`
- `api/jobs.py`
