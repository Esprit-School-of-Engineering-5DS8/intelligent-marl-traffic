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

## F-006 - SuperSuit and Stable-Baselines3 versions disagree on the vector-env API (2026-09-24)

- **Tried:** the documented pipeline `pettingzoo_env_to_vec_env_v1` + `concat_vec_envs_v1(...,
  base_class="stable_baselines3")` with `PPO(..., seed=s)`.
- **Evidence:** `AttributeError: 'ConcatVecEnv' object has no attribute 'seed'` (SB3 2.9 seeds
  environments through `VecEnv.seed`); SuperSuit also needs a `render_mode` attribute on the
  environment, and never sets `TimeLimit.truncated`, so SB3 would treat the end of every
  episode as a real termination.
- **Fix / lesson:** we seed Python/NumPy/PyTorch and our episode generator explicitly, add
  `render_mode`, and mark time-limit ends in the environment's `infos`. Read the glue code
  between libraries: none of these problems raises an error at the right place, and the
  last one silently biases the value estimates.

## F-007 - Changing the reward did not close the gap with Max-Pressure (2026-09-24) [report]

- **Tried:** after IND reached Max-Pressure's waiting time but not its travel time, three
  alternatives at the same budget: queue-length reward, pressure reward (PressLight),
  entropy bonus 0.01.
- **Evidence:** on validation seeds all four IND variants are within 1.6% of each other
  (medium 161.8-162.7 s, peak 211.5-214.9 s) and about 2% behind Max-Pressure (159.3 / 207.7 s).
  Every variant converges to the same behaviour: a switch at almost every opportunity the
  shield allows, which Max-Pressure also does on this network.
- **Diagnosis:** with 2-phase junctions and 250 m links the room for improvement over a
  well-behaved pressure rule is small; what a local agent can learn is close to what
  Max-Pressure already does. Better rewards do not add information the agent lacks.
- **Lesson:** the lever is information (neighbour messages, COOP) and richer decisions, not
  the reward. This motivates the IND vs COOP ablation (RQ1) and is itself a result: a simple
  classical controller is a strong baseline that learning does not beat easily.

## F-008 - Forecast evaluated on the simulation's cool-down (2026-09-24)

- **Tried:** chronological split at minute 60 of the 90-minute evaluation runs.
- **Evidence:** persistence beat Ridge and gradient boosting by a wide margin (MAE 11.0 vs
  14.9 / 16.6) in that split, while gradient boosting was best on held-out seeds (5.6).
- **Diagnosis:** the test window included the 15-minute cool-down, during which the protocol
  stops all new demand - an artefact that never occurs on a street and that the time-of-hour
  feature had never seen.
- **Fix / lesson:** forecasting targets are restricted to the demand period. Check what the
  test set contains before comparing models; an unexpected winner is a signal to look at the
  data, not a result.
