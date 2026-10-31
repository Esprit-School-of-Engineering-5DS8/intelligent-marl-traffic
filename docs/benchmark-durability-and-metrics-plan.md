# Benchmark: durable campaigns and multi-metric evidence

## What is wrong today

The plumbing exists but does not survive reality:

1. **A campaign is lost when the API process stops.** `JobRunner._load_saved` rewrites any
   `queued`/`running` job to `failed` with "automatic resume is not supported". A 24-episode
   suite takes ~35 minutes; a crashed backend, a closed terminal, or a reloaded window throws
   away everything except what happened to be flushed. Observed: 23 of 24 episodes finished,
   the job stayed `running` forever, the tab kept showing a progress bar that would never move.
2. **Durability is already half-built, but only for humans reading JSON.** `_persist` runs
   after every episode, so the rows are on disk — nothing can resume from them.
3. **The evidence is one metric wide in the place people look.** The suite records paired CIs,
   Wilcoxon p-values and Cliff's delta for each metric, but the Compare tab shows one metric at
   a time through a selector, so a campaign reads as "mean waiting time only".

## Goals

- An interrupted campaign is *resumable*, not lost: it keeps its completed rows, tells the
  user exactly what is missing, and finishing it costs only the missing episodes.
- A finished campaign can be read as a whole: every metric, its mean, its interval, its paired
  change and its significance, in one table with CSV export.
- Nothing about the traffic semantics changes: same networks, scenarios, demands, seeds and
  saved-model checksums. This is a durability and reporting change only.

## Phase 1 — Durable suite execution

| Change | Where |
| --- | --- |
| `updated_at` heartbeat on every persist | `api/jobs.py` (`JobRecord`, `_persist`, `public_job`) |
| On load, a suite with completed rows becomes `interrupted` (not `failed`), keeping its result and a message naming the gap | `api/jobs.py::_load_saved` |
| `resume` requeues an interrupted suite | `api/jobs.py::JobRunner.resume` |
| `POST /api/jobs/{id}/resume` | `api/routes/jobs.py` |
| `interrupted` becomes a known status; `useResumeJob` mutation | `frontend/src/shared/api/jobs.ts` |
| Resume button on the campaign card, honest "interrupted after N of M" line | `frontend/src/features/analytics/FreshCompare.tsx` |

**Resume rule:** `_run_benchmark_suite` seeds its row list from the retained result and skips
every `(model, scenario, demand, seed)` cell already recorded as `done`. A resumed campaign
therefore re-runs exactly the missing episodes and reuses the rest, so the paired statistics
stay valid (same seeds, same saved versions, same code path).

**Known limit, stated in the UI:** an interrupted campaign is only resumable while its saved
model versions still resolve and are checksum-clean; resuming after a model has been removed
fails loudly at the missing cell instead of silently mixing versions.

## Phase 2 — All metrics in one place

- Broaden the suite's tracked metric set from 7 to the metrics the evaluation already computes:
  mean/median/p95 waiting time, travel time, time loss, person-weighted delay, stops per
  vehicle, throughput, mean queue, CO₂, SSM conflicts per 1 000 vehicles, emergency-vehicle
  delay and pedestrian waiting time. Each keeps its unit and its improvement direction.
- Add an **all-metrics table** to the Compare result: one row per condition × model × metric
  with mean, 95 % interval, paired change against the reference, its interval and p-value.
  The metric selector keeps driving the plots; the table is the complete evidence.

## Phase 3 — Verification

1. Interrupt a suite mid-campaign (stop the API), restart it, and check the job loads as
   `interrupted` with its rows intact.
2. Resume it and confirm only the missing cells run and the result reaches `done`.
3. Confirm an ordinary finished campaign still reports `done`, and a cancelled one `cancelled`.
4. Check the all-metrics table renders for a campaign whose sandbox lacks some metrics
   (e.g. no pedestrians): missing values show `–`, never a fabricated zero.
5. `python -m pytest tests/test_benchmark_redesign.py` and `tsc --noEmit`.

## Out of scope

- MLflow or any external tracker: the tab is the product surface, and a second UI or a second
  service adds failure modes rather than removing them. The durability work above is the part
  a tracker would have given us; the paired statistics are not.
- Retiring the single-metric `benchmark` job kind: it stays as the quick A/B path.
