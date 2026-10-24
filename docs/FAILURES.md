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

## F-009 - Neighbour messages did not improve the agents (2026-09-25) [report]

- **Tried:** COOP agents receive, from each upstream neighbour, the queue heading to them,
  whether the neighbour is releasing traffic toward them and its largest phase pressure.
- **Evidence:** COOP = IND at low and medium demand (differences below 0.1%), -3.3% at peak
  and -1.2% on the rush profile, not significant; the spread between COOP training seeds
  (218-234 s at peak) is larger than the IND-COOP difference.
- **Diagnosis (hypotheses, to be discussed in the report):** (1) on 250 m links a platoon
  released upstream reaches the next junction in about 20 s, i.e. four decisions later,
  and is already visible on the incoming lanes that every agent observes; (2) with two
  phases and near-maximal switching (F-007) the decision space leaves little room for
  anticipation; (3) twelve more inputs slightly slow learning at the same budget.
- **Lesson:** communication is only worth its cost when neighbours know something the
  local detectors cannot see soon enough - longer links, several phases, or events outside
  the detection range. The comm-dropout and district results test the same question.
- **Confirmed (2026-09-26):** losing 10-50% of the messages changes COOP's travel time by
  +0.5% (paired on training run and test seed, CI within +-2%), and shuffling the message
  block changes 7% of COOP's decisions with no effect on travel time (fig. 12). In the
  9 cells where both were run, COOP is between 0.1% faster and 12% slower than IND (the
  district and grid8x8 included), and never better than the best baseline. We keep the
  COOP results as they are (no retraining).
- **Future work:** learned, selective communication - attention over the neighbours'
  messages (e.g. graph attention, as in CoLight, Wei et al. 2019), so that an agent can
  weight the neighbours that matter, instead of a fixed concatenation of all messages.

## F-010 - An incident that did not disturb anything (2026-09-25)

- **Tried:** a vehicle stopped for 15 min at 40% of a main approach's right lane.
- **Evidence:** +2-4% halting vehicles during the incident, travel times unchanged, for every
  controller (journal, 2026-09-25).
- **Diagnosis:** mid-link, vehicles merge past the obstacle and still use both lanes at the
  stop line; a single lane of free flow carries more than the approach's green-time share.
- **Fix / lesson:** crash next to the stop line (85% of the link) and local metrics
  (vehicles crossing the blocked approach, queue on that approach). Check that a scenario
  actually stresses the system before comparing controllers on it; a scenario without
  effect cannot discriminate anything.

## F-011 - Pedestrians on a network without sidewalks (2026-09-25)

- **Tried:** the same pedestrian flows on the OSM district as on the grid, including in the
  training episodes of COOP-FULL and in the runs that estimate the reward scales.
- **Evidence:** Max-Pressure at peak, validation seed 1000: 1 026 s mean travel time and 108
  teleports with pedestrians vs 134 s and 1 without; 92 of 112 edges carry pedestrians on
  the carriageway; COOP-FULL's district training did not improve at peak.
- **Diagnosis:** an import artefact (sidewalks guessed only on slow roads), not traffic.
- **Fix / lesson:** scenario excluded on the district, reward scales re-estimated, district
  runs retrained (about 1.5 h of compute lost). Look at what a scenario does to the
  simulation before training on it - the symptom (a flat training curve) appeared far from
  the cause.
- **Later (2026-10-04, demonstration only):** the cause is netconvert's default of guessing
  sidewalks and crossings only on roads up to 50 km/h. `real_district_ped` rebuilds the
  district from the same extract with both guessed on every street (106 of 112 edges with
  a sidewalk, 57 crossings, one connected walking network). Max-Pressure with pedestrians
  there: 160 s mean travel time in a quick peak episode, no collapse. It is used by the
  demo with the agents trained on real_district and is not part of the evaluation.

## F-012 - The anti-starvation rule only protects movements it can see (2026-09-26) [report]

- **Tried:** sensor-fault scenario (20% of lane detectors report 0) with every controller
  behind the same safety shield.
- **Evidence:** Max-Pressure, evaluation seed 3: 359 s mean travel time (199 s without
  faults), 18 teleports, a maximum wait of 1 762 s, and 0 anti-starvation interventions.
- **Diagnosis:** the shield serves a movement that has been red longer than `max_red` only if
  it has *detected* demand, and ends a green at `max_green` only if another phase has
  detected demand. A movement whose detectors have all failed is invisible to both rules
  and to Max-Pressure. The learned agents are less affected because they switch at a steady
  rhythm.
