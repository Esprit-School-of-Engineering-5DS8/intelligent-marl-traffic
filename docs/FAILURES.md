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
