"""Live demo: the LLM advises the PPO agents during a short episode, and the shield decides.

    python scripts/llm_demo.py                       # urgences, grille 4x4, pointe
    python scripts/llm_demo.py --scenario incident --compare
    python scripts/llm_demo.py --source rules        # sans LLM (secours si Ollama est absent)
    python scripts/llm_demo.py --log docs/demo/llm_demo_emergency.txt

The model is loaded first (keep-alive), then a quick episode (20 simulated minutes, on
validation seed 1000) runs with COOP-FULL advised by the source. Printed live:
* for each call: the situation sent, the advice received, its latency and when it
  applies (the latency is modelled: the advice only acts once the answer has arrived),
  and what the rule-based advisor would propose for the same situation;
* for each decision that the advice changes: the PPO phase without advice, the phase
  requested with the advice, the phase the shield executes, and why. ``--all`` prints
  every advised decision, including those the advice did not change.
"""

from __future__ import annotations

import argparse
import time
from collections import Counter
from pathlib import Path

import numpy as np

from cotraffic.controllers.registry import make_controller
from cotraffic.evaluation.runner import run_episode
from cotraffic.llm.advised import AdvisedPolicy, AdvisorConfig
from cotraffic.llm.client import Ollama
from cotraffic.llm.prompts import load
from cotraffic.llm.settings import load_settings
from cotraffic.llm.situation import Situation
from cotraffic.llm.sources import AdviceSource, LlmSource, RuleSource, SourceReply
from cotraffic.paths import CHECKPOINTS_DIR, RESULTS_DIR

OUT = RESULTS_DIR / "tmp" / "demo"
SHIELD = {
    "min_green": "vert minimum pas encore atteint",
    "max_green": "vert maximum atteint",
    "starvation": "anti-famine : un mouvement attend depuis trop longtemps",
    "invalid": "phase invalide",
    "spillback": "sortie bloquée",
}


class Out:
    """Prints to the console and, optionally, to a log file (backup of the demo)."""

    def __init__(self, path: Path | None):
        self.file = None
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.file = path.open("w", encoding="utf-8")

    def __call__(self, text: str = "") -> None:
        print(text, flush=True)
        if self.file:
            self.file.write(text + "\n")
            self.file.flush()


class Watched(AdviceSource):
    """Keeps the last situation sent to the source, to print it."""

    def __init__(self, source: AdviceSource):
        self.source = source
        self.name = source.name
        self.situation: Situation | None = None

    def reset(self, seed: int) -> None:
        self.source.reset(seed)

    def advise(self, situation: Situation) -> SourceReply:
        self.situation = situation
        return self.source.advise(situation)


