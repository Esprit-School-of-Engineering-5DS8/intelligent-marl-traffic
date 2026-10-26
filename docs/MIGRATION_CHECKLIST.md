# Migration checklist — retiring the legacy stack

> Gate before deleting anything. A box is ticked only when the command was run **on this
> branch** and passed. Copy this file per phase and keep the evidence line filled in.
>
> Companion document: [ARCHITECTURE.md](ARCHITECTURE.md) (§8 Deprecation map).

## 0. Baseline

- [ ] Working tree clean (`git status --short`) — otherwise stash or commit first.
- [ ] `python -m cotraffic --help` lists every command.
- [ ] `python -m pytest tests -q` — record the pass/fail counts: `______`.
- [ ] `cd frontend && npx tsc --noEmit` — clean.
- [ ] `cd frontend && npx vite build` — succeeds.

## 1. Domain boundary (src/cotraffic)

- [ ] `python -m cotraffic episode --net grid2x2 --demand medium --steps 120` completes.
- [ ] `python -m cotraffic evaluate --experiment llm_ab_quick --jobs 1` → all runs written.
- [ ] `python -m cotraffic aggregate && python -m cotraffic tables` regenerates
      `results/summary/REPORT_TABLES.md` with every network section.
- [ ] `python -m cotraffic smoke` passes.

## 2. HTTP layer

- [ ] `uvicorn api.main:app --port 8000` starts without import errors.
- [ ] `curl -s localhost:8000/api/health` → `{"ok": true, ...}`.
- [ ] `curl -s localhost:8000/api/data/meta` returns the exported meta file.
- [ ] `GET /api/policy` returns the active method and its availability.
- [ ] `PUT /api/policy {"method": "coop", "network": "grid4x4"}` → 200 when the checkpoint
      exists, `422` when it does not.
- [ ] `PUT /api/policy {"method": "nope"}` → `422` (unknown method).
- [ ] `PUT /api/policy {"method": "mp", "network": "grid4x4"}` then
      `POST /api/simulation/start {"scenario": "grid-2x2"}` → snapshots carry `simulationTime`,
      `vehicles`, `signals`, `status`; `step` accepts an empty body while paused.
- [ ] A learned method whose checkpoint exists only for `grid4x4` → the 2x2 live run returns
      `422` (the checkpoint must match the network that runs, not the settings selection).
- [ ] `PUT /api/policy {"method": "llm"}` with no key → accepted, marked `degraded`, and the
      live run still completes on the Max-Pressure fallback.
- [ ] `PUT /api/policy {"method": "coop", "network": "grid2x2"}` (no checkpoint) → `422`.

## 3. Frontend contract

- [ ] Dashboard loads with `dataSource=mock` (no backend) — every tab renders.
- [ ] Dashboard loads with `dataSource=live` (backend on :8000) — same numbers.
- [ ] Live map: start / pause / step / stop still drive `/api/simulation/*`.
- [ ] Settings: changing the control policy persists and reaches `PUT /api/policy`.
- [ ] `npm run build` output boots from `vite preview` without console errors.
- [ ] Both themes render (KEMETRA green/white + dark glass), RTL language still laid out.

## 4. Legacy imports are gone

Run these before deleting; each must return **no matches** (except in this checklist and
`docs/ARCHITECTURE.md`):

```bash
grep -rn "multi_agent_env\|SumoMARLEnv" --include="*.py" . | grep -v "docs/"
grep -rn "from baselines\|import baselines" --include="*.py" . | grep -v "docs/"
grep -rn "benchmark_baselines\|run_experiments" --include="*.py" . | grep -v "docs/"
grep -rn "from agents\.\|import agents\." --include="*.py" . | grep -v "docs/"
grep -rn "runner.py" --include="*.py" . | grep -v "docs/"
```

- [ ] All five greps are empty.
- [ ] `python -m pytest tests -q` still passes after rewriting/removing the tests that
      imported the legacy environment (`tests/test_multimodal.py` is the known one).

## 5. Deletion (only after §4)

- [ ] `environment/` removed
- [ ] `baselines/` removed
- [ ] `evaluation/benchmark_baselines.py`, `evaluation/run_experiments.py` removed
      (keep the folder if it still holds shared helpers — check imports first)
- [ ] `agents/rl/*` stubs removed (keep `agents/` only if something imports it)
- [ ] `scenarios/*/runner.py` removed (SUMO network/route assets stay)
- [ ] `requirements-rami.txt` / `requirements-backend.txt` reconciled with
      `requirements.txt`
- [ ] README.md and frontend/README.md point only at `cotraffic` + `api/`

## 6. Final regression

- [ ] `python -m cotraffic smoke`
- [ ] `python -m cotraffic evaluate --experiment llm_ab_quick --jobs 1`
- [ ] `python -m cotraffic tables`
- [ ] `python -m pytest tests -q`
- [ ] `uvicorn api.main:app` + dashboard live mode, one full start/pause/step/stop cycle
- [ ] Commit message records: removed paths, replacement commands, test evidence.

## Rollback

Every step above is a git-visible change: `git revert <commit>` restores a removed folder.
Deletions happen in **separate commits** per area (simulation / baselines / evaluation /
agents / scenarios) so a single revert never has to untangle unrelated edits.
