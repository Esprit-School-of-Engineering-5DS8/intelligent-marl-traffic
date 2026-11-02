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
    # Heartbeat: written on every persist, so an abandoned campaign is distinguishable
    # from one that is still working.
    updated_at: str | None = None
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
    data["updatedAt"] = data.pop("updated_at")
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
                        updated_at=data.get("updatedAt"),
                        step=data.get("step", 0),
                        total_steps=data.get("totalSteps", 0),
                        steps_per_s=data.get("stepsPerS", 0.0),
                        eta_s=data.get("etaS", 0.0),
                        reward=data.get("reward"),
                        mean_halting=data.get("meanHalting"),
                        checkpoint_path=data.get("checkpointPath"),
                        result=data.get("result"),
                        metrics_ring=[
                            {key: value for key, value in point.items() if key in {"step", "reward", "halting", "t", "seed", "policyLoss", "valueLoss", "entropy", "approxKl", "explainedVariance"}}
                            for point in data.get("metricsRing", [])
                        ],
                        log=data.get("log", []),
                        error=data.get("error"),
                    )
                    if job.status in ("queued", "running"):
                        # A campaign that finished episodes before the process stopped is not a
                        # failure: the retained rows are valid evidence and the rest is a resume
                        # away. Everything else has to restart from zero.
                        rows = (job.result or {}).get("rows") if isinstance(job.result, dict) else None
                        completed = sum(1 for row in rows or [] if row.get("status") == "done")
                        job.ended_at = datetime.now(UTC).isoformat(timespec="seconds")
                        if job.kind == "benchmark-suite" and completed:
                            job.status = "interrupted"
                            job.step = completed
                            job.error = (
                                f"Interrupted after {completed} of {job.total_steps} episodes; "
                                f"completed episodes are retained. Resume to run the remaining {job.total_steps - completed}."
                            )
                        else:
                            job.status = "failed"
                            job.error = "API restarted before the job completed; progress was retained but there is nothing to resume."
                        self._persist(job)
                    self.jobs[job.id] = job
                except Exception:
                    continue
        except OSError:
            raise

    def _persist(self, job: JobRecord) -> None:
        job.updated_at = datetime.now(UTC).isoformat(timespec="seconds")
        path = JOBS_DIR / f"{job.id}.json"
        pub = public_job(job)
        temp = path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(pub, indent=2), encoding="utf-8")
        os.replace(temp, path)

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
                # The hash (and therefore the checkpoint folder) must ignore the human
                # label: renaming “Tunis agent v1” to “Tunis agent v2” keeps the same
                # profile and weights instead of forking an empty copy.
                profile = f"rl_{recipes.recipe_hash({k: v for k, v in cfg.items() if k != 'label'})[:8]}"
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
            if overrides and isinstance(overrides.get("training"), dict):
                training_overrides = overrides["training"]
                valid_demands = {"low", "medium", "peak", "rush_profile"}
                valid_scenarios = {"normal", "emergency", "pedestrians", "buses", "incident"}
                if "demand_levels" in training_overrides:
                    values = set(training_overrides["demand_levels"])
                    if values and not values <= valid_demands:
                        raise ValueError(f"unsupported training demand levels: {sorted(values - valid_demands)}")
                    if values:
                        cfg["training"]["demand_levels"] = sorted(values)
                if "scenarios" in training_overrides:
                    values = set(training_overrides["scenarios"])
                    if values and not values <= valid_scenarios:
                        raise ValueError(f"unsupported training scenarios: {sorted(values - valid_scenarios)}")
                    from cotraffic.envs.episodes import unsupported
                    invalid = values & unsupported(network)
                    if invalid:
                        raise ValueError(f"{network} does not support training scenarios: {sorted(invalid)}")
                    if values:
                        cfg["training"]["scenarios"] = sorted(values)
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

    def submit_model_benchmark(
        self,
        network: str,
        scenario: str,
        demand: str,
        seeds: list[int],
        models: list[dict[str, Any]],
        quick: bool = True,
    ) -> dict[str, Any]:
        """Queue a paired comparison of explicit, immutable saved checkpoints."""
        with self.lock:
            if network not in NETWORKS:
                raise ValueError(f"Unknown network: {network}")
            if len(models) < 1 or len(models) > 5:
                raise ValueError("benchmark requires 1–5 saved model versions")
        seeds = sorted({int(seed) for seed in seeds})
        if not seeds or len(seeds) > 100:
            raise ValueError("benchmark requires 1–100 shared evaluation seeds")
        if not isinstance(scenario, str) or not isinstance(demand, str):
            raise ValueError("scenario and demand must be strings")
        if scenario != "normal":
            try:
                config.load("scenarios", scenario)
            except (FileNotFoundError, ValueError) as error:
                raise ValueError(f"unknown benchmark scenario {scenario}") from error
            from cotraffic.envs.episodes import unsupported
            if scenario in unsupported(network):
                raise ValueError(f"{network} does not support scenario {scenario}")
        if demand not in {"low", "medium", "peak", "rush_profile"}:
            raise ValueError(f"unknown demand profile {demand}")
        for model in models:
            path = Path(model["checkpoint"]).resolve()
            if not path.is_file() or path.suffix != ".zip":
                raise ValueError(f"checkpoint unavailable for {model.get('label', model.get('id'))}")
            if model.get("network") != network:
                raise ValueError(f"{model.get('label', model.get('id'))} was trained for {model.get('network')}, not {network}")
        job_id = f"bench_{network}_{uuid.uuid4().hex[:8]}"
        job = JobRecord(
            id=job_id,
            kind="benchmark",
            request={
                "network": network,
                "scenario": scenario,
                "demand": demand,
                "seeds": seeds,
                "models": models,
                "quick": bool(quick),
                "primaryMetric": "mean_waiting_time",
            },
            total_steps=len(models) * len(seeds),
        )
        self.jobs[job_id] = job
        self._persist(job)
        self.queue.put(job_id)
        return public_job(job)

    def submit_benchmark_suite(
        self,
        network: str,
        scenarios: list[str],
        demands: list[str],
        seeds: list[int],
        models: list[dict[str, Any]],
        quick: bool = True,
    ) -> dict[str, Any]:
        if network not in NETWORKS:
            raise ValueError(f"Unknown network: {network}")
        if len(models) < 2 or len(models) > 5:
            raise ValueError("benchmark requires 2–5 saved model versions")
        allowed_scenarios = {"normal", "emergency", "pedestrians", "buses", "incident"}
        allowed_demands = {"low", "medium", "peak", "rush_profile"}
        if not scenarios or not set(scenarios) <= allowed_scenarios:
            raise ValueError("benchmark suite includes an unknown or empty scenario selection")
        if not demands or not set(demands) <= allowed_demands:
            raise ValueError("benchmark suite includes an unknown or empty demand selection")
        if len(set(scenarios)) != len(scenarios) or len(set(demands)) != len(demands):
            raise ValueError("benchmark suite scenarios and demands must be unique")
        from cotraffic.envs.episodes import unsupported
        invalid_scenarios = set(scenarios) & unsupported(network)
        if invalid_scenarios:
            raise ValueError(f"{network} does not support scenarios: {sorted(invalid_scenarios)}")
        seeds = sorted({int(seed) for seed in seeds})
        if not seeds or len(seeds) > 100:
            raise ValueError("benchmark suite requires 1–100 unique evaluation seeds")
        for model in models:
            checkpoint = Path(model["checkpoint"]).resolve()
            if not checkpoint.is_file() or checkpoint.suffix != ".zip":
                raise ValueError(f"checkpoint unavailable for {model.get('label', model.get('id'))}")
            if model.get("network") != network:
                raise ValueError(f"{model.get('label', model.get('id'))} was trained for {model.get('network')}, not {network}")
        conditions = [{"scenario": scenario, "demand": demand} for scenario in scenarios for demand in demands]
        if len(conditions) * len(seeds) * len(models) > 2000:
            raise ValueError("benchmark suite exceeds the 2,000 episode campaign limit")
        job_id = f"suite_{network}_{uuid.uuid4().hex[:8]}"
        job = JobRecord(
            id=job_id,
            kind="benchmark-suite",
            request={"network": network, "conditions": conditions, "seeds": seeds, "models": models, "quick": bool(quick), "primaryMetric": "mean_waiting_time"},
            total_steps=len(conditions) * len(seeds) * len(models),
        )
        with self.lock:
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
        llm_settings: dict[str, Any] | None = None,
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
                    "llmSettings": llm_settings or {},
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

    def resume(self, job_id: str) -> dict[str, Any]:
        """Requeue a benchmark campaign that still owns completed episodes.

        The suite runner seeds itself from the retained rows and skips every cell already
        recorded as done, so resuming costs only the missing episodes and keeps the shared
        seeds intact.
        """
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                raise ValueError(f"Job {job_id} not found")
            if job.kind != "benchmark-suite":
                raise ValueError("Only benchmark campaigns can be resumed")
            if job.status not in ("interrupted", "cancelled", "failed"):
                raise ValueError(f"Job {job_id} is {job.status}, not resumable")
            rows = (job.result or {}).get("rows") if isinstance(job.result, dict) else None
            completed = sum(1 for row in rows or [] if row.get("status") == "done")
            if not completed:
                raise ValueError(f"Job {job_id} has no completed episodes to resume from")
            job.status = "queued"
            job.error = None
            job.ended_at = None
            job.step = completed
            job.log.append(f"Resumed: skipping {completed} completed episodes of {job.total_steps}.")
            self._persist(job)
            self._notify(job)
            self.queue.put(job_id)
            return public_job(job)

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
                elif job.kind == "benchmark-suite":
                    self._run_benchmark_suite(job)
                elif job.kind == "compare":
                    self._run_compare(job)
                elif job.kind == "benchmark":
                    self._run_model_benchmark(job)
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
                                "policyLoss": self.model.logger.name_to_value.get("train/policy_gradient_loss"),
                                "valueLoss": self.model.logger.name_to_value.get("train/value_loss"),
                                "entropy": self.model.logger.name_to_value.get("train/entropy_loss"),
                                "approxKl": self.model.logger.name_to_value.get("train/approx_kl"),
                                "explainedVariance": self.model.logger.name_to_value.get("train/explained_variance"),
                            }
                            job.metrics_ring = [*job.metrics_ring[-199:], point]
                        self._persist(job)
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

    def _run_benchmark_suite(self, job: JobRecord) -> None:
        """Evaluate each saved model on every shared scenario/demand/seed cell."""
        from cotraffic.evaluation.matrix import _dirs
        from cotraffic.evaluation.runner import run_episode

        request = job.request
        network, seeds, models = request["network"], request["seeds"], request["models"]
        conditions = request["conditions"]
        quick = bool(request["quick"])
        raw_dir, logs_dir = _dirs(quick)
        # Resuming: the retained rows are the campaign's own history, so they are the starting
        # point and every cell already recorded as done is skipped instead of re-simulated.
        retained = (job.result or {}).get("rows") if isinstance(job.result, dict) else None
        rows: list[dict[str, Any]] = [row for row in (retained or []) if row.get("status") == "done"]
        completed = {
            (row["modelId"], row["scenario"], row["demand"], int(row["evaluationSeed"]))
            for row in rows
        }
        total = len(conditions) * len(seeds) * len(models)

        def suite_summaries() -> dict[str, Any]:
            """Per condition × model summary over every tracked metric. The first model
            of each condition is the reference; the others carry paired improvements on
            the shared evaluation seeds plus Cliff's delta."""
            metric_specs = (
                ("mean_waiting_time", "Mean waiting time", "s", True),
                ("median_waiting_time", "Median waiting time", "s", True),
                ("p95_waiting_time", "95th percentile waiting time", "s", True),
                ("mean_travel_time", "Mean travel time", "s", True),
                ("mean_time_loss", "Mean time loss", "s", True),
                ("person_weighted_delay", "Person-weighted delay", "s", True),
                ("stops_per_vehicle", "Stops per vehicle", "", True),
                ("throughput_per_h", "Throughput", "vehicles/hour", False),
                ("mean_queue", "Mean queue", "vehicles", True),
                ("co2_total_kg", "CO₂ emissions", "kg", True),
                ("ssm_conflicts_per_1000_veh", "SSM conflicts per 1 000 vehicles", "", True),
                ("ev_delay", "Emergency-vehicle delay", "s", True),
                ("ped_mean_waiting_time", "Pedestrian waiting time", "s", True),
            )
            cells = []
            for condition_index, condition in enumerate(conditions):
                condition_rows = [row for row in rows if row["scenario"] == condition["scenario"] and row["demand"] == condition["demand"] and row.get("status") == "done"]
                reference_values: dict[str, dict[float, float]] = {}
                model_entries = []
                for model_index, model in enumerate(models):
                    metric_entries = {}
                    for metric, label, unit, lower_is_better in metric_specs:
                        values_by_seed = {float(row["evaluationSeed"]): float(row[metric]) for row in condition_rows if row["modelId"] == model["id"] and isinstance(row.get(metric), (int, float))}
                        values = list(values_by_seed.values())
                        mean, lo, hi = bootstrap_ci(values, seed=400 + condition_index * 100 + model_index) if values else (None, None, None)
                        paired_improvement = None
                        paired_ci = None
                        cliffs = None
                        p_value = None
                        if model_index == 0:
                            reference_values[metric] = values_by_seed
                            paired_improvement = 0.0
                        else:
                            refs = reference_values.get(metric, {})
                            shared = sorted(set(values_by_seed) & set(refs))
                            reference_mean = sum(refs.values()) / len(refs) if refs else 0.0
                            if len(shared) >= 2 and abs(reference_mean) > 1e-12:
                                raw_delta, raw_lo, raw_hi = paired_change_ci([list(refs[s] for s in shared)], [values_by_seed[s] for s in shared], seed=600 + condition_index * 100 + model_index)
                                orientation = -1 if lower_is_better else 1
                                paired_improvement = orientation * raw_delta
                                paired_ci = sorted((orientation * raw_lo, orientation * raw_hi))
                                diffs = [values_by_seed[s] - refs[s] for s in shared]
                                if all(value == 0 for value in diffs):
                                    p_value = 1.0
                                else:
                                    try:
                                        from scipy.stats import wilcoxon
                                        p_value = float(wilcoxon(diffs, alternative="two-sided").pvalue)
                                    except Exception:
                                        p_value = None
                                cliffs = cliffs_delta([values_by_seed[s] for s in shared], [refs[s] for s in shared])
                        metric_entries[metric] = {
                            "label": label, "unit": unit, "lowerIsBetter": lower_is_better,
                            "n": len(values), "mean": mean,
                            "ci95": [lo, hi] if len(values) >= 2 and len(values) else None,
                            "pairedImprovementPct": paired_improvement,
                            "pairedImprovementCi95": paired_ci,
                            "pValue": p_value, "cliffsDelta": cliffs,
                            "perSeed": [[seed, value] for seed, value in sorted(values_by_seed.items())],
                        }
                    model_entries.append({"modelId": model["id"], "label": model["label"], "version": model["version"], "metrics": metric_entries})
                cells.append({"scenario": condition["scenario"], "demand": condition["demand"], "n": len(condition_rows), "models": model_entries})
            return {"conditions": cells, "metricSpecs": [{"key": m, "label": l, "unit": u, "lowerIsBetter": lb} for m, l, u, lb in metric_specs]}

        from cotraffic.analysis.stats import bootstrap_ci, cliffs_delta, paired_change_ci

        for condition in conditions:
            for model in models:
                for seed in seeds:
                    if (model["id"], condition["scenario"], condition["demand"], int(seed)) in completed:
                        continue
                    if self.cancel_event.is_set():
                        with self.lock:
                            job.status = "cancelled"
                            job.ended_at = datetime.now(UTC).isoformat(timespec="seconds")
                            job.result = {"rows": rows, "models": models, "conditions": conditions, "seeds": seeds, "network": network, "quick": quick, "summaries": suite_summaries(), "evidence": "smoke" if quick else "exploratory", "warning": "Campaign cancelled; completed episode rows are retained."}
                            self._persist(job)
                            self._notify(job)
                        return
                    scenario, demand = condition["scenario"], condition["demand"]
                    scenarios = [] if scenario == "normal" else [scenario]
                    with self.lock:
                        job.log.append(f"{model['label']} · {scenario}/{demand} · seed {seed} ({len(rows)+1}/{total})")
                        job.step = len(rows)
                        self._notify(job)
                    try:
                        result = run_episode(method=str(model["method"]), network=network, demand=demand, scenarios=scenarios, seed=seed, checkpoint=Path(model["checkpoint"]).resolve(), quick=quick, raw_dir=raw_dir, logs_dir=logs_dir, tag=f"{job.id}_{model['id']}_{scenario}_{demand}_{seed}", agent_overrides=model.get("recipe"))
                        rows.append({"modelId": model["id"], "modelLabel": model["label"], "version": model["version"], "scenario": scenario, "demand": demand, "evaluationSeed": seed, "status": "done", **result})
                    except Exception as error:
                        rows.append({"modelId": model["id"], "modelLabel": model["label"], "version": model["version"], "scenario": scenario, "demand": demand, "evaluationSeed": seed, "status": "failed", "error": str(error)})
                        job.log.append(f"FAILED {model['label']} · {scenario}/{demand} · seed {seed}: {error}")
                    with self.lock:
                        job.step = len(rows)
                        job.result = {"rows": rows, "models": models, "conditions": conditions, "network": network, "seeds": seeds, "quick": quick, "summaries": suite_summaries(), "evidence": "smoke" if quick else "exploratory" if len(seeds) < 10 else "reportable"}
                        self._persist(job)
                        self._notify(job)
        with self.lock:
            failed = any(row.get("status") == "failed" for row in rows)
            job.status = "failed" if failed and not any(row.get("status") == "done" for row in rows) else "done"
            if failed and job.status == "failed":
                job.error = "All benchmark episodes failed; inspect the retained per-episode errors."
            # Recompute from the full row set: a resumed campaign has rows from before the
            # restart, so the summaries must reflect all of them, not only this run's episodes.
            job.result = {
                "rows": rows,
                "models": models,
                "conditions": conditions,
                "seeds": seeds,
                "network": network,
                "quick": quick,
                "summaries": suite_summaries(),
                "evidence": "smoke" if quick else "exploratory" if len(seeds) < 10 else "reportable",
            }
            job.step = total
            job.ended_at = datetime.now(UTC).isoformat(timespec="seconds")
            self._persist(job)
            self._notify(job)

    def _run_model_benchmark(self, job: JobRecord) -> None:
        """Evaluate saved checkpoints on exactly the same scenario/demand/seeds."""
        from cotraffic.analysis.stats import bootstrap_ci, cliffs_delta, cliffs_magnitude, holm, paired_change_ci
        from cotraffic.evaluation.matrix import _dirs
        from cotraffic.evaluation.runner import run_episode

        request = job.request
        network, scenario, demand = request["network"], request["scenario"], request["demand"]
        seeds, models, quick = request["seeds"], request["models"], bool(request["quick"])
        scenarios = [] if scenario == "normal" else [scenario]
        raw_dir, logs_dir = _dirs(quick)
        rows: list[dict[str, Any]] = []
        total = len(models) * len(seeds)

        def summarize(completed: list[dict[str, Any]]) -> dict[str, Any]:
            summaries = []
            primary = "mean_waiting_time"
            reference = models[0]
            reference_values = {
                int(row["evaluationSeed"]): float(row[primary])
                for row in completed
                if row["modelId"] == reference["id"] and isinstance(row.get(primary), (int, float))
            }
            for model_index, model in enumerate(models):
                values_by_seed = {
                    int(row["evaluationSeed"]): float(row[primary])
                    for row in completed
                    if row["modelId"] == model["id"] and isinstance(row.get(primary), (int, float))
                }
                values = list(values_by_seed.values())
                mean, lo, hi = bootstrap_ci(values, seed=200 + model_index) if values else (None, None, None)
                metric_summary = {}
                for metric, label, unit, lower_is_better in (
                    ("mean_waiting_time", "Mean waiting time", "s", True),
                    ("mean_travel_time", "Mean travel time", "s", True),
                    ("throughput_per_h", "Throughput", "vehicles/hour", False),
                    ("co2_total_kg", "CO₂ emissions", "kg", True),
                    ("stops_per_vehicle", "Stops per vehicle", "", True),
                    ("teleports_total", "Teleports", "", True),
                    ("collisions", "Collisions", "", True),
                ):
                    metric_values = {
                        int(row["evaluationSeed"]): float(row[metric])
                        for row in completed
                        if row["modelId"] == model["id"]
                        and isinstance(row.get(metric), (int, float))
                    }
                    metric_mean, metric_lo, metric_hi = bootstrap_ci(
                        list(metric_values.values()), seed=500 + model_index
                    ) if metric_values else (None, None, None)
                    reference_metric_values = {
                        int(row["evaluationSeed"]): float(row[metric])
                        for row in completed
                        if row["modelId"] == reference["id"]
                        and isinstance(row.get(metric), (int, float))
                    }
                    common_seeds = sorted(set(metric_values) & set(reference_metric_values))
                    paired_improvement = None
                    paired_ci = None
                    if model["id"] == reference["id"]:
                        paired_improvement = 0.0
                        paired_ci = [0.0, 0.0] if len(common_seeds) >= 2 else None
                    elif len(common_seeds) >= 2:
                        raw_delta, raw_lo, raw_hi = paired_change_ci(
                            [[metric_values[seed] for seed in common_seeds]],
                            [reference_metric_values[seed] for seed in common_seeds],
                            seed=700 + model_index,
                        )
                        orientation = -1 if lower_is_better else 1
                        paired_improvement = orientation * raw_delta
                        paired_ci = sorted((orientation * raw_lo, orientation * raw_hi))
                    paired_values = [metric_values[seed] for seed in common_seeds]
                    paired_reference = [reference_metric_values[seed] for seed in common_seeds]
                    raw_paired_delta = None
                    if model["id"] != reference["id"] and len(common_seeds) >= 2:
                        differences = [left - right for left, right in zip(paired_values, paired_reference, strict=True)]
                        if all(value == 0 for value in differences):
                            raw_paired_delta = 1.0
                        else:
                            from scipy.stats import wilcoxon
                            raw_paired_delta = float(wilcoxon(differences, alternative="two-sided").pvalue)
                    metric_summary[metric] = {
                        "label": label, "unit": unit, "lowerIsBetter": lower_is_better,
                        "n": len(metric_values), "mean": metric_mean,
                        "ci95": [metric_lo, metric_hi] if len(metric_values) >= 2 else None,
                        "pairedSeeds": len(common_seeds),
                        "pairedImprovementPct": paired_improvement,
                        "pairedImprovementCi95": paired_ci,
                        "pValue": raw_paired_delta,
                        "cliffsDelta": cliffs_delta(paired_values, paired_reference) if paired_values and paired_reference else None,
                    }
                shared = sorted(set(values_by_seed) & set(reference_values))
                delta = delta_lo = delta_hi = None
                if model["id"] != reference["id"] and shared:
                    raw_delta, raw_lo, raw_hi = paired_change_ci(
                        [[values_by_seed[seed] for seed in shared]],
                        [reference_values[seed] for seed in shared],
                        seed=300 + model_index,
                    )
                    delta, delta_lo, delta_hi = -raw_delta, -raw_hi, -raw_lo
                summaries.append({
                    "modelId": model["id"], "label": model["label"], "n": len(values),
                    "meanWaitingTime": mean, "ci95": [lo, hi] if len(values) >= 2 else None,
                    "pairedImprovementPct": 0.0 if model["id"] == reference["id"] else delta,
                    "pairedImprovementCi95": [delta_lo, delta_hi] if len(shared) >= 2 and model["id"] != reference["id"] else None,
                    "referenceModelId": reference["id"],
                    "metrics": metric_summary,
                })
            test_entries = [
                metric for item in summaries for metric in item["metrics"].values()
                if item["modelId"] != reference["id"] and isinstance(metric.get("pValue"), (int, float))
            ]
            adjusted = holm([entry["pValue"] for entry in test_entries])
            for entry, p_holm in zip(test_entries, adjusted, strict=True):
                entry["pHolm"] = p_holm
                entry["significant"] = bool(p_holm < 0.05)
                entry["effect"] = cliffs_magnitude(entry["cliffsDelta"]) if isinstance(entry.get("cliffsDelta"), (int, float)) else ""
            for item in summaries:
                for metric, entry in zip(item["metrics"].keys(), item["metrics"].values(), strict=True):
                    if item["modelId"] != reference["id"]:
                        entry.setdefault("pHolm", None)
                        entry.setdefault("significant", False)
                        entry.setdefault("effect", "")
            evidence = "smoke" if quick else ("exploratory" if len(seeds) < 10 else "reportable")
            return {"summaries": summaries, "primaryMetric": primary,
                    "evidence": evidence, "winner": None,
                    "verdict": "not enough seeds to call a winner" if len(seeds) < 10 else "tests are exploratory; interpret confidence intervals, Holm-adjusted p-values and effect sizes together",
                    "metrics": [
                        {"key": key, "label": label, "unit": unit,
                         "lowerIsBetter": lower}
                        for key, label, unit, lower in (
                            ("mean_waiting_time", "Mean waiting time", "s", True),
                            ("mean_travel_time", "Mean travel time", "s", True),
                            ("throughput_per_h", "Throughput", "vehicles/hour", False),
                            ("co2_total_kg", "CO₂ emissions", "kg", True),
                            ("stops_per_vehicle", "Stops per vehicle", "", True),
                            ("teleports_total", "Teleports", "", True),
                            ("collisions", "Collisions", "", True),
                        )
                    ]}

        for model in models:
            for seed in seeds:
                if self.cancel_event.is_set():
                    with self.lock:
                        job.status = "cancelled"
                        job.ended_at = datetime.now(UTC).isoformat(timespec="seconds")
                        job.result = {"rows": rows, "models": models, "network": network, "scenario": scenario, "demand": demand, "seeds": seeds, "quick": quick, "warning": "Campaign cancelled; completed episode rows are retained.", **summarize(rows)}
                        self._persist(job)
                        self._notify(job)
                    return
                with self.lock:
                    job.log.append(f"{model['label']} · evaluation seed {seed} ({len(rows) + 1}/{total})")
                    job.step = len(rows)
                    self._notify(job)
                checkpoint = Path(model["checkpoint"]).resolve()
                # A named model is an immutable checkpoint plus its training recipe.
                # Pass that config explicitly so evaluation never consults the mutable
                # current recipe stored under the source agent name.
                result = run_episode(
                    method=str(model["method"]), network=network, demand=demand,
                    scenarios=scenarios, seed=seed, checkpoint=checkpoint,
                    quick=quick, raw_dir=raw_dir, logs_dir=logs_dir,
                    tag=f"{job.id}_{model['id']}",
                    agent_overrides=model.get("recipe"),
                )
                rows.append({"modelId": model["id"], "modelLabel": model["label"], "version": model["version"], "evaluationSeed": seed, **result})
                with self.lock:
                    job.step = len(rows)
                    job.result = {"rows": rows, "models": models, "network": network, "scenario": scenario, "demand": demand, "seeds": seeds, "quick": quick, **summarize(rows)}
                    self._persist(job)
                    self._notify(job)
        with self.lock:
            job.status = "done"
            job.step = total
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
                    # The Training page's LLM settings condition the team only; every
                    # other controller keeps its config-file defaults.
                    controller_kwargs=(
                        (job.request.get("llmSettings") or {})
                        if method == "llm_team"
                        else None
                    ),
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
