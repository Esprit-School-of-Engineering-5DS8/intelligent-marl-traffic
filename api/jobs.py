"""Job runner for training and comparison tasks.

Maintains a single worker queue and thread to prevent CPU oversubscription.
Stores job state and metric ring buffers in results/jobs/<id>.json.
Provides event subscriptions for Server-Sent Events (SSE).
"""

from __future__ import annotations

import asyncio
import json
import os
import queue
import shutil
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, AsyncGenerator, Callable

from api.policy import LABELS, LEARNED, METHODS, NETWORKS, checkpoint_path
from cotraffic import config, recipes
from cotraffic.analysis.style import BASELINE_METHODS, LLM_METHODS
from cotraffic.paths import CHECKPOINTS_DIR, RESULTS_DIR

ROOT = Path(__file__).resolve().parents[1]
JOBS_DIR = RESULTS_DIR / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

# Metrics the comparison reports, with whether lower is better. The paired delta is
# oriented so that positive always means "better than the reference", whatever the metric.
COMPARE_METRICS: tuple[tuple[str, bool], ...] = (
    ("mean_waiting_time", True),
    ("p95_waiting_time", True),
    ("mean_travel_time", True),
    ("throughput_per_h", False),
    ("co2_total_kg", True),
    ("stops_per_vehicle", True),
)


@dataclass
class JobRecord:
    id: str
    kind: str  # "train" | "compare"
    request: dict[str, Any]
    status: str = "queued"  # "queued" | "running" | "done" | "failed" | "cancelled"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))
    started_at: str | None = None
    ended_at: str | None = None
    step: int = 0
    total_steps: int = 0
    steps_per_s: float = 0.0
    eta_s: float = 0.0
    reward: float | None = None
    mean_halting: float | None = None
    checkpoint_path: str | None = None
    result: dict[str, Any] | None = None
    metrics_ring: list[dict[str, Any]] = field(default_factory=list)
    log: list[str] = field(default_factory=list)
    error: str | None = None


def public_job(job: JobRecord) -> dict[str, Any]:
    data = asdict(job)
    data["createdAt"] = data.pop("created_at")
    data["startedAt"] = data.pop("started_at")
    data["endedAt"] = data.pop("ended_at")
    data["totalSteps"] = data.pop("total_steps")
    data["stepsPerS"] = data.pop("steps_per_s")
    data["etaS"] = data.pop("eta_s")
    data["meanHalting"] = data.pop("mean_halting")
    data["checkpointPath"] = data.pop("checkpoint_path")
    data["metricsRing"] = data.pop("metrics_ring")
    return data


