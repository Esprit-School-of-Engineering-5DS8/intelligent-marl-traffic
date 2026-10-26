"""The advisor's settings, read from configs/llm.yaml (the single place where they are set)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from cotraffic.llm.advised import AdvisorConfig
from cotraffic.llm.client import Options
from cotraffic.paths import REPO_ROOT

CONFIG = REPO_ROOT / "configs" / "llm.yaml"


@dataclass(frozen=True)
class LlmSettings:
    model: str
    quantization: str
    options: Options
    prompt_version: str
    technique: str
    vote: int
    vote_temperature: float
    advisor: AdvisorConfig


def load_settings(path: Path = CONFIG) -> LlmSettings:  # [Exigence 3] lit configs/llm.yaml
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    model, sampling, prompt, advisor = cfg["model"], cfg["sampling"], cfg["prompt"], cfg["advisor"]
    options = Options(
        temperature=float(sampling["temperature"]),
        top_p=float(sampling["top_p"]),
        top_k=int(sampling["top_k"]),
        repeat_penalty=float(sampling["repeat_penalty"]),
        num_ctx=int(sampling["num_ctx"]),
        num_predict=int(sampling["num_predict"]),
        seed=int(sampling["seed"]),
        timeout_s=float(sampling["timeout_s"]),
        keep_alive=str(model["keep_alive"]),
    )
    return LlmSettings(
        model=str(model["name"]),
        quantization=str(model["quantization"]),
        options=options,
        prompt_version=str(prompt["version"]),
        technique=str(prompt["technique"]),
        vote=int(prompt["vote"]),
        vote_temperature=float(prompt["vote_temperature"]),
        advisor=AdvisorConfig(
            beta=float(advisor["beta"]),
            period_s=float(advisor["period_s"]),
            min_gap_s=float(advisor["min_gap_s"]),
            latency=str(advisor["latency"]),
            cache=bool(advisor.get("cache", False)),
        ),
    )
