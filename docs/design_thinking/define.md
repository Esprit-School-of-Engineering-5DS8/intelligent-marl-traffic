# 2. Define - the problem we solve

## How might we

*How might we use data and intelligent agents to make urban traffic more efficient,
adaptive, and sustainable?* (project brief)

## TEAM - point-of-view statements

Format: *[stakeholder] needs [need] because [insight from the Empathize stage].*

1.
2.
3.

## Technical problem statement

We control the traffic signals of a district. Each signalised intersection is an agent
that, every 5 s, chooses which green phase to show next. The system must reduce delay,
adapt to demand that changes over the hour and to events (incident, emergency vehicle),
and account for people rather than vehicles (buses, pedestrians) and for emissions,
without ever producing an unsafe signal sequence.

Formally this is a decentralised partially observable Markov decision process
(Dec-POMDP) with one agent per intersection:

- state: positions and speeds of all road users (hidden);
- observation of agent *i*: local lane measurements, its phase and timer, messages from
  its neighbours, emergency vehicles, pedestrians and buses near it;
- action: index of the next green phase, filtered by the safety shield;
- reward: decrease of the person-weighted waiting time at the intersection, minus CO2,
  emergency-vehicle and pedestrian waiting penalties;
- objective: maximise the expected discounted sum of rewards of all agents.

## Needs to requirements

| Need (to be confirmed by the Empathize stage) | Requirement | How we measure it |
|---|---|---|
| Shorter and more reliable trips | Lower mean and 95th-percentile travel time than fixed-time and Max-Pressure | Travel time, time loss, P95 waiting |
| Fairness between approaches | No approach starved | Max waiting, Gini of waiting times, shield anti-starvation count |
| Faster emergency response | Emergency vehicles cross with little delay, without blocking everyone else | EV delay vs free-flow; delay of other vehicles |
| People, not vehicles | A bus with 30 passengers weighs more than a car | Person-weighted delay |
| Pedestrian comfort and safety | Bounded pedestrian waits | Pedestrian mean and max waiting time |
| Cleaner air | Fewer stops and less idling | CO2, NOx, fuel, stops per vehicle |
| Safety | No unsafe signal sequence; fewer conflicts | Shield guarantees; SSM conflicts (TTC < 1.5 s); hard braking |
| Robustness | Keeps working with bad sensors or lost messages | Performance under sensor noise and communication dropout |
| Deployability | Runs on cheap hardware at the roadside | Inference latency per decision |

## Success criteria

Defined before running the experiments (see `docs/report_outline.md`, research
questions RQ1-RQ6): a method "wins" on a metric only if the difference with the best
baseline is significant (Mann-Whitney U, Holm-corrected, alpha = 0.05) over 5
evaluation seeds, and we report the effect size (Cliff's delta).