- **Fix / lesson:** we keep the shield as it is so that every result uses the same rules,
  and discuss this in the report. Field controllers handle it with detector diagnostics: a
  failed detector is placed on recall, i.e. its movement is served every cycle as if it
  had demand. A fault-tolerant shield would do the same (a demand-independent `max_red`
  for movements with a failed detector).

## F-013 - A preemption baseline built on a collapsing controller (2026-09-26) [report]

- **Tried:** RQ2 compared COOP-FULL with EV-RULE, rule-based preemption on top of actuated
  control, and reported EV-RULE's +36% travel time against Max-Pressure as the cost of
  preemption.
- **Evidence:** found when reviewing the draft: actuated control alone is 278.0 s at grid
  peak against 211.6 s for Max-Pressure; preemption adds 3.6% to actuated control. The
  same rule on Max-Pressure (EV-RULE-MP) cuts the EV delay by 64% for +0.4% of travel
  time, and beats COOP-FULL on both criteria (38 s vs 74 s EV delay, 212 s vs 219 s).
- **Diagnosis:** the comparison mixed the effect of the mechanism with the effect of the
  controller it runs on, which flattered the learned agent.
- **Fix / lesson:** EV-RULE-MP added as a baseline; every mechanism is reported against
  its own base controller. Compare a mechanism with the same mechanism on the strongest
  base available before crediting the learned agent.

## F-014 - COOP-FULL gridlocks with pedestrians at peak (2026-09-27) [report]

- **Tried:** COOP-FULL (pedestrian block and pedestrian term in the reward, trained with
  pedestrians in every episode) evaluated at peak demand with pedestrians (extended
  matrix, 3 training runs x 5 test seeds).
- **Evidence:** 4 of 15 runs gridlock (mean travel time 441-638 s; 34 to 1 140 vehicles
  still in the network at the end, 24.8 teleports per run on average); the other 11 runs
  are at 235-306 s, close to Max-Pressure (237-297 s), and every training run is affected
  at least once. No other controller gridlocks in this cell (Max-Pressure 0.2 teleports
  per run).
- **Diagnosis (hypothesis, not verified):** at peak, serving the crossings the reward
  asks for costs vehicle capacity; once queues spill back to the upstream junction the
  network locks, and neither the shield nor the observation has any notion of spillback.
  Training episodes draw the demand level at random, so saturated peak episodes with
  pedestrians are a minority of what the policy saw.
- **Fix / lesson:** reported as a failure of the learned multi-objective agent; a
  deployment would need a spillback guard in the shield and training weighted toward
  saturated conditions. A mean over 15 runs hides such tails: look at the worst runs
  and at unfinished vehicles, not only at the mean.

## F-015 - A spillback guard that never acted (2026-10-22)

- **Tried:** two optional shield rules for F-012 and F-014, off by default: a spillback
  guard (a phase whose waiting vehicles can only enter exit lanes above 80 % of their
  capacity is not served while another phase can move traffic) and detector recall
  (movements whose detector failed count as having demand). Validation seeds 1000-1004,
  106 runs, `scripts/validate_methods.py`.
- **Evidence:** 0 guard interventions in 106 runs, results identical with and without the
  guard. In a gridlocking run (Max-Pressure, sensor faults, seed 1001) exit lanes were
  blocked 407 times, with densities up to 1.14, but never all exits of a phase at once:
  with two lanes per approach one exit of the phase is almost always free. In normal runs
  exit density never exceeded 0.66, so 0.8 was also an arbitrary threshold. Under sensor
  faults, 28 of the 32 failed detectors were on exit lanes: they read 0 vehicles, so
  Max-Pressure sees those exits as empty and sends traffic into them; recall of approach
  detectors cannot prevent that, and the anti-starvation rule never triggered.
- **Diagnosis:** the rule required a fully blocked phase, a state the network reaches only
  after it has locked; and the sensor-fault gridlock comes from failed exit detectors
  read as empty lanes, not from starved movements.
- **Fix / lesson:** kept in the code, off by default, as a documented negative result. A
  useful guard would act on partially blocked phases with a threshold set from measured
  densities, and a failed detector should be treated as unknown (imputed from neighbouring
  lanes) rather than as zero. Check that a new safety rule actually fires before
  evaluating its effect.