class DemoPolicy(AdvisedPolicy):
    def __init__(self, base, source: Watched, cfg: AdvisorConfig, out: Out, show_all: bool):
        super().__init__(base, source, cfg)
        self.watched = source
        self.out = out
        self.show_all = show_all
        self.tally: Counter = Counter()
        self.phases: dict[str, list[str]] = {}
        self._waiting: dict[str, tuple[float, int, int]] = {}
        self._read = 0
        self._env = None

    def reset(self, env) -> None:
        super().reset(env)
        self.tally, self._waiting, self._read, self._env = Counter(), {}, 0, env

    def name_of(self, junction: str, phase: int) -> str:
        sides = self.phases.get(junction)
        return f"p{phase} ({sides[phase]})" if sides and phase < len(sides) else f"p{phase}"

    def _ask(self, env, trigger: str) -> None:
        super()._ask(env, trigger)
        call, sit, out = self.calls[-1], self.watched.situation, self.out
        if sit is not None:
            self.phases = {j.id: j.phases for j in sit.junctions}
        out()
        out(
            f"t = {env.now:5.0f} s  == APPEL n°{call.call + 1} ({self.watched.name}), "
            f"déclencheur : {trigger}"
        )
        if sit is not None:
            out("  Situation envoyée :")
            for line in sit.to_text().splitlines():
                out(f"    {line}")
        if not call.valid:
            out(
                f"  Réponse invalide ou trop lente ({call.latency_s:.1f} s) "
                "-> repli : PPO décide seul"
            )
            self.tally["fallbacks"] += 1
        elif not call.advice:
            out(f"  Réponse en {call.latency_s:.1f} s : abstention, aucun conseil")
            self.tally["abstentions"] += 1
        else:
            start = call.time + call.delay_s
            out(f"  Conseil reçu en {call.latency_s:.1f} s : {self.items_text(call.advice)}")
            out(
                f"  Il agit à partir de t = {start:.0f} s (après la latence réelle), "
                f"biais = beta {self.cfg.beta:g} x force/3"
            )
        for reason in call.rejected:
            out(f"  Refusé par la validation : {reason}")
        if sit is not None and self.watched.name != "rules":
            rules = RuleSource().advise(sit).advice
            text = self.items_text([i.model_dump() for i in rules.a]) if rules.a else "rien"
            out(f"  (Pour comparaison, le conseiller à règles proposerait : {text})")

    def items_text(self, items: list[dict]) -> str:
        return " ; ".join(
            f"{a['j']} -> {self.name_of(a['j'], a['p'])} force {round(3 * a['w'])} "
            f"pendant {a['s']} s"
            for a in items
        )

    def _flush(self) -> None:
        if self._env is None:
            return
        new = self._env.decisions[self._read :]
        self._read = len(self._env.decisions)
        executed = {d["agent"]: d for d in new}
        for j, (t, plain, chosen) in self._waiting.items():
            d = executed.get(j)
            self.tally["advised"] += 1
            changed = plain != chosen
            self.tally["changed"] += int(changed)
            if d is None:
                shield = "jaune en cours : la demande attend"
                corrected = False
            else:
                corrected = d["executed"] != chosen
                why = SHIELD.get(d["reason"], d["reason"])
                shield = f"{self.name_of(j, d['executed'])}" + (
                    f", corrigé : {why}" if corrected else " (accepté)"
                )
            self.tally["corrected"] += int(corrected)
            self.tally["changed_corrected"] += int(changed and corrected)
            if self.show_all or changed:
                self.out(
                    f"  t = {t:5.0f} s  {j:>3s} : PPO seul -> {self.name_of(j, plain)} | "
                    f"avec le conseil -> {self.name_of(j, chosen)} | bouclier -> {shield}"
                )
        self._waiting = {}

    def act(self, env, obs):
        self._env = env
        self._flush()
        actions = super().act(env, obs)
        self._waiting = {j: (env.now, p, c) for j, (p, c, _) in self.advised_now.items()}
        return actions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scenario", default="emergency")
    parser.add_argument("--net", default="grid4x4")
    parser.add_argument("--demand", default="peak")
    parser.add_argument("--seed", type=int, default=1000)
    parser.add_argument("--source", choices=["llm", "rules"], default="llm")
    settings = load_settings()  # configs/llm.yaml
    parser.add_argument("--model", default=settings.model)
    parser.add_argument("--beta", type=float, default=settings.advisor.beta)
    parser.add_argument("--period", type=float, default=settings.advisor.period_s)
    parser.add_argument("--all", action="store_true", help="every advised decision")
    parser.add_argument("--compare", action="store_true", help="also run COOP-FULL alone")
    parser.add_argument("--log", type=Path, default=None)
    args = parser.parse_args()

    out = Out(args.log)
    checkpoint = CHECKPOINTS_DIR / "coop_full" / args.net / "seed1.zip"
    if args.source == "llm":
        client = Ollama(args.model, settings.options)
        start = time.perf_counter()
        client.warm_up()
        info = client.fingerprint()
        out(
            f"Modèle {args.model} ({info.get('parameters')}, {info.get('quantization')}) "
            f"chargé en {time.perf_counter() - start:.1f} s, gardé en mémoire "
            f"{settings.options.keep_alive}"
        )
        source: AdviceSource = LlmSource(client, load(settings.prompt_version, settings.technique))
    else:
        source = RuleSource()
        out("Source : conseiller à règles (sans LLM)")
    out(
        f"Épisode court : {args.net}, {args.scenario}, {args.demand}, graine {args.seed} "
        f"(validation) ; COOP-FULL + conseils, beta {args.beta:g}, appel toutes les "
        f"{args.period / 60:g} min et à chaque nouvel événement"
    )
    cfg = AdvisorConfig(
        beta=args.beta,
        period_s=args.period,
        min_gap_s=settings.advisor.min_gap_s,
        latency=settings.advisor.latency,
    )
    policy = DemoPolicy(
        make_controller("coop_full", checkpoint), Watched(source), cfg, out, args.all
    )
    common = dict(
        quick=True,
        ssm=False,
        raw_dir=OUT / "raw",
        logs_dir=OUT / "logs",
        record_decisions=True,
        mode="validation",
    )
    wall = time.perf_counter()
    row = run_episode(
        "coop_full_llm",
        args.net,
        args.demand,
        [args.scenario],
        args.seed,
        checkpoint=checkpoint,
        tag="demo",
        controller=policy,
        **common,
    )
    policy._flush()
    t, calls = policy.tally, policy.calls
    lat = [c.latency_s for c in calls if c.valid]
    out()
    out("== Bilan")
    out(
        f"  {len(calls)} appels : {sum(c.valid for c in calls)} réponses valides, "
        f"{t['abstentions']} abstentions, {t['fallbacks']} replis sur PPO seul ; "
        f"latence médiane {np.median(lat) if lat else 0:.1f} s"
    )
    out(
        f"  {t['advised']} décisions sous conseil : {t['changed']} changées par le conseil "
        f"(dont {t['changed_corrected']} refusées ensuite par le bouclier) ; au total "
        f"{t['corrected']} demandes corrigées par le bouclier : il garde le dernier mot"
    )
    out(f"  Attente moyenne par véhicule : {row['mean_waiting_time']:.1f} s")
    if args.compare:
        alone = run_episode(
            "coop_full",
            args.net,
            args.demand,
            [args.scenario],
            args.seed,
            checkpoint=checkpoint,
            tag="demo",
            **common,
        )
        gain = (
            100
            * (alone["mean_waiting_time"] - row["mean_waiting_time"])
            / max(alone["mean_waiting_time"], 1e-9)
        )
        out(
            f"  COOP-FULL seul : {alone['mean_waiting_time']:.1f} s -> gain du conseil "
            f"{gain:+.1f} % (gain positif = mieux ; un seul épisode court : indicatif)"
        )
    out(f"  Durée de la démo : {time.perf_counter() - wall:.0f} s")


if __name__ == "__main__":
    main()
