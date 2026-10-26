"""Benchmark local language models as traffic advisors, on validation situations only.

    python scripts/llm_benchmark.py --models qwen2.5:0.5b qwen2.5:1.5b qwen2.5:3b \
        [--techniques zero] [--prompt advisor-v2] [--num-predict 120] [--betas 2 4 8] \
        [--horizon 300] [--jobs 3] [--set validation] [--tag name] [--no-rollouts]
    python scripts/llm_benchmark.py --reuse-calls models_zero --models qwen2.5:1.5b \
        --betas 4 8 --tag beta_v1      # replay advice already obtained, no model call
    python scripts/llm_benchmark.py --summary-only --tag v2_zero   # tables from saved rows

Phase 1, calls: every model answers every situation (latency, valid JSON, tokens, memory,
digest, quantisation, licence). Phase 2, quality: each advice is replayed from the
situation's snapshot for ``horizon`` seconds, activated after the latency it really took,
and compared with the no-advice replay and with the rule-based advice on the same start,
for every bias strength ``beta``. Rows go to results/exploration/llm_benchmark/<tag>_*.csv
(calls, models, scores, summary, by_kind); each row carries the commit, the prompt id,
the sampling options and the intervention mechanism.
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import pandas as pd

from cotraffic.llm.advice import Advice
from cotraffic.llm.client import LLMError, Ollama, Options
from cotraffic.llm.progress import Progress
from cotraffic.llm.prompts import DEFAULT_VERSION, load
from cotraffic.llm.rollout import Stored
from cotraffic.llm.sources import RuleSource, llm_source
from cotraffic.paths import CHECKPOINTS_DIR, RESULTS_DIR
from cotraffic.seeds import TEST_SEEDS
from cotraffic.utils.io import git_commit

SITUATIONS = RESULTS_DIR / "tmp" / "llm" / "situations"
OUT = RESULTS_DIR / "exploration" / "llm_benchmark"
MECHANISM = "bias"  # logit bias on the advised phase, then argmax, then the shield


def situations(name: str, limit: int | None) -> list[Stored]:
    items = [Stored.load(p) for p in sorted((SITUATIONS / name).glob("*.json"))]
    if any(s.spec.seed in TEST_SEEDS for s in items):
        raise SystemExit("test-seed situations found: refusing to tune on them")
    return items[:limit] if limit else items


def kind_of(stored: Stored) -> str:
    kinds = sorted({e["kind"] for e in stored.situation.events})
    return "+".join(kinds) if kinds else "none"


def model_info(client: Ollama) -> dict:
    info = client.fingerprint()
    try:
        req = urllib.request.Request(
            client.url + "/api/show",
            json.dumps({"model": client.model}).encode(),
            {"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            show = json.loads(r.read())
        lines = [ln.strip() for ln in (show.get("license") or "").splitlines() if ln.strip()]
        info["license"] = lines[0][:80] if lines else ""
    except Exception:
        info["license"] = ""
    try:
        with urllib.request.urlopen(client.url + "/api/ps", timeout=10) as r:
            ps = json.loads(r.read())
        loaded = [m for m in ps.get("models", []) if m.get("name", "").startswith(client.model)]
        info["memory_gb"] = round(loaded[0]["size"] / 1e9, 2) if loaded else None
    except Exception:
        info["memory_gb"] = None
    return info


def call_phase(
    items,
    models,
    techniques,
    options: Options,
    version: str,
    run: dict,
    vote: int = 1,
    vote_temperature: float = 0.7,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, infos = [], []
    opts = {f"opt_{k}": v for k, v in asdict(options).items()}
    progress = Progress("calls", len(models) * len(techniques) * len(items))
    for model in models:
        for technique in techniques:
            client = Ollama(model, options)
            try:
                client.warm_up()
            except LLMError as err:
                print(f"{model}: unavailable ({err})")
                progress.tick(len(items))
                continue
            info = model_info(client)
            prompt = load(version, technique)
            source, label = llm_source(model, technique, options, version, vote, vote_temperature)
            infos.append({**info, "technique": label, "prompt": prompt.id, **run})
            for s in items:
                reply = source.advise(s.situation)
                rows.append(
                    {
                        "model": model,
                        "digest": info.get("digest", ""),
                        "technique": label,
                        "prompt": prompt.id,
                        "situation": s.id,
                        "kind": kind_of(s),
                        "trigger": s.situation.trigger,
                        "latency_s": reply.latency_s,
                        "attempts": reply.meta.get("attempts", 0),
                        "valid": reply.advice is not None,
                        "first_valid": reply.advice is not None and reply.meta.get("attempts") == 1,
                        "items": len(reply.advice.a) if reply.advice else 0,
                        "advice": reply.advice.model_dump_json() if reply.advice else "",
                        "prompt_tokens": reply.meta.get("prompt_tokens", 0),
                        "output_tokens": reply.meta.get("output_tokens", 0),
                        "error": reply.meta.get("error", ""),
                        **opts,
                        **run,
                    }
                )
                progress.tick()
            done = [r for r in rows if r["model"] == model and r["technique"] == label]
            lat = [r["latency_s"] for r in done]
            print(
                f"{model:14s} {technique:5s} p50 {np.median(lat):5.1f}s "
                f"valid {sum(r['valid'] for r in done)}/{len(done)}",
                flush=True,
            )
    return pd.DataFrame(rows), pd.DataFrame(infos)


_WORKER: dict = {}


def _score(task):
    from cotraffic.controllers.registry import make_controller
    from cotraffic.llm.rollout import make_env, score

    path, label, advice_json, delay, horizon, beta = task
    stored = Stored.load(Path(path))
    if "base" not in _WORKER:
        _WORKER["base"] = make_controller(
            "coop_full", CHECKPOINTS_DIR / "coop_full" / stored.spec.network / "seed1.zip"
        )
    key = json.dumps(asdict(stored.spec))
    envs = _WORKER.setdefault("envs", {})
    if key not in envs:
        envs[key] = make_env(stored.spec, _WORKER["base"].agent_cfg)
    advice = Advice.model_validate_json(advice_json) if advice_json else None
    result = score(envs[key], _WORKER["base"], stored, advice, horizon, beta, delay)
    return {
        "situation": stored.id,
        "kind": kind_of(stored),
        "label": label,
        "beta": beta,
        "delay_s": delay,
        **asdict(result),
    }


def score_phase(
    items, calls: pd.DataFrame, horizon: float, betas: list[float], jobs: int, run: dict
) -> pd.DataFrame:
    paths = {s.id: str(SITUATIONS_PATHS[s.id]) for s in items}
    tasks = []
    rules = RuleSource()
    for s in items:  # without advice, beta plays no role: one replay per situation
        tasks.append((paths[s.id], "none", "", 0.0, horizon, 0.0))
    for beta in betas:
        for s in items:
            rule = rules.advise(s.situation).advice
            tasks.append((paths[s.id], "rules", rule.model_dump_json(), 0.0, horizon, beta))
        for row in calls.itertuples():
            if row.valid and row.items and row.situation in paths:
                label = f"{row.model}|{row.technique}"
                tasks.append(
                    (paths[row.situation], label, row.advice, row.latency_s, horizon, beta)
                )
    print(f"{len(tasks)} replays of {horizon:.0f} s on {jobs} workers", flush=True)
    progress = Progress("replays", len(tasks), every=10)
    results = []
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        for result in pool.map(_score, tasks, chunksize=4):
            results.append(result)
            progress.tick()
    scores = pd.DataFrame(results)
    scores["horizon_s"] = horizon
    scores["mechanism"] = MECHANISM
    for k, v in run.items():
        scores[k] = v
    return scores


SITUATIONS_PATHS: dict[str, Path] = {}


def relative(scores: pd.DataFrame, label: str, beta: float) -> pd.DataFrame:
    """Per situation: waiting change in % and EV stop change in s, against no advice. Every
    situation counts: without a replay (no advice, or no valid answer) the policy acts
    alone, which is a change of 0."""
    base = scores[scores.label == "none"].set_index("situation")
    s = scores[(scores.label == label) & (scores.beta == beta)].set_index("situation")
    out = pd.DataFrame(index=base.index)
    out["kind"] = base["kind"]
    waiting = (
        100
        * (s.waiting_veh_s - base.loc[s.index, "waiting_veh_s"])
        / base.loc[s.index, "waiting_veh_s"].clip(lower=1)
    )
    out["waiting_%"] = waiting.reindex(base.index).fillna(0.0)
    ev = s.ev_stopped_s - base.loc[s.index, "ev_stopped_s"]
    out["ev_s"] = ev.reindex(base.index).fillna(0.0)
    out["changed"] = s.changed.reindex(base.index).fillna(0)
    out["advised"] = base.index.isin(s.index)
    return out


def quality(rel: pd.DataFrame) -> dict:
    """Gains against PPO alone: positive = better (less waiting, fewer EV stops)."""
    return {
        "n_situations": len(rel),
        "n_advised": int(rel.advised.sum()),
        "gain_waiting_%": round(-rel["waiting_%"].mean(), 2),
        "better_than_none_%": round(100 * (rel["waiting_%"] < -0.01).mean(), 0),
        "worse_than_none_%": round(100 * (rel["waiting_%"] > 0.01).mean(), 0),
        "gain_ev_stopped_s": round(-rel.ev_s.mean(), 1),
        "changed_decisions": round(rel.changed.mean(), 1),
    }


def summarise(
    calls: pd.DataFrame, infos: pd.DataFrame, scores: pd.DataFrame | None
) -> pd.DataFrame:
    out = []
    betas = sorted(scores.beta[scores.label != "none"].unique()) if scores is not None else [None]
    for (model, technique), g in calls.groupby(["model", "technique"], sort=False):
        info = infos[(infos.model == model) & (infos.technique == technique)].iloc[0]
        head = {
            "model": model,
            "technique": technique,
            "params": info.get("parameters", ""),
            "quant": info.get("quantization", ""),
            "memory_gb": info.get("memory_gb"),
            "licence": info.get("license", ""),
            "latency_p50_s": round(g.latency_s.median(), 1),
            "latency_p95_s": round(g.latency_s.quantile(0.95), 1),
            "json_first_try_%": round(100 * g.first_valid.mean(), 0),
            "json_valid_%": round(100 * g.valid.mean(), 0),
            "output_tokens": round(g.output_tokens.mean(), 0),
            "advice_items": round(g["items"].mean(), 1),
        }
        for beta in betas:
            row = dict(head, beta=beta)
            if scores is not None:
                rel = relative(scores, f"{model}|{technique}", beta)
                if len(rel):
                    row.update(quality(rel))
            out.append(row)
    for beta in betas if scores is not None else []:
        out.append(
            {
                "model": "rules (control)",
                "technique": "-",
                "beta": beta,
                **quality(relative(scores, "rules", beta)),
            }
        )
    return pd.DataFrame(out)


def by_kind(scores: pd.DataFrame) -> pd.DataFrame:
    out = []
    for (label, beta), _ in scores[scores.label != "none"].groupby(["label", "beta"], sort=False):
        rel = relative(scores, label, beta)
        groups = [("all", rel), ("any event", rel[rel.kind != "none"])]
        groups += [(k, g) for k, g in rel.groupby("kind")]
        for kind, g in groups:
            if len(g):
                out.append({"label": label, "beta": beta, "kind": kind, **quality(g)})
    return pd.DataFrame(out)


def resummarise(tag: str, calls_tag: str | None = None) -> None:
    """Summary and per-kind tables again from the saved calls and replays of ``tag``
    (``calls_tag``: the run whose calls ``tag`` replayed, if any)."""
    calls = pd.read_csv(OUT / f"{calls_tag or tag}_calls.csv", keep_default_na=False)
    infos = pd.read_csv(OUT / f"{calls_tag or tag}_models.csv", keep_default_na=False)
    scores = pd.read_csv(OUT / f"{tag}_scores.csv", keep_default_na=False)
    calls = calls[(calls.model + "|" + calls.technique).isin(set(scores.label))]
    for col in ("valid", "first_valid"):
        calls[col] = calls[col].astype(str) == "True"
    for col in ("latency_s", "output_tokens", "items"):
        calls[col] = pd.to_numeric(calls[col])
    for col in ("waiting_veh_s", "ev_stopped_s", "changed"):
        scores[col] = pd.to_numeric(scores[col])
    if "beta" not in scores:  # rows written before betas were recorded: one beta, 2
        scores["beta"] = 2.0
    scores["beta"] = pd.to_numeric(scores["beta"])
    if "kind" not in scores:
        for p in sorted((SITUATIONS / "validation").glob("*.json")):
            SITUATIONS_PATHS[p.stem] = p
        kinds = {
            sid: kind_of(Stored.load(SITUATIONS_PATHS[sid])) for sid in scores.situation.unique()
        }
        scores["kind"] = scores.situation.map(kinds)
    by_kind(scores).to_csv(OUT / f"{tag}_by_kind.csv", index=False)
    table = summarise(calls, infos, scores)
    table.to_csv(OUT / f"{tag}_summary.csv", index=False)
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        print(table.to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--models", nargs="+", default=None)
    parser.add_argument("--techniques", nargs="+", default=["zero"])
    parser.add_argument("--prompt", default=DEFAULT_VERSION)
    parser.add_argument("--set", default="validation")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--num-predict", type=int, default=120)
    parser.add_argument("--num-ctx", type=int, default=2048)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--vote", type=int, default=1, help="self-consistency: k samples")
    parser.add_argument("--vote-temperature", type=float, default=0.7)
    parser.add_argument("--betas", nargs="+", type=float, default=[2.0])
    parser.add_argument("--horizon", type=float, default=300.0)
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--tag", default="bench")
    parser.add_argument("--reuse-calls", default=None, help="tag of a run whose calls to replay")
    parser.add_argument("--no-rollouts", action="store_true")
    parser.add_argument("--summary-only", action="store_true", help="recompute the tables")
    args = parser.parse_args()
    if args.summary_only:
        resummarise(args.tag, args.reuse_calls)
        return

    items = situations(args.set, args.limit)
    for p in sorted((SITUATIONS / args.set).glob("*.json")):
        SITUATIONS_PATHS[p.stem] = p
    print(f"{len(items)} situations ({args.set})")
    run = {
        "commit": git_commit(),
        "tag": args.tag,
        "vote_k": args.vote,
        "vote_temperature": args.vote_temperature if args.vote > 1 else "",
    }
    if args.reuse_calls:
        calls = pd.read_csv(OUT / f"{args.reuse_calls}_calls.csv", keep_default_na=False)
        infos = pd.read_csv(OUT / f"{args.reuse_calls}_models.csv", keep_default_na=False)
        calls["valid"] = calls["valid"].astype(str) == "True"
        calls["first_valid"] = calls["first_valid"].astype(str) == "True"
        keep = calls.technique.isin(args.techniques)
        if args.models:
            keep &= calls.model.isin(args.models)
        calls = calls[keep & calls.situation.isin({s.id for s in items})]
        print(f"reusing {len(calls)} calls of {args.reuse_calls}")
    else:
        if not args.models:
            parser.error("--models is required unless --reuse-calls is given")
        options = replace(
            Options(),
            num_predict=args.num_predict,
            num_ctx=args.num_ctx,
            temperature=args.temperature,
        )
        calls, infos = call_phase(
            items,
            args.models,
            args.techniques,
            options,
            args.prompt,
            run,
            args.vote,
            args.vote_temperature,
        )
        OUT.mkdir(parents=True, exist_ok=True)
        calls.to_csv(OUT / f"{args.tag}_calls.csv", index=False)
        infos.to_csv(OUT / f"{args.tag}_models.csv", index=False)
    scores = None
    if not args.no_rollouts:
        scores = score_phase(items, calls, args.horizon, args.betas, args.jobs, run)
        scores.to_csv(OUT / f"{args.tag}_scores.csv", index=False)
        by_kind(scores).to_csv(OUT / f"{args.tag}_by_kind.csv", index=False)
    table = summarise(calls, infos, scores)
    table.to_csv(OUT / f"{args.tag}_summary.csv", index=False)
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        print(table.to_string(index=False))


if __name__ == "__main__":
    main()
