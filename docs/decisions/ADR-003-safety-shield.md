# ADR-003: Safety shield between controllers and signals

- Status: accepted
- Date: 2026-09-24

## Context

A learned policy can output any phase at any time. Real controllers must respect
minimum greens, yellow clearance, maximum greens and never starve a movement. The jury
will rightly ask what prevents the agent from producing an unsafe or unacceptable
signal sequence.

## Options considered

1. Reward shaping only (penalise short greens, long reds): no guarantee, the agent may
   still violate the rules during exploration or in unseen situations.
2. Action masking inside the policy: guarantees validity but ties the rules to the
   learning algorithm and does not apply to the Max-Pressure baseline.
3. A separate shield module that turns the proposed phase into the executed phase.

## Decision

Option 3 (`src/cotraffic/envs/shield.py`), pure logic, applied to every learning or
pressure-based controller (IND, COOP, COOP-ECO, COOP-FULL, Max-Pressure). Rules in
priority order, with the values of `configs/protocol.yaml`:

| Rule | Value | Effect |
|---|---|---|
| Invalid (padded) action | - | keep current phase |
| Minimum green | 10 s | a green cannot be cut earlier |
| Anti-starvation | 90 s | a movement with waiting demand red for longer is served next |
| Maximum green | 60 s | a green is cut if another phase has demand |
| Yellow | 3 s | produced by the intersection model, never by the policy |

Crossings that lose their green turn red at the start of the vehicle yellow, so no
pedestrian starts crossing during a transition.

Two interpretation choices, both deliberate:

- Anti-starvation and maximum green only act when there is demand elsewhere. Forcing a
  phase for an empty approach would waste green time without any safety benefit; this
  mirrors how actuated controllers treat max-out with no conflicting call.
- Decisions happen every 5 s and yellow lasts 3 s, so the effective minimum green is
  12 s (switch at t, green from t+3, next allowed switch at t+15).

## Consequences

- No action sequence can produce an unsafe signal sequence; `tests/test_shield.py`
  checks every rule and an exhaustive grid of states, and `tests/test_env.py` replays
  the real SUMO signal states of a random-policy episode (no green-to-red without
  yellow, no green shorter than the minimum).
- Interventions are counted per reason and reported as a safety metric. With a random
  policy on grid4x4 (1 h), about 25% of decisions are min-green overrides, which is the
  expected behaviour of a policy that ignores timing.
