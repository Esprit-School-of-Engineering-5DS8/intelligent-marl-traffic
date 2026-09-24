# ADR-006: Real district and heterogeneous intersections

- Status: accepted (district is a placeholder until the team confirms the area)
- Date: 2026-09-24

## Context

The project needs a real district of 6-10 signalised intersections imported from
OpenStreetMap. The project inputs did not name the city yet. Real intersections differ:
number of approaches, lanes, phases and crossings.

## Decision - district

- Placeholder: central Tunis, arterial network around Avenue Mohamed V, Avenue Habib
  Bourguiba and Rue Jean Jaures (`configs/networks/real_district.yaml`). The OSM extract
  is versioned next to the network so the build is reproducible.
- Only roads from tertiary upwards are kept: residential streets are not signalised and
  would triple the network without adding decisions.
- OSM tags very few signals in Tunis (FAILURES F-003). Signals come from the OSM tags plus
  an explicit list of junctions where two main avenues meet (`osm.tls_set`); the result is
  7 signalised junctions. The list is meant to be checked on site by the team.
- Trips are drawn only between entry and exit roads that are connected in the one-way
  network; pedestrians only inside the largest connected sidewalk network (F-005).

## Decision - one policy for heterogeneous intersections

Parameter sharing needs identical observation and action spaces for every agent:

- **Lanes:** fixed slots, `lanes_per_side` per side (N, E, S, W), filled from the rightmost
  lane; extra lanes on a side are averaged into the last slot. A slot therefore means the
  same thing at every intersection.
- **Actions:** `Discrete(max_phases)`. An index beyond the intersection's phases is an
  invalid action that the shield turns into "keep the current phase" and counts.
- **Phase meaning:** because phase *k* of one intersection is not phase *k* of another,
  the observation contains, for every phase, the queue it would serve and its pressure.
  The policy can tell what each action does without knowing the intersection
  (the idea behind FRAP and MPLight's phase-demand features).
- Padding values are part of the network config and checked at reset: an intersection
  larger than the padding stops the run with an explicit error.

## Consequences

- grid4x4 and grid8x8 share the same padding (2 lanes per side, 2 phases), which is what
  makes zero-shot evaluation on grid8x8 possible.
- District: 3 lanes per side, 3 phases, 4 crossings; its policies are trained separately.
- If the team changes the area, only the config changes; `tls_set`, bus line and incident
  edges must be revised because they are street-specific.
