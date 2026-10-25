"""A language model in the decision loop of the traffic-signal agents.

Three levels (docs/LLM_DESIGN.md):

* strategic - an advice source (local LLM, rules, or random placebo), called rarely, on
  events and every few minutes of simulated time;
* tactical - the PPO policy, every 5 s, whose logits receive a bounded bias toward the
  advised phases while the advice is active;
* safety - the shield, unchanged, which turns every request into a safe phase.

An advice never applies before the latency of the call that produced it has elapsed in
simulated time, and the policy decides alone whenever there is no valid advice.
"""
