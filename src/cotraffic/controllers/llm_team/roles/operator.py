"""Operator role: bias and hold directives for routine traffic."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cotraffic.controllers.llm_team.agent import LLMAgent


class OperatorAgent(LLMAgent):
    def __init__(
        self,
        client,
        system_prompt: str | None = None,
        max_retries: int = 1,
        max_tokens: int = 300,
    ) -> None:
        super().__init__(
            "operator", client, system_prompt, max_retries, max_tokens=max_tokens
        )

    def snapshot_for_prompt(self, snapshot: Mapping[str, Any]) -> Mapping[str, Any]:
        view = dict(snapshot)
        view.pop("pedestrians", None)
        view["evs"] = [
            {
                "id": ev.get("id", ""),
                "eta_s": min(
                    (
                        row.get("eta_s")
                        for row in ev.get("next_tls") or ()
                        if row.get("eta_s") is not None
                    ),
                    default=None,
                ),
                "tls": [
                    row.get("tls")
                    for row in ev.get("next_tls") or ()
                    if row.get("tls")
                ],
            }
            for ev in snapshot.get("evs") or ()
        ]
        return view
