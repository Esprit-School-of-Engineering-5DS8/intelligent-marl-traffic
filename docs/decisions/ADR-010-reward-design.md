# ADR-010: Reward design and weights

- Status: accepted (weights to be confirmed by the sensitivity check, journal M5)
- Date: 2026-09-24

## Context

The reward defines what "good" means for the agents. It must be local (computable at the
intersection), dense (feedback every 5 s) and aligned with the metrics of the evaluation,
and it must let us trade travel time against CO2, emergency and pedestrian priority.

## Decision

    r = -Δ(person-weighted waiting)/n_wait - λ_co2 · CO2/n_co2 - λ_ev · EVwait/n_ev - λ_ped · PEDwait/n_ped

clipped to [-5, 5], where:

- `Δ(person-weighted waiting)` is the change over the decision interval of the waiting
  time accumulated by vehicles on the intersection's incoming lanes, counting only the
  waiting done since they reached those lanes (an agent is not charged for delay caused
  upstream). With person weighting (COOP-FULL) a bus counts 30 persons, a car 1.2;
- `CO2` is the mass emitted on the incoming lanes during the interval;
- `EVwait` is the waiting time of emergency vehicles on the incoming lanes during the
  interval; `PEDwait` the pedestrian-seconds of waiting at the crossings;
- the `n_*` scales come from Max-Pressure runs on training demand
  (`python -m cotraffic calibrate`, `configs/reward_norm/`): the standard deviation of the
  waiting term, the mean CO2 per decision, and the mean *non-zero* EV and pedestrian
  terms (they are zero most of the time; their scale must reflect an event).

| Variant | λ_co2 | λ_ev | λ_ped | person-weighted |
|---|---|---|---|---|
| IND, COOP | 0 | 0 | 0 | no |
| COOP-ECO | 0.5 or 1.0 | 0 | 0 | no |
| COOP-FULL | 0.5 | 2.0 | 0.5 | yes |

Why these weights: after normalisation every term is of order 1, so λ expresses relative
importance directly. Emergency waiting weighs 2 because a stopped ambulance is the most
costly event we model; CO2 and pedestrians at 0.5 so that they shape but do not dominate
the delay objective. COOP-ECO at two values of λ gives the Pareto front (RQ3).

## Consequences

- Over an episode the undiscounted sum of the waiting term telescopes; with discounting
  the agent minimises the discounted waiting present at its intersection, which is what
  we want. We checked that rewards are not dominated by clipping (first episodes: mean
  reward about -0.003 per decision).
- A sensitivity check on λ_ev and λ_co2 is part of M5.
