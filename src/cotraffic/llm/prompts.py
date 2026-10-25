"""Versioned prompts of the advisor (configs/prompts/), and the messages sent to the model.

The state is placed between <state> tags and the system prompt says it is data: values
or texts inside it (e.g. an incident description) can never act as instructions.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from cotraffic.paths import REPO_ROOT

PROMPTS = REPO_ROOT / "configs" / "prompts"
TECHNIQUES = ("zero", "brief", "few")


@dataclass
class Prompt:
    version: str
    technique: str
    system: str
    examples: list[tuple[str, str]] = field(default_factory=list)  # (state text, advice JSON)
    reason_max: int = 60

    @property
    def id(self) -> str:
        """Version, technique and a hash of the exact text (stored in every result row)."""
        digest = hashlib.sha256(
            (self.system + json.dumps(self.examples) + str(self.reason_max)).encode("utf-8")
        ).hexdigest()[:8]
        return f"{self.version}/{self.technique}/{digest}"

    def messages(self, state_text: str) -> list[dict[str, str]]:
        msgs = [{"role": "system", "content": self.system}]
        for state, advice in self.examples:
            msgs.append({"role": "user", "content": wrap(state)})
            msgs.append({"role": "assistant", "content": advice})
        msgs.append({"role": "user", "content": wrap(state_text)})
        return msgs


def wrap(state_text: str) -> str:
    # tags inside the data are neutralised so that data cannot close the block
    clean = state_text.replace("<state>", "(state)").replace("</state>", "(/state)")
    return f"<state>\n{clean}\n</state>"


DEFAULT_VERSION = "advisor-v2"


def load(version: str = DEFAULT_VERSION, technique: str = "zero") -> Prompt:
    if technique not in TECHNIQUES:
        raise ValueError(f"technique must be one of {TECHNIQUES}")
    cfg = yaml.safe_load((PROMPTS / f"{version}.yaml").read_text(encoding="utf-8"))
    tech = cfg["techniques"][technique]
    system = cfg["system"].rstrip() + "\n" + tech["reason"]
    examples: list[tuple[str, str]] = []
    if "examples" in tech:
        path = REPO_ROOT / tech["examples"]
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    ex = json.loads(line)
                    advice = ex["advice"]
                    if not isinstance(advice, str):
                        advice = json.dumps(advice, separators=(",", ":"))
                    examples.append((ex["state"], advice))
    return Prompt(
        version=cfg["version"],
        technique=technique,
        system=system,
        examples=examples,
        reason_max=int(tech.get("reason_max", 60)),
    )


def examples_path(version: str = DEFAULT_VERSION) -> Path:
    return PROMPTS / f"{version}-examples.jsonl"
