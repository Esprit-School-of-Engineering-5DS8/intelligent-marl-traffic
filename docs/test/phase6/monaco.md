# Phase 6 — Monaco (MoST) real-scenario evaluation

The real-world companion to the 3x3 grid package (`grid_3x3.md`): the Monaco
SUMO Traffic scenario (MoST, Codecà & Härri, VNC 2017; **GPL-3.0**) with 12
signalized junctions, ~1,700 edges, multimodal demand and a real
`vClass=emergency` fleet. Integrated from
`origin/feature/monaco-real-scenario` (`6d84e4a`); see
`scenarios/monaco/README.md`.

## Setup

- **Window**: `begin=25200` (07:00, morning peak), **1000 steps = 17 minutes**
  (`monaco.llm.sumocfg`; the config itself remains capable of a 30-minute
  window, `end=28800`). The full upstream route files are reused unchanged —
  SUMO discards departures before `begin`. The window was shortened from the
  planned 30 minutes for budget/runtime reasons; the per-seed LLM caches act
  as deterministic checkpoints, so no recorded work was lost in the change.
- **Step length 1.0 s** (MoST recommends 0.25 for lateral fidelity); the
  sublane model (`lateral-resolution`) is dropped as meaningless at 1 s.
  `time-to-teleport=120`, striping pedestrians, rerouting as in MoST.
- **Arms**: A0 `sumo_default` (MoST's genuine actuated programs — the real
  baseline), A2 `max_pressure`, A4 `llm_team` (Operator + Emergency; no
  Pedestrian agent on this scenario). 3 seeds each, same window.
- **Control generalization** (see `tests/test_monaco.py`): 8 junctions have 2
  distinct vehicle-green sets, 4 have 3 (protected-turn / one-way phases).
  `TLSTopology` exposes every set as a selectable group (28 groups total);
  groups are clustered into the NS/EW axes by lane heading for the
  LLM/directive layer, and the Emergency reviewer pins the exact group
  (`phase_index`) so pre-emption serves the EV's real approach. Controlled
  arms first convert MoST's actuated programs to **static copies** (on
  actuated logic SUMO caps pinned phases at `maxDur` and would take control
  back; a 400-step drift check shows zero SUMO-initiated phase changes);
  `sumo_default` keeps the real actuated logic.
- **EVs**: real specials, 60% `vClass=emergency`; EV KPIs aggregate
  `vType=emergency` tripinfo records (`authority`/`army` stay civilian).
- **LLM**: `deepseek-v4.1-flash`, temperature 0, `LLM_MAX_CALLS=900`
  (never reached). Recorded with `--llm openai` in two segments (a resume
  replayed the first 262–274 calls of each seed from cache); strict
  `--llm replay` of all three seeds is **bit-identical** on every summary
  metric. Prompts were not modified (grid replay caches stay valid).

## Results (3 seeds, mean ± std)

**Vehicles** (`tripinfo`, all non-emergency vehicles; the `pedestrian_*` ids
in MoST route files are cars on multimodal person trips, not walkers):

| Arm | Step standing time (s) | Mean speed (m/s) | Arrived | Tripinfo wait (s) | Time loss (s) |
|---|---|---|---|---|---|
| A0 `sumo_default` | **432.35 ± 15.71** | **10.78 ± 0.03** | **575.0 ± 8.5** | **15.37 ± 0.34** | **81.37 ± 0.60** |
| A2 `max_pressure` | 3555.29 ± 141.03 | 10.55 ± 0.03 | 534.7 ± 2.3 | 20.50 ± 1.00 | 82.91 ± 1.20 |
| A4 `llm_team` | 3593.35 ± 72.53 | 10.54 ± 0.04 | 532.0 ± 4.0 | 21.85 ± 0.34 | 84.05 ± 0.75 |

**Emergency vehicles** (completed EV trips per 17-min window: 14–17):

| Arm | EV duration (s) | EV waiting (s) | Per-seed EV waiting |
|---|---|---|---|
| A0 `sumo_default` | 375.17 ± 6.79 | 16.02 ± 2.79 | 12.8 / 17.9 / 17.3 |
| A2 `max_pressure` | 346.29 ± 19.56 | 22.29 ± 17.94 | 13.4 / 42.9 / 10.5 |
| A4 `llm_team` | **337.59 ± 19.41** | **13.51 ± 12.33** | 7.7 / 27.7 / 5.1 |

**Pedestrians** (`<personinfo>`, 546–553 walkers per window):

| Arm | Mean wait (s) | p95 wait (s) |
|---|---|---|
| A0 `sumo_default` | 2.43 ± 0.27 | 12.67 ± 3.06 |
| A2 `max_pressure` | 1.93 ± 0.19 | 12.33 ± 1.53 |
| A4 `llm_team` | **1.85 ± 0.36** | **10.67 ± 2.52** |

