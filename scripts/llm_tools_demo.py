"""Function-calling demo: the model reads a validation situation through the read-only
tools, then calls submit_advice; every tool call, its arguments and its result are printed.

    python scripts/llm_tools_demo.py [--kind emergency] [--model qwen2.5:3b] [--count 1]

The situations come from validation seed 1000 (scripts/llm_situations.py). Without the
live environment, get_neighbors and forecast_inflow have no data (empty results).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cotraffic.llm.client import Ollama
from cotraffic.llm.prompts import load
from cotraffic.llm.rollout import Stored
from cotraffic.llm.settings import load_settings
from cotraffic.llm.sources import ToolLlmSource
from cotraffic.paths import RESULTS_DIR

SITUATIONS = RESULTS_DIR / "tmp" / "llm" / "situations" / "validation"


def main() -> None:
    settings = load_settings()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--kind", default="emergency")
    parser.add_argument("--model", default=settings.model)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--log", type=Path, default=None)
    args = parser.parse_args()

    lines: list[str] = []

    def out(text: str = "") -> None:
        print(text, flush=True)
        lines.append(text)

    client = Ollama(args.model, settings.options)
    client.warm_up()
    source = ToolLlmSource(client, load(settings.prompt_version, settings.technique))
    stored = [
        s
        for s in (Stored.load(p) for p in sorted(SITUATIONS.glob("*.json")))
        if any(e["kind"] == args.kind for e in s.situation.events)
    ][: args.count]
    for s in stored:
        out(f"== Situation {s.id}")
        for line in s.situation.to_text().splitlines():
            if line.split(" ")[0][:1] not in "ABCD" or line.startswith(("EMERG", "DETECT")):
                out(f"   {line}")
        reply = source.advise(s.situation)
        for i, call in enumerate(reply.meta.get("tools", []), 1):
            args_text = json.dumps(call["arguments"], ensure_ascii=False)
            out(f"   outil {i} : {call['name']}({args_text})")
            if call["error"]:
                out(f"      refusé : {call['error']}")
            elif call["result"] is not None:
                out(f"      résultat : {json.dumps(call['result'], ensure_ascii=False)[:300]}")
        if reply.advice is None:
            out(f"   pas de conseil ({reply.meta.get('error')}) -> PPO décide seul")
        else:
            items = [(i.j, i.p, round(3 * i.w), i.s) for i in reply.advice.a]
            out(f"   conseil soumis : {items or 'aucun (abstention)'}")
        out(
            f"   {reply.meta['attempts']} tours du modèle, {reply.latency_s:.1f} s au total, "
            f"{reply.meta['prompt_tokens']} tokens lus, {reply.meta['output_tokens']} écrits"
        )
    if args.log:
        args.log.parent.mkdir(parents=True, exist_ok=True)
        args.log.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