class JobRunner:
    """Manages sequential execution of training and comparison tasks."""

    def __init__(self) -> None:
        self.jobs: dict[str, JobRecord] = {}
        self.lock = threading.RLock()
        self.queue: queue.Queue[str] = queue.Queue()
        self.active_id: str | None = None
        self.cancel_event = threading.Event()
        self.listeners: dict[str, list[queue.Queue[dict[str, Any]]]] = {}
        self._load_saved()
        threading.Thread(target=self._worker, daemon=True).start()

    def _load_saved(self) -> None:
        try:
            for p in sorted(JOBS_DIR.glob("*.json")):
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    job = JobRecord(
                        id=data["id"],
                        kind=data.get("kind", "train"),
                        request=data.get("request", {}),
                        status=data.get("status", "done"),
                        created_at=data.get("createdAt", ""),
                        started_at=data.get("startedAt"),
                        ended_at=data.get("endedAt"),
                        step=data.get("step", 0),
                        total_steps=data.get("totalSteps", 0),
                        steps_per_s=data.get("stepsPerS", 0.0),
                        eta_s=data.get("etaS", 0.0),
                        reward=data.get("reward"),
                        mean_halting=data.get("meanHalting"),
                        checkpoint_path=data.get("checkpointPath"),
                        result=data.get("result"),
                        metrics_ring=data.get("metricsRing", []),
                        log=data.get("log", []),
                        error=data.get("error"),
                    )
                    self.jobs[job.id] = job
                except Exception:
                    continue
        except Exception:
            pass

    def _persist(self, job: JobRecord) -> None:
        try:
            path = JOBS_DIR / f"{job.id}.json"
            pub = public_job(job)
            path.write_text(json.dumps(pub, indent=2), encoding="utf-8")
        except Exception:
            pass

    def list(self) -> list[dict[str, Any]]:
        with self.lock:
            return [
                public_job(j)
                for j in sorted(self.jobs.values(), key=lambda x: x.created_at, reverse=True)
            ]

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self.lock:
            job = self.jobs.get(job_id)
            return public_job(job) if job else None

    def submit_train(
        self,
        agent: str | None,
        network: str,
        seeds: list[int],
        timesteps: int | None,
        *,
        recipe_id: str | None = None,
        recipe: dict[str, Any] | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self.lock:
            # Refuse >1 concurrent training
            for j in self.jobs.values():
                if j.kind == "train" and j.status in ("queued", "running"):
                    raise ValueError(f"Training job {j.id} is already in progress.")

            if network not in config.available("networks"):
                raise ValueError(f"Unknown network: {network}")

            name = recipe_id or agent
            inline = recipe is not None and not name
            if recipe is None:
                if not name:
                    raise ValueError("POST /api/train needs agent, recipe_id or recipe")
                try:
                    cfg = recipes.load_recipe(name)
                except (FileNotFoundError, ValueError) as error:
                    raise ValueError(f"Unknown agent recipe: {name} ({error})") from error
            else:
                cfg = recipes.normalize_recipe(recipe)
                if name:
                    cfg["name"] = name
            if overrides:
                cfg = recipes.normalize_recipe(config.deep_merge(cfg, overrides))
            if inline:
                # An inline profile is every configuration the editor builds: freeze it
                # as rl_<hash> so the checkpoints land per profile instead of
                # overwriting whatever the shared `rl` preset last produced.
                cfg = recipes.normalize_recipe({**cfg, "name": "rl"})
                profile = f"rl_{recipes.recipe_hash(cfg)[:8]}"
                cfg["name"] = profile
                try:
                    recipes.save_recipe(cfg, overwrite=True)
                except (OSError, ValueError) as error:
                    raise ValueError(f"cannot save the training profile: {error}") from error
            algorithm = str(cfg.get("algorithm", "ppo"))
            if not cfg.get("training") or not cfg.get(algorithm):
                raise ValueError(f"{cfg.get('name', name)} is a controller preset, not a trainable policy")

            seeds = sorted({int(s) for s in (seeds or [1])})
            if not seeds:
                raise ValueError("at least one training seed is required")
            if len(seeds) > 8:
                raise ValueError("at most 8 training seeds per job")
            total = int(
                timesteps
                or cfg["training"].get("quick_timesteps")
                or cfg["training"].get("total_timesteps", 3000)
            )
            rid = str(cfg.get("name", name or "recipe"))
            label = str(cfg.get("label") or ("LLM controller" if cfg.get("llm") else rid))
            job_id = f"train_{rid}_{network}_{uuid.uuid4().hex[:6]}"
            job = JobRecord(
                id=job_id,
                kind="train",
                request={
                    "agent": rid,
                    "label": label,
                    "recipe_id": rid,
                    "recipe": cfg,
                    "recipe_hash": recipes.recipe_hash(cfg),
                    "overlays": recipes.overlay_ids(cfg),
                    "network": network,
                    "seeds": seeds,
                    "timesteps": total,
                },
                total_steps=total * len(seeds),
            )
            self.jobs[job_id] = job
            self._persist(job)
            self.queue.put(job_id)
            return public_job(job)

    def submit_compare(
        self,
        network: str,
        scenario: str,
        demand: str,
        seed: int,
        methods: list[str],
        seeds: list[int] | None = None,
        quick: bool = True,
        overrides: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        with self.lock:
            if network not in NETWORKS:
                raise ValueError(f"Unknown network: {network}")
            for m in methods:
                if m not in METHODS:
                    raise ValueError(f"Unknown controller method: {m}")
                if m in LEARNED:
                    path = checkpoint_path(m, network)
                    if not path or not Path(path).is_file():
                        raise ValueError(
                            f"no trained {m} model for {network}: train one in the "
                            "Entraînement tab, or pick methods that have a checkpoint"
                        )
            seeds = sorted({int(s) for s in (seeds or [seed])})
            if not seeds or len(seeds) > 5:
                raise ValueError("compare needs between 1 and 5 seeds")

            job_id = f"comp_{network}_{uuid.uuid4().hex[:6]}"
            job = JobRecord(
                id=job_id,
                kind="compare",
                request={
                    "network": network,
                    "scenario": scenario,
                    "demand": demand,
                    "seed": seeds[0],
                    "seeds": seeds,
                    "methods": methods,
                    "quick": bool(quick),
                    "overrides": overrides or {},
                },
                total_steps=len(methods) * len(seeds),
            )
            self.jobs[job_id] = job
            self._persist(job)
            self.queue.put(job_id)
            return public_job(job)

    def delete(self, job_id: str) -> bool:
        """Remove a finished job record from the queue and from disk.

        The queue is a handoff surface, not an archive: failed and cancelled runs
        accumulate until the useful rows are buried under the noise. A job that is
        still queued or running cannot be removed — cancel it first.
        """
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                return False
            if job.status in ("queued", "running"):
                return False
            del self.jobs[job_id]
            (JOBS_DIR / f"{job_id}.json").unlink(missing_ok=True)
            return True

    def cancel(self, job_id: str) -> bool:
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                return False
            if job.status == "queued":
                job.status = "cancelled"
                self._persist(job)
                self._notify(job)
                return True
            if job.status == "running" and self.active_id == job_id:
                self.cancel_event.set()
                return True
        return False

    def subscribe(self, job_id: str) -> queue.Queue[dict[str, Any]]:
        with self.lock:
            q: queue.Queue[dict[str, Any]] = queue.Queue()
            self.listeners.setdefault(job_id, []).append(q)
            # Send current state immediately
            job = self.jobs.get(job_id)
            if job:
                q.put(public_job(job))
            return q

    def unsubscribe(self, job_id: str, q: queue.Queue[dict[str, Any]]) -> None:
        with self.lock:
            lst = self.listeners.get(job_id, [])
            if q in lst:
                lst.remove(q)

    def _notify(self, job: JobRecord) -> None:
        pub = public_job(job)
        with self.lock:
            for q in list(self.listeners.get(job.id, [])):
                q.put(pub)

    def _worker(self) -> None:
        while True:
            job_id = self.queue.get()
            with self.lock:
                job = self.jobs.get(job_id)
                if not job or job.status == "cancelled":
                    continue
                self.active_id = job_id
                self.cancel_event.clear()
                job.status = "running"
                job.started_at = datetime.now(UTC).isoformat(timespec="seconds")
                self._persist(job)
                self._notify(job)

            try:
                if job.kind == "train":
                    self._run_training(job)
                elif job.kind == "compare":
                    self._run_compare(job)
            except Exception as e:
                with self.lock:
                    if self.cancel_event.is_set():
                        job.status = "cancelled"
                    else:
                        job.status = "failed"
                        job.error = str(e)
                    job.ended_at = datetime.now(UTC).isoformat(timespec="seconds")
                    self._persist(job)
                    self._notify(job)
            finally:
                with self.lock:
                    self.active_id = None
                    self.cancel_event.clear()

    def _run_training(self, job: JobRecord) -> None:
        from stable_baselines3.common.callbacks import BaseCallback

        from cotraffic.training.train import (
            list_checkpoints,
            train as train_recipe,
            write_checkpoint_sidecar,
        )

        agent = job.request["agent"]
        network = job.request["network"]
        seeds = job.request.get("seeds") or [1]
        timesteps = int(job.request.get("timesteps") or 3000)
        cfg = job.request.get("recipe") or config.load_agent(agent)
        runner_self = self

        class JobProgress(BaseCallback):
            def __init__(self, base_step: int, target: int, seed: int) -> None:
                super().__init__()
                self.base_step = base_step
                self.target = target
                self.seed = seed
                self.started = time.perf_counter()
                self.start_steps = 0
                self.last_report = 0.0

            def _on_training_start(self) -> None:
                self.started = time.perf_counter()
                self.start_steps = int(self.model.num_timesteps)

            def _on_step(self) -> bool:
                if runner_self.cancel_event.is_set():
                    return False
                now = time.perf_counter()
                summary = self.locals.get("infos", [{}])[0].get("episode_summary")
                if (now - self.last_report >= 1.5) or summary:
                    done = max(0, int(self.model.num_timesteps) - self.start_steps)
                    step = self.base_step + done
                    elapsed = max(0.1, now - self.started)
                    rate = done / elapsed
                    eta = max(0, self.target - done) / max(1.0, rate)
                    reward = float(summary["episode_reward"]) if summary else job.reward
                    halting = float(summary["mean_halting"]) if summary else job.mean_halting
                    with runner_self.lock:
                        job.step = step
                        job.steps_per_s = round(rate, 1)
                        job.eta_s = round(eta, 1)
                        if reward is not None:
                            job.reward = round(reward, 2)
                        if halting is not None:
                            job.mean_halting = round(halting, 1)
                        if summary:
                            point = {
                                "step": step,
                                "reward": job.reward,
                                "halting": job.mean_halting,
                                "t": round(elapsed, 1),
                                "seed": self.seed,
                            }
                            job.metrics_ring = [*job.metrics_ring[-199:], point]
                        runner_self._notify(job)
                    self.last_report = now
                return True

        cancelled = False
        for index, seed in enumerate(seeds):
            if self.cancel_event.is_set():
                cancelled = True
                break
            callback = JobProgress(base_step=index * timesteps, target=timesteps, seed=seed)
            folder = train_recipe(
                agent,
                network,
                seed,
                total_timesteps=timesteps,
                recipe=cfg,
                extra_callbacks=[callback],
            )
            checkpoints = list_checkpoints(folder / "checkpoints")
            if not checkpoints:
                raise RuntimeError(f"training finished without a checkpoint in {folder}")
            # A cancelled seed publishes neither progress nor checkpoint: the last
            # intermediate checkpoint belongs to the cancelled run, not to a result,
            # and claiming the full step count would misrepresent what happened.
            if self.cancel_event.is_set():
                cancelled = True
                break
            steps, final = checkpoints[-1]
            dest_dir = CHECKPOINTS_DIR / agent / network
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / f"seed{seed}.zip"
            shutil.copyfile(final, dest)
            write_checkpoint_sidecar(
                dest,
                cfg,
                network,
                seed,
                extra={
                    "selected_steps": steps,
                    "training_checkpoint": str(final),
                    "selection": "final",
                    "api_job": job.id,
                },
            )
            with self.lock:
                job.checkpoint_path = str(dest)
                job.step = (index + 1) * timesteps
                job.eta_s = 0.0
                self._persist(job)
                self._notify(job)

        with self.lock:
            if cancelled or self.cancel_event.is_set():
                job.status = "cancelled"
            else:
                job.status = "done"
            job.ended_at = datetime.now(UTC).isoformat(timespec="seconds")
            self._persist(job)
            self._notify(job)

    def _run_compare(self, job: JobRecord) -> None:
        """Run every method on the same seeds and report paired deltas, not one ratio.

        A single episode per method cannot support a verdict: the demand realisation is
        random, so two methods differing by 5% may simply have drawn different vehicles.
        Every method therefore runs on the *same* seeds, and each metric is compared
        pairwise on those seeds, with the same bootstrap CI and Holm correction the
        report uses (``cotraffic.analysis.stats``). Hyperparameters travel with the result
        so the deltas can be attributed to a specific configuration, and a degraded LLM
        cell is reported as such instead of being read as a language-model result.
        """
        from cotraffic.analysis.stats import (
            cliffs_delta,
            cliffs_magnitude,
            holm,
            mann_whitney_p,
            paired_change_ci,
        )
        from cotraffic.evaluation.matrix import _dirs
        from cotraffic.evaluation.runner import run_episode

        network = job.request["network"]
        scenario = job.request.get("scenario", "normal")
        demand = job.request.get("demand", "medium")
        seeds = job.request.get("seeds") or [job.request.get("seed", 3)]
        methods = job.request["methods"]
        quick = bool(job.request.get("quick", True))
        scenarios = [scenario] if scenario != "normal" else []
        # Quick runs are not results: they go to results/tmp, never into results/raw where
        # the report's aggregate would refuse to run.
        raw_dir, logs_dir = _dirs(quick)

        by_method: dict[str, list[dict[str, Any]]] = {m: [] for m in methods}
        done = 0
        for method in methods:
            for seed in seeds:
                if self.cancel_event.is_set():
                    with self.lock:
                        job.status = "cancelled"
                        job.ended_at = datetime.now(UTC).isoformat(timespec="seconds")
                        self._persist(job)
                        self._notify(job)
                    return
                with self.lock:
                    job.step = done
                    job.log.append(
                        f"{LABELS.get(method, method)} - seed {seed} "
                        f"({done + 1}/{len(methods) * len(seeds)})"
                    )
                    self._notify(job)
                row = run_episode(
                    method=method,
                    network=network,
                    demand=demand,
                    scenarios=scenarios,
                    seed=seed,
                    checkpoint=checkpoint_path(method, network),
                    quick=quick,
                    raw_dir=raw_dir,
                    logs_dir=logs_dir,
                    agent_overrides=(job.request.get("overrides") or {}).get(method),
                )
                by_method[method].append(row)
                done += 1

        def mean(metric: str, method: str) -> float:
            values = [float(r.get(metric) or 0.0) for r in by_method[method]]
            return sum(values) / len(values) if values else float("nan")

        values = {
            m: {
                metric: [float(r.get(metric) or 0.0) for r in by_method[m]]
                for metric, _ in COMPARE_METRICS
            }
            for m in methods
        }
        # The reference is the best scripted baseline present (MP, FT, ACT...), which is
        # what a controller has to beat; the first method only if none is selected.
        baselines = [m for m in methods if m in BASELINE_METHODS]
        reference = (
            min(baselines, key=lambda m: mean("mean_waiting_time", m))
            if baselines
            else methods[0]
        )
        tested = len(seeds) >= 2

        comparisons: list[dict[str, Any]] = []
        for metric, lower_better in COMPARE_METRICS:
            sign = -1.0 if lower_better else 1.0
            ref_values = values[reference][metric]
            ref_mean = sum(ref_values) / len(ref_values)
            for method in methods:
                cand = values[method][metric]
                cand_mean = sum(cand) / len(cand)
                point, lo, hi = paired_change_ci([cand], ref_values)
                paired = sorted((sign * lo, sign * hi))
                same = method == reference
                p_value = float("nan") if (same or not tested) else mann_whitney_p(cand, ref_values)
                delta = float("nan") if (same or not tested) else cliffs_delta(cand, ref_values)
                comparisons.append(
                    {
                        "metric": metric,
                        "method": method,
                        "reference": reference,
                        "isReference": same,
                        "mean": cand_mean,
                        "referenceMean": ref_mean,
                        # Oriented like the paired delta: positive always means better,
                        # both here and in the report and the UI.
                        "improvementPct": sign * 100 * (cand_mean - ref_mean) / ref_mean
                        if ref_mean
                        else float("nan"),
                        "pairedImprovementPct": sign * point,
                        "pairedCiLo": paired[0],
                        "pairedCiHi": paired[1],
                        "pValue": p_value,
                        "effect": cliffs_magnitude(delta) if delta == delta else "",
                        "cliffsDelta": delta,
                        "nSeeds": len(seeds),
                    }
                )
        p_values = [c["pValue"] for c in comparisons if c["pValue"] == c["pValue"]]
        corrected = holm(p_values) if p_values else []
        for entry, p_holm in zip(
            [c for c in comparisons if c["pValue"] == c["pValue"]], corrected, strict=True
        ):
            entry["pHolm"] = p_holm
            entry["significant"] = bool(p_holm < 0.05)
        for entry in comparisons:
            entry.setdefault("pHolm", None)
            entry.setdefault("significant", False)

        warnings: list[str] = []
        if not tested:
            warnings.append(
                "one seed: no significance test, and the deltas describe a single demand "
                "realisation. Run again with 2 seeds or more for a paired verdict."
            )
        llm_health: dict[str, dict[str, Any]] = {}
        for method in methods:
            if method not in LLM_METHODS:
                continue
            rows = by_method[method]
            statuses = [str(r.get("llm_status") or "unknown") for r in rows]
            valid = sum(1 for r in rows if str(r.get("llm_valid", 0)) in {"1", "1.0"})
            llm_health[method] = {
                "statuses": statuses,
                "validSeeds": valid,
                "seeds": len(rows),
                "calls": int(sum(float(r.get("llm_calls") or 0) for r in rows)),
                "success": int(sum(float(r.get("llm_success") or 0) for r in rows)),
                "errors": int(sum(float(r.get("llm_errors") or 0) for r in rows)),
                "coveragePct": round(
                    sum(float(r.get("llm_coverage_pct") or 0) for r in rows) / len(rows), 1
                )
                if rows
                else 0.0,
                "promptTokens": int(sum(float(r.get("llm_prompt_tokens") or 0) for r in rows)),
                "lastError": next(
                    (str(r.get("llm_last_error")) for r in rows if r.get("llm_last_error")), ""
                ),
            }
            if valid < len(rows):
                warnings.append(
                    f"the LLM answered in {valid}/{len(rows)} runs (status "
                    f"{', '.join(sorted(set(statuses)))}): the other runs measured "
                    "Max-Pressure, its fallback, so those numbers are not LLM results."
                )

        worst = max(methods, key=lambda m: mean("mean_waiting_time", m))
        best = min(methods, key=lambda m: mean("mean_waiting_time", m))
        best_entry = next(
            c for c in comparisons if c["metric"] == "mean_waiting_time" and c["method"] == best
        )
        best_label, ref_label = LABELS.get(best, best), LABELS.get(reference, reference)
        if best == reference:
            verdict = (
                f"{best_label} held the best mean waiting time ({best_entry['mean']:.1f} s) "
                f"on {network} ({demand}, {len(seeds)} seed(s))."
            )
        elif best == worst:
            verdict = f"all methods ran the same mean waiting time on {network} ({demand})."
        else:
            significance = (
                "significant" if best_entry["significant"] else "not significant"
            )
            tested_note = (
                f"{len(seeds)} paired seeds" if tested else "1 seed, no test"
            )
            verdict = (
                f"{best_label} beats {ref_label} by {best_entry['pairedImprovementPct']:+.1f}% "
                f"waiting time (95% CI {best_entry['pairedCiLo']:+.1f} to "
                f"{best_entry['pairedCiHi']:+.1f}, {tested_note}, {significance})."
            )

        params: dict[str, dict[str, Any]] = {}
        for method in methods:
            raw = by_method[method][0].get("parameters") if by_method[method] else None
            try:
                params[method] = json.loads(raw) if raw else {}
            except (TypeError, ValueError):
                params[method] = {}

        with self.lock:
            job.status = "done"
            job.step = len(methods) * len(seeds)
            job.ended_at = datetime.now(UTC).isoformat(timespec="seconds")
            job.result = {
                "network": network,
                "scenario": scenario,
                "demand": demand,
                "seeds": seeds,
                "quick": quick,
                "reference": reference,
                "methods": methods,
                "metrics": [m for m, _ in COMPARE_METRICS],
                "rows": {m: by_method[m][0] for m in methods},
                "perSeed": {m: by_method[m] for m in methods},
                "comparisons": comparisons,
                "parameters": params,
                "llm": llm_health,
                "warnings": warnings,
                "verdict": verdict,
            }
            self._persist(job)
            self._notify(job)


runner = JobRunner()