Figures: `figures/step_wait_monaco.png` (A4 tracks A2 tightly; both far above
A0), `figures/bars_ev.png` (rightmost group), `bars_civilian.png`,
`bars_arrivals.png`.

## Findings

1. **MoST's actuated programs beat both phase-pinned arms on car KPIs**: −7%
   arrivals, +5–6 s tripinfo waiting, and a much lower standing-time curve.
   The queue-greedy controller (10 s min-green, no gap-out / max-green, plus
   long transition paths on the 3-set junctions) is simply not competitive
   with the network's tuned actuated logic. This is a property of the
   controller simplification and applies equally to A2/A4 — the fair
   attribution of the LLM layer is **A4 vs A2**, where the difference is
   within noise (−1% step wait, −0.5% arrivals).
2. **The LLM team consistently improves the emergency fleet over its own base
   policy**: EV duration −2.5% (lower on all 3 seeds), EV mean waiting −39%
   (13.5 vs 22.3 s; lower on all 3 seeds), and −10% EV duration vs A0. With
   ~20 emergency vehicles concurrently active, the corridor
   reviewer/scheduler (axis pinning, queue-aware starts, FCFS sequencing)
   runs at scale: 266–289 emergency calls per run, 0 fallbacks.
3. **Pedestrian waits are best under A4** (mean and p95), consistent with the
   grid finding that holding green phases longer serves crossings; the
   differences are small (p95 10.7 vs 12.3/12.7 s).
4. **LLM operations** (`tables/llm_ops.csv`): 334–356 calls per run
   (66–68 operator, 266–289 emergency; 62–83 fresh calls in the final
   recording segment), 0 fallbacks, 2 retries (invalid JSON, recovered).
   Fresh-call latency: median 24.6–26.6 s, p90 43–52 s, max ~90 s. **~30k
   input tokens per call**: with ~20 active EVs the snapshot and corridor
   views change on nearly every call, so provider prompt caching barely
   helps (~0.2–0.3M cached of 1.7–2.6M input tokens per seed). Token/latency
   counters cover fresh calls only (replayed checkpoint calls carry no usage).
5. **Decision excerpts** (all from seed 1's recorded log).

   *Multi-EV corridor plan across N-phase junctions (t=26035):*

   ```
   emergency [preempt cluster_135794_135910 NS eta 5.6 s; 142742 EW eta 22.5 s;
             release 148690]  note: "148690: phase None -> NS (EV approach)"
   explanation: "Kept the blocked cluster preempt for special_1-2_31, protected the
             green at 142742 for special_1-3_286, and released stale 148690."
   ```

   *Exact-group pinning + FCFS sequencing when two EVs need one junction
   (t=26174, directive `phase_index: 2` selects the S-set of 142742):*

   ```
   note: "142742: special_1-1_115 start delayed to 12.9s (serve the earlier
         arrival first)"
   accepted: 142742 EW (special_1-1_115), 142742 NS phase_index=2
         (special_1-3_187), cluster NS, 146640 NS
   ```

   *Operator favors starved axes while sparing the EV corridor (t=25991):*

   ```
   operator [bias 142742 ns=1.3 ew=0.7; bias 137525 ns=1.2 ew=0.85]
   explanation: "Starved NS at 142742 and the growing NS queue at 137525 get favor,
         while EV-corridor TLSs 146640 and cluster_135794_135910 stay untouched."
   ```

## Limitations

- **17-minute window** (1000 steps) instead of 30 min; cold start at 07:00
  (all arms start empty, equally). One hour of real morning peak would need
  ~4–5x the LLM budget.
- **1.0 s step length**, no sublane model; lateral behavior is coarser than
  reference MoST runs (0.25 s).
- **No Pedestrian agent arm** on Monaco: `serve_ped` never fires here, and
  pedestrian KPIs are personinfo aggregates only.
- **EV KPIs count completed EV trips** (14–17 per window); EVs departing near
  the window end are not in `<tripinfo>`.
- **Axis labels** on 2-set junctions follow program order, not the compass;
  cosmetic for the LLM interface but worth knowing when reading snapshots.
- **Third green sets** (protected turns / one-way phases) are served by the
  k-way base policy; the Operator/Emergency layer addresses axes (plus the
  reviewer's exact-group `phase_index` for pre-emption), so bias/hold
  directives cannot target a single sibling group.
- **Prompt size**: ~30k input tokens per call under dense EV traffic (see
  Finding 4). Pruning the per-EV `next_tls` list or capping concurrent EVs in
  the snapshot is the obvious future-work lever for cost.
- **Budget-discipline note**: the recorded runs used two segments separated by
  an explicit stop/resume; strict replay confirms the resumed segments produce
  the same decisions as a single run would have.
