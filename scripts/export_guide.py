"""The technical summary of the final controller for the dashboard (page "Le résumé technique").

    python scripts/export_guide.py      # -> frontend/public/data/guide.json

Reads docs/RESUME_CONTROLEUR_FINAL.md and cuts it into its parts (one per "## " heading),
then takes from the code itself the excerpts each part refers to: a function or a method
is located by its name with the ``ast`` module (its first and last lines come from the
parser, not from a hand-written number), a few top-level constants by a line range checked
against the text they must contain. The dashboard shows the document and, under each part,
the real code that computes it.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "RESUME_CONTROLEUR_FINAL.md"
OUT = ROOT / "frontend" / "public" / "data" / "guide.json"

# (part of the document, title, file, function/method name or (first line, last line, check))
EXCERPTS = [
    ("2", "La récompense de COOP-FULL", "src/cotraffic/envs/rewards.py", "RewardComputer.combine"),
    ("2", "La taille de l'observation", "src/cotraffic/envs/observations.py", "block_sizes"),
    ("3", "La pression d'une phase", "src/cotraffic/controllers/classical.py", "phase_pressure"),
    ("3", "Max-Pressure", "src/cotraffic/controllers/classical.py", "MaxPressure.act"),
    ("3", "Le biais β : une décision de la candidate", "src/cotraffic/controllers/hybrid.py",
     "HybridPolicy.act"),
    ("4", "Les ambulances proches d'un feu", "src/cotraffic/controllers/ev_preemption.py",
     "approaching"),
    ("4", "La demande de vert pour l'ambulance", "src/cotraffic/controllers/combined.py",
     "EvRuleGuide.requests"),
    ("5", "Le bouclier de sécurité", "src/cotraffic/envs/shield.py", "apply_shield"),
    ("6", "La candidate, telle qu'elle est construite", "src/cotraffic/controllers/registry.py",
     (69, 77, "method == CANDIDATE")),
    ("7", "La règle de classement sur la validation", "scripts/hybrid_rank.py", "classify"),
    ("8", "Le critère de l'oracle", "scripts/oracle_report.py", (76, 82, "ok = ok or")),
    ("9", "Les fichiers figés", "scripts/combined_final.py", (38, 47, "FROZEN = [")),
    ("9", "Le refus de démarrer", "scripts/combined_final.py", "frozen_since"),
    ("10", "Temps de trajet et attente", "src/cotraffic/evaluation/metrics.py",
     (241, 249, "travel = np.where")),
    ("11", "Le gain et le bootstrap croisé", "scripts/combined_analysis.py", "gain_draws"),
    ("11", "Holm et les verdicts", "scripts/combined_analysis.py", "with_holm"),
    ("11", "La correction de Holm", "src/cotraffic/analysis/stats.py", "holm"),
    ("12", "Le compromis : l'écart au meilleur", "scripts/combined_figures.py", "criteria"),
    ("12", "Les 71 trajets sur 72", "scripts/combined_figures.py", "ambulance_counts"),
    ("13", "Le conseiller : le biais sur les notes", "src/cotraffic/llm/advised.py",
     "AdvisedPolicy.bias_logits"),
    ("13 bis", "Ce que lit le LLM stratège", "src/cotraffic/llm/strategist.py", "network_state"),
    ("13 bis", "L'appel au LLM et ses garde-fous", "src/cotraffic/llm/strategist.py",
     "LlmStrategist._ask"),
    ("13 bis", "Le mode appliqué à la candidate", "src/cotraffic/llm/strategist.py",
     "LlmStrategyPolicy.act"),
]  # fmt: skip


def locate(path: Path, name: str) -> tuple[int, int]:
    """First and last line of a function or a method ("Class.method"), from the parser."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    parts = name.split(".")
    nodes = tree.body
    for k, part in enumerate(parts):
        last = k == len(parts) - 1
        kinds = (ast.FunctionDef, ast.AsyncFunctionDef) if last else (ast.ClassDef,)
        found = next((n for n in nodes if isinstance(n, kinds) and n.name == part), None)
        if found is None:
            raise LookupError(f"{name} not found in {path}")
        if last:
            first = min([found.lineno, *(d.lineno for d in found.decorator_list)])
            return first, int(found.end_lineno or found.lineno)
        nodes = found.body
    raise LookupError(name)


def excerpt(part: str, title: str, file: str, what) -> dict:
    path = ROOT / file
    lines = path.read_text(encoding="utf-8").splitlines()
    if isinstance(what, tuple):
        first, last, check = what
        if check not in "\n".join(lines[first - 1 : last]):
            raise ValueError(f"{file}:{first}-{last} no longer holds {check!r}: update the range")
        name = None
    else:
        first, last = locate(path, what)
        name = what
    return {"part": part, "title": title, "file": file, "name": name, "start": first,
            "end": last, "code": "\n".join(lines[first - 1 : last])}  # fmt: skip


def parts(text: str) -> list[dict]:
    """The document cut at each "## " heading; the text before the first one is the intro."""
    out, current = [], {"number": "", "title": "", "lines": []}
    for line in text.splitlines():
        m = re.match(r"^## (.+)$", line)
        if m:
            out.append(current)
            title = m.group(1).strip()
            num = re.match(r"^(\d+(?: bis)?)\.\s*(.*)$", title)
            current = {
                "number": num.group(1) if num else "",
                "title": num.group(2) if num else title,
                "lines": [],
            }
        else:
            current["lines"].append(line)
    out.append(current)
    sections = []
    for p in out:
        body = "\n".join(p["lines"]).strip().strip("-").strip()
        if not body and not p["title"]:
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", (p["number"] or p["title"] or "intro").lower()).strip("-")
        sections.append({"id": f"part-{slug}" if p["title"] else "intro", "number": p["number"],
                         "title": p["title"], "markdown": body})  # fmt: skip
    return sections


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    text = DOC.read_text(encoding="utf-8")
    title = text.splitlines()[0].lstrip("# ").strip()
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                            text=True, check=False).stdout.strip()  # fmt: skip
    found = parts(text)
    intro = found[0]["markdown"] if found and not found[0]["title"] else ""
    data = {
        "source": "docs/RESUME_CONTROLEUR_FINAL.md; code excerpts located in the files "
        "(scripts/export_guide.py)",
        "title": title,
        "commit": commit,
        # the first line of the intro is the document's own title
        "intro": "\n".join(intro.splitlines()[1:]).strip(),
        "sections": [s for s in found if s["title"]],
        "code": [excerpt(*e) for e in EXCERPTS],
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(OUT, len(data["sections"]), "parts,", len(data["code"]), "excerpts")


if __name__ == "__main__":
    main()
