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
FIGURES_DIR = REPO_ROOT / "figures"
DOCS_DIR = REPO_ROOT / "docs"
