# ADR-002: Environment interface - our own PettingZoo environment on top of TraCI/libsumo

- Status: accepted
- Date: 2026-09-24

## Context

The agents need a multi-agent environment around SUMO. The obvious candidate is
`sumo-rl` (PettingZoo parallel API), which we installed (version 1.4.5, the latest
release) and read before deciding. Our design needs:

1. a maximum green time and an anti-starvation rule, with every override counted
   (safety shield, ADR-003);
2. a new demand realisation at every training episode (random demand level and seed);
3. neighbour messages, emergency-vehicle, pedestrian and bus features;
4. one action space shared by intersections with different phase counts, where a padded
   action means "keep the current phase";
5. the classical baselines (fixed-time, actuated) run through exactly the same
   measurement code as the learning agents.

## What we found in sumo-rl 1.4.5

- `max_green` is documented as "currently ignored" in `SumoEnvironment`'s docstring.
- The route file is fixed when the environment is created (`self._route`), so demand
  cannot change between episodes without patching private attributes.
- The minimum green is applied silently inside `TrafficSignal.set_next_phase`; there is
  no hook for anti-starvation and no count of overridden actions.
- Each traffic signal gets its own `Discrete(num_green_phases)` space, so heterogeneous
  intersections need an external padding wrapper whose out-of-range actions do not
  mean "keep the phase".
- With `fixed_ts=True` the number of phases is guessed as `len(phases) // 2`.

## Options considered

1. Use sumo-rl and patch or subclass its internals.
2. Write a small environment of our own on TraCI/libsumo, reusing sumo-rl's proven
   idea for phases (green phases taken from the SUMO program, yellow transitions
   computed between every pair of greens).

## Decision

Option 2. `src/cotraffic/envs/` contains the environment (`traffic_env.py`), the
intersection model (`intersection.py`), the shield (`shield.py`), observations and
rewards. It implements the PettingZoo `ParallelEnv` API and passes PettingZoo's
`parallel_api_test` (tests and `make smoke`). sumo-rl is not a dependency.

## Consequences

- About 1 000 lines of code that we own and test; every behaviour listed above is
  explicit and unit-tested (signal-sequence test replays SUMO's real signal states).
- Programs with pedestrian crossings contain a "pedestrian clearance" variant of each
  vehicle green. We merge green states that are identical on vehicle signals, so a
  4-arm grid junction has 2 actions (north-south, east-west), not 4 (see FAILURES.md).
- With `controlled=False` the same class steps SUMO without touching its programs,
  which is how the fixed-time and actuated baselines are measured.
