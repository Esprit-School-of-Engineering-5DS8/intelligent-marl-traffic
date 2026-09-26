# 9. Ablations

Same conventions as section 8. Each variant differs from the one above it by one design
choice; all use the same PPO settings, 500 000 agent steps and 3 training runs, except the
reward study (one run, validation seeds only).

## 9.1 Neighbour messages: IND vs COOP

COOP receives from each upstream neighbour the queue heading to it, whether the neighbour
is releasing traffic toward it and its largest phase pressure (ADR-009). Mean travel time
(s) in every cell where both were evaluated:

| Cell | IND | COOP | COOP vs IND |
|---|---|---|---|
| grid4x4, low | 150.8 | 150.8 | 0.0% |
| grid4x4, medium | 161.1 | 161.0 | -0.1% |
| grid4x4, peak | 217.5 | 224.6 | +3.3% |
| grid4x4, rush profile | 184.5 | 186.7 | +1.2% |
| grid4x4, incident | 219.2 | 227.3 | +3.7% |
| grid4x4, sensor faults | 220.4 | 247.7 | +12.4% |
| grid8x8, peak (zero-shot) | 312.7 | 313.1 | +0.2% |
| district, medium | 109.7 | 109.9 | +0.2% |
| district, peak | 158.4 | 159.5 | +0.7% |

- The messages bring no gain in any cell. The largest differences come from one COOP
  training run (t2: 234 s at grid peak, against 218-222 s for t1 and t3 and 214-221 s for
  the three IND runs), i.e. from the spread between training runs, not from the messages.
- Two independent checks show that COOP barely uses them: shuffling the message block
  changes 7% of its decisions and nothing in travel time (section 8.9), and losing up to
  50% of the messages costs +0.5% (section 8.4).
- Our explanation (FAILURES F-009): on 250 m links a platoon released upstream reaches the
  next junction about four decisions later and is already visible on the incoming lanes;
  with two phases and frequent switching there is little to anticipate. Communication
  would pay off where neighbours know something local detectors cannot see in time -
  longer links, more phases, events beyond detection range - and with a mechanism that
  lets an agent weight the neighbours that matter, such as graph attention over the
  messages (CoLight). We leave this to future work.

## 9.2 CO2 weight in the reward: lambda_co2 = 0, 0.5, 1.0

| Variant | travel, medium (s) | CO2, medium (kg) | travel, peak (s) | CO2, peak (kg) |
|---|---|---|---|---|
| COOP (lambda = 0) | 161.0 | 2 270 | 224.6 | 4 190 |
| COOP-ECO (lambda = 0.5) | 160.2 | 2 257 | 215.2 | 4 050 |
| COOP-ECO (lambda = 1.0) | 160.0 | 2 255 | 218.2 | 4 091 |

The penalty reduces travel time and CO2 together (section 8.3). The gain over COOP at peak
(-4.2% travel time, -3.3% CO2 for lambda = 0.5) comes largely from COOP's weak training
run: per training run at peak, COOP-ECO reaches 214-217 s (lambda = 0.5) and 216-222 s
(lambda = 1.0), COOP 218-234 s and IND 214-221 s.
Doubling the weight does not help further. On our networks the CO2 term is a second
congestion signal rather than a competing objective.

## 9.3 Emergency vehicles: learned priority vs rule-based preemption

Each mechanism against its own base (section 8.2, grid4x4 at peak, paired):

| Mechanism | Base | EV delay | Travel time |
|---|---|---|---|
| preemption rule (EV-RULE) | ACT | -61.1% [-68.8, -50.2] | +3.6% [+1.4, +5.8] |
| preemption rule (EV-RULE-MP) | MP | -64.2% [-69.7, -55.3] | +0.4% [-0.5, +1.0] |
| EV block + reward term (COOP-FULL) | COOP | -36.6% [-49.4, -16.6] | -2.7% [-3.7, -1.4] |

The learned mechanism reaches about 60% of the rule's reduction; the rule on Max-Pressure
also keeps the lower travel time. A first version of this comparison set COOP-FULL against
the rule on actuated control only, which attributed the breakdown of actuated control to
preemption (FAILURES F-013).

Weight of the EV term (grid4x4 at peak; one training run per weight, all with training
seed 1, paired by test seed against lambda_ev = 2):

| lambda_ev | EV delay (s) | vs lambda_ev = 2 | Travel time (s) | vs lambda_ev = 2 |
|---|---|---|---|---|
| 1 | 109.7 | +70.4% [+45.7, +98.7] | 226.6 | +4.4% [+3.5, +5.8] |
| 2 (COOP-FULL) | 64.4 | | 217.0 | |
| 4 | 63.3 | -1.6% [-11.8, +9.4] | 220.7 | +1.7% [+0.6, +2.8] |

These runs suggest that a weight of at least 2 is needed: with lambda_ev = 1 the
emergency vehicles lose most of the benefit (110 s, close to COOP's 116 s), while 2 and 4
give the same EV delay. Each weight rests on a single training run, and the spread between
training runs is large (COOP's run t2 is 6% slower than the others at peak, section 9.1),
so this is indicative, not a conclusion; the travel-time differences in particular are
within that spread.

## 9.4 Reward definition and exploration (validation seeds, M3)

Before the main runs we checked whether a different reward or more exploration would close
the gap to Max-Pressure (one training run of 300 000 steps each, validation seeds only;
journal, 2026-09-24). Mean travel time (s):

| Variant | medium | peak |
|---|---|---|
| IND, waiting-difference reward (used) | 162.7 | 211.5 |
| IND, queue-length reward | 161.9 | 212.6 |
| IND, pressure reward (PressLight) | 162.0 | 214.9 |
| IND, entropy bonus 0.01 | 161.8 | 211.9 |
| Max-Pressure | 159.3 | 207.7 |

No variant differs by more than 1.6%: the reward definition is not what separates the
learned agents from Max-Pressure (FAILURES F-007).

## 9.5 Forecast observation (Tier 3)

`coop_forecast` adds the predicted inflow of the next 5 minutes per approach (Ridge model)
to COOP's observation. It matches IND at medium, peak and rush-profile demand (all
differences within +-0.4%, intervals including zero; section 8.6) and does not narrow the
gap to Max-Pressure. The forecast is accurate only to within 25% of the noise floor of
Poisson arrivals, which leaves little for the policy to exploit.
