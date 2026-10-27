"""Standard locations inside the repository.

The root can be overridden with ``COTRAFFIC_ROOT`` (useful on Kaggle/Colab when the
package is installed from a clone that lives somewhere else).
"""

from __future__ import annotations

import os
from pathlib import Path


def _detect_root() -> Path:
    env = os.environ.get("COTRAFFIC_ROOT")
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve().parents[2]
    if (here / "configs").is_dir():
        return here
    return Path.cwd().resolve()


REPO_ROOT = _detect_root()
CONFIG_DIR = REPO_ROOT / "configs"
SUMO_DIR = REPO_ROOT / "sumo_files"
ROUTES_DIR = SUMO_DIR / "routes"
RESULTS_DIR = REPO_ROOT / "results"
RAW_DIR = RESULTS_DIR / "raw"
SUMMARY_DIR = RESULTS_DIR / "summary"
LOGS_DIR = RESULTS_DIR / "logs"
TRAINING_DIR = RESULTS_DIR / "training"
CHECKPOINTS_DIR = RESULTS_DIR / "checkpoints"
EXTRA_DIR = RESULTS_DIR / "extra"  # dashboard measurements, apart from the report's results
FIGURES_DIR = REPO_ROOT / "figures"
DOCS_DIR = REPO_ROOT / "docs"

# Every network trains its own agents. Kept as a hook for derived networks: map a
# network to the one whose checkpoints it should run.
TRAINED_ON: dict[str, str] = {}


def default_checkpoint(agent: str, network: str) -> Path:
    """Training run 1 of ``agent`` on ``network`` (or on the network it derives from)."""
    return CHECKPOINTS_DIR / agent / TRAINED_ON.get(network, network) / "seed1.zip"
