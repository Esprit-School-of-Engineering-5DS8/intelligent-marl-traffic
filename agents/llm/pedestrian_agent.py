"""
agents/llm/pedestrian_agent.py
Pedestrian agent (plan Phase 5, section 4.5): crossing-window planning on top
of the shared LLM transport.

The agent emits `serve_ped` directives for crossings where people are waiting.
`serve_ped` guarantees the axis whose green phase serves the crossing runs at
least `min_green_s` (see DirectiveLayer): it forces the axis if another one is
running and blocks switching away while the window is owed.

Role-specific additions over `LLMAgent`:

1. **Reviewer.** A directive survives only when `(tls, phase)` matches a
   snapshot pedestrian group with waiting people; `min_green_s` is floored so
   a person can actually clear the crossing and the TTL is stretched to cover
   the window. Hallucinated crossings are dropped.
2. **Rule fallback.** When the call fails or proposes nothing usable, the
   longest-waiting crossings (wait >= `rule_wait_s`) are served instead.
3. **`ped_surge` blackboard message.** Waiting groups at/above
   `surge_wait_s` are published so the Operator knows pedestrians are
   accumulating (plan 4.5 inter-agent communication).
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from agents.llm.agent import AgentCall, LLMAgent

MIN_GREEN_S = 18.0        # crossing walk + clearance + start-decision budget
MIN_GREEN_FLOOR_S = 15.0  # reviewer floor (short windows starve crossings)
MAX_TARGETS = 2           # crossings served per tick
RULE_WAIT_S = 15.0        # rule fallback: serve waits beyond this
SURGE_WAIT_S = 20.0       # publish a ped_surge message beyond this
DEFAULT_TTL_S = 40.0
MAX_TTL_S = 60.0

GroupKey = Tuple[str, str]


def _as_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return float(value)


class PedestrianAgent(LLMAgent):
    def __init__(self, client, system_prompt: Optional[str] = None,
                 max_retries: int = 1,
                 min_green_s: float = MIN_GREEN_S,
                 min_green_floor_s: float = MIN_GREEN_FLOOR_S,
                 max_targets: int = MAX_TARGETS,
                 rule_wait_s: float = RULE_WAIT_S,
                 surge_wait_s: float = SURGE_WAIT_S,
                 rule_fallback: bool = True):
        super().__init__("pedestrian", client, system_prompt, max_retries)
        self.min_green_s = float(min_green_s)
        self.min_green_floor_s = float(min_green_floor_s)
        self.max_targets = max(1, int(max_targets))
        self.rule_wait_s = float(rule_wait_s)
        self.surge_wait_s = float(surge_wait_s)
        self.rule_fallback = bool(rule_fallback)

    # ── reviewer ────────────────────────────────────────────────────────────

    @staticmethod
    def _groups(snapshot: Mapping[str, Any]) -> Dict[GroupKey, Dict[str, Any]]:
        groups: Dict[GroupKey, Dict[str, Any]] = {}
        for state in (snapshot.get("pedestrians") or ()):
            key = (str(state.get("tls", "")), str(state.get("axis", "")))
            groups[key] = state
        return groups

    def _review_serve_ped(self, raw: Mapping[str, Any],
                          groups: Mapping[GroupKey, Dict[str, Any]],
                          notes: List[str]) -> Optional[Dict[str, Any]]:
        tls_id = raw.get("tls")
        axis = str(raw.get("phase", "")).upper()
        state = groups.get((tls_id, axis))
        if state is None or int(state.get("waiting", 0) or 0) <= 0:
            notes.append(f"{tls_id}/{axis}: dropped, no pedestrians waiting there")
            return None
        fixed = dict(raw)
        fixed["type"] = "serve_ped"
        fixed["phase"] = axis
        min_green = max(_as_float(fixed.get("min_green_s"), self.min_green_s),
                        self.min_green_floor_s)
        min_green = min(min_green, 30.0)
        fixed["min_green_s"] = round(min_green, 1)
        ttl = _as_float(fixed.get("ttl_s"), DEFAULT_TTL_S)
        fixed["ttl_s"] = round(min(MAX_TTL_S, max(ttl, min_green + 10.0)), 1)
        return fixed

    def review(self, t: float, snapshot: Mapping[str, Any], call: AgentCall) -> AgentCall:
        notes: List[str] = []
        groups = self._groups(snapshot)
        directives: List[Dict[str, Any]] = []
        # One serve_ped slot per TLS (the DirectiveLayer keeps one): when the
        # model asks for both crossings of an intersection, keep the longer
        # wait. Serving both back-to-back would make the signal thrash.
        chosen: Dict[str, Tuple[Dict[str, Any], float]] = {}
        order: List[str] = []

        for raw in (call.envelope.get("directives") or ()):
            if not isinstance(raw, Mapping) or raw.get("type") != "serve_ped":
                directives.append(raw)  # the arbiter rejects role violations
                continue
            fixed = self._review_serve_ped(raw, groups, notes)
            if fixed is None:
                continue
            tls_id = str(fixed["tls"])
            wait = float(groups[(tls_id, fixed["phase"])].get("max_wait_s", 0.0) or 0.0)
            existing = chosen.get(tls_id)
            if existing is None:
                chosen[tls_id] = (fixed, wait)
                order.append(tls_id)
            elif wait - existing[1] > 1e-6:
                notes.append(f"{tls_id}: serve_ped phase -> {fixed['phase']} (longer wait)")
                chosen[tls_id] = (fixed, wait)
            else:
                notes.append(f"{tls_id}: duplicate serve_ped for a shorter wait dropped")
        directives.extend(chosen[tls_id][0] for tls_id in order)

        source = "llm"
        if call.failed or not directives:
            fallback = self._rule_directives(groups, notes)
            if fallback:
                source = "rules"
                covered = {(d.get("tls"), str(d.get("phase", "")).upper())
                           for d in directives if isinstance(d, Mapping)}
                directives = list(directives) + [
                    d for d in fallback
                    if (d.get("tls"), d.get("phase")) not in covered]
        if call.failed and not directives:
            source = "rules"

        envelope = dict(call.envelope)
        envelope["directives"] = directives
        if source == "rules" and not envelope.get("explanation"):
            envelope["explanation"] = "rule-based pedestrian-window fallback"

        # Publish waiting surges for the Operator (plan 4.5).
        alerts = [a for a in (call.envelope.get("alerts") or ())
                  if not (isinstance(a, Mapping) and a.get("kind") == "ped_surge")]
        for key in sorted(groups):
            state = groups[key]
            if float(state.get("max_wait_s", 0.0) or 0.0) >= self.surge_wait_s:
                alerts.append({"kind": "ped_surge", "tls": key[0], "axis": key[1],
                               "waiting": int(state.get("waiting", 0) or 0),
                               "max_wait_s": round(float(state["max_wait_s"]), 1)})
        envelope["alerts"] = alerts

        groups_log = [
            {"tls": key[0], "axis": key[1], "waiting": int(groups[key].get("waiting", 0)),
             "max_wait_s": round(float(groups[key].get("max_wait_s", 0.0)), 1)}
            for key in sorted(groups)
        ]
        return AgentCall(
            role=call.role, envelope=envelope, response=call.response,
            error=call.error, prompt_hash=call.prompt_hash,
            attempts=call.attempts, effort=call.effort,
            review={"source": source, "notes": notes,
                    "n_directives": len(directives), "groups": groups_log},
        )

    def ask(self, t: float, snapshot: Mapping[str, Any],
            blackboard: Iterable[Any] = (),
            effort: Optional[str] = None) -> AgentCall:
        call = super().ask(t, snapshot, blackboard, effort)
        return self.review(t, snapshot, call)

    # ── rule fallback ───────────────────────────────────────────────────────

    def _rule_directives(self, groups: Mapping[GroupKey, Dict[str, Any]],
                         notes: List[str]) -> List[Dict[str, Any]]:
        if not self.rule_fallback:
            return []
        candidates = sorted(
            (state for state in groups.values()
             if float(state.get("max_wait_s", 0.0) or 0.0) >= self.rule_wait_s),
            key=lambda s: (-float(s.get("max_wait_s", 0.0)), str(s.get("tls", ""))),
        )[: self.max_targets]
        directives = []
        for state in candidates:
            notes.append(f"{state.get('tls')}/{state.get('axis')}: served by rule fallback")
            directives.append({
                "tls": state.get("tls"), "type": "serve_ped",
                "phase": state.get("axis"), "min_green_s": self.min_green_s,
                "ttl_s": DEFAULT_TTL_S,
            })
        return directives
