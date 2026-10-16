# Monaco Real-World Scenario (MoST)

The **Monaco SUMO Traffic (MoST) Scenario**: a real OSM network of the
Principality of Monaco with 12 signalized junctions, ~1,700 edges, sidewalks,
signalized crossings and multimodal demand (cars, buses, trains, commercial,
pedestrians, and "special" vehicles that are 60% `vClass="emergency"`).

> **Citation:** L. Codecà, J. Härri, *"Towards Multimodal Mobility Simulation
> of C-ITS: The Monaco SUMO Traffic Scenario"*, IEEE Vehicular Networking
> Conference (VNC), 2017.
>
> **License:** MoST is distributed under **GPL-3.0** (see the headers in the
> network/route files). It is bundled here for evaluation only; our own code
> stays under the repository's license.
>
> Integrated from `origin/feature/monaco-real-scenario` (commit `6d84e4a`),
> Phase 6 of the LLM-agents plan.

## Network facts relevant to the controller

| Property | Value |
|---|---|
| Signalized junctions | 12, all with `actuated` programs (minDur 5 s, maxDur 30 s on greens) |
| Green phase sets per junction | 8 junctions × 2 sets, 4 × 3 sets (protected turns / one-way phases) |
| EV sensing | `environment/ev.py` picks up real `vClass=emergency` specials, no synthetic `ev_*` needed |
| Demand in the evaluation window | ~300 commercial + ~140 special vehicles + ~15k persons per 30 min |

`environment.topology.TLSTopology` handles the N-phase programs: each distinct
vehicle-green lane set is a selectable group; groups are clustered into the
NS/EW axes by lane heading for the LLM/directive layer. For controlled arms
(`max_pressure`, `llm_team`) `MultiAgentEnv.build_agents()` first converts the
actuated program to an equivalent **static** copy — on actuated logic SUMO
caps pinned phases at `maxDur` and would take control back. `sumo_default`
keeps MoST's genuine actuated programs (the real baseline).

## Evaluation window (`monaco.llm.sumocfg`)

- `begin=25200` (07:00): the start of a morning peak; the config supports up to
  `end=28800` (30 minutes). The committed Phase 6 evaluation
  (`docs/test/phase6/monaco.md`) used the **first 1000 steps (17 min)** for
  LLM budget/runtime reasons — pass `--steps 1000` to reproduce it. Route
  entries departing before `begin` are discarded by SUMO, so the full
  upstream route files are reused unchanged.
- `step-length=1.0` (MoST recommends 0.25 for lateral fidelity). Approximation,
  documented in `docs/test/phase6/monaco.md`; the sublane model
  (`lateral-resolution`) is dropped because it is meaningless at 1 s.
- `time-to-teleport=120`, `ignore-route-errors`, striped pedestrian model and
  vehicle rerouting as in MoST.

## Running

```bash
# GUI smoke run (MoST programs, no controller)
sumo-gui -c scenarios/monaco/monaco.llm.sumocfg

# Evaluation arms (one SUMO process per run, distinct TraCI ports)
~/.venvs/sumo/bin/python evaluation/run_experiments.py \
    --scenario monaco --arms sumo_default,max_pressure,llm_team \
    --seeds 1,2,3 --steps 1000 --jobs 3          # add --llm openai to record
```

Results land in `results/monaco/<arm>/seed_<n>/`; the consolidated tables and
figures are committed under `docs/test/phase6/`.
