# What failed, and what we learned

Every approach that failed or underperformed, with the evidence and the lesson. Newest
entries at the bottom. Negative results that belong in the report are marked **[report]**.

## F-001 - Treating every green state of SUMO's program as an action (2026-09-24)

- **Tried:** the first version of the intersection model used every distinct green
  state of the default SUMO program as a candidate phase (the approach of sumo-rl).
- **Evidence:** on our grid junctions (with crossings) this gave 4 actions per
  junction, while there are only 2 vehicle movements groups (north-south, east-west).
  netconvert adds, for each vehicle green, a short variant where only the crossings are
  red ("pedestrian clearance"); `env.reset` failed our padding check (4 > 2).
- **Diagnosis:** pairs of actions were identical for vehicles; half of the action space
  would have been redundant and the random policy would have switched uselessly.
- **Fix / lesson:** merge green states that are identical on vehicle signals and keep
  the variant with the most greens (`envs/intersection.py::green_states`, tested in
  `tests/test_phase_logic.py`). Always inspect the generated signal programs before
  designing the action space.

## F-002 - Latest library versions dropped Python 3.10 (2026-09-24)

- **Tried:** pinning the newest releases installed on the team laptop (numpy 2.5.3,
  scipy 1.18.1, pandas 3.0.6, ...).
- **Evidence:** PyPI metadata: numpy 2.5.3 and scipy 1.18.1 require Python >= 3.12,
  pandas 3.0.6 and scikit-learn 1.9.1 require >= 3.11.
- **Lesson:** Kaggle and Colab images do not always ship the newest Python. We pinned
  the newest versions that still support Python 3.10 (numpy 2.2.6, scipy 1.15.3,
  pandas 2.3.3, scikit-learn 1.7.2, matplotlib 3.10.9) and re-ran the full test suite.

## F-003 - Importing the district's signals from OpenStreetMap alone (2026-09-24)

- **Tried:** netconvert with `--tls.guess-signals` on central Tunis, then netconvert's own
  signal guessing (`--tls.guess`) at several thresholds.
- **Evidence:** OSM tags only 72 signal nodes in the whole of greater Tunis; the district
  gave 3 signalised junctions (5 without discarding mid-block crossings). Guessing gave
  either nothing new on the arterial network or 20-22 signals, most of them on
  residential streets.
- **Diagnosis:** incomplete OSM mapping, not a property of the city.
- **Fix / lesson:** keep the arterial network and signalise the junctions where two main
  avenues meet through an explicit, reviewable list (`osm.tls_set`, ADR-006). The team's
  field observation is the ground truth to correct that list.

## F-004 - Fixed-time plans from SUMO's tlsCycleAdaptation.py (2026-09-24)

- **Tried:** SUMO's Webster script on our networks.
- **Evidence:** on grid4x4 (at the first, uncalibrated demand of 2 600 veh/h) it returned four
  greens of 10 s per junction; its `--verbose --write-critical-flows` output lists program
  phases 0, 1, 3 and 4 as separate phases, i.e. each vehicle green *and* its short
  pedestrian-clearance variant receive their own share of the cycle.
- **Fix / lesson:** our own Webster implementation on the merged phases
  (`controllers/programs.py`, tested in `tests/test_webster.py`). Checked afterwards that
  its plan beats longer-cycle plans (journal, M1).

## F-005 - Random origin-destination pairs on a real street network (2026-09-24)

- **Tried:** the grid demand generator (any entry to any exit) on the district.
- **Evidence:** duarouter aborted ("No connection between edge ... found"); pedestrians made
  SUMO stop with a fatal error at insertion.
- **Diagnosis:** one-way streets make the network connected but not strongly connected, and
  the sidewalk network has two separate pieces.
- **Fix / lesson:** draw car trips only among reachable entry/exit pairs and pedestrian
  walks inside the largest connected sidewalk component (`reachable_exits`,
  `walkable_component`). Route caches now carry a generator version so that stale files
  are never reused after such a fix.
