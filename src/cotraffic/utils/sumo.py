"""Locating SUMO and choosing the Python binding (libsumo or TraCI).

SUMO can come from a system install (``SUMO_HOME`` set), from the ``eclipse-sumo``
pip wheel (which ships the binaries inside the ``sumo`` package), or simply be on
``PATH``. We try these in that order and fail with an explicit message otherwise.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from functools import lru_cache
from pathlib import Path
from types import ModuleType


class SumoNotFoundError(RuntimeError):
    pass


def _has_binary(home: Path, name: str = "sumo") -> bool:
    exe = name + (".exe" if sys.platform == "win32" else "")
    return (home / "bin" / exe).is_file()


@lru_cache(maxsize=1)
def find_sumo_home() -> Path:
    """Return the SUMO installation directory and export it as ``SUMO_HOME``."""
    candidates: list[Path] = []
    if os.environ.get("SUMO_HOME"):
        candidates.append(Path(os.environ["SUMO_HOME"]))
    try:
        import sumo  # the eclipse-sumo wheel

        candidates.append(Path(sumo.SUMO_HOME))
    except (ImportError, AttributeError):
        pass
    on_path = shutil.which("sumo")
    if on_path:
        candidates.append(Path(on_path).resolve().parent.parent)

    for home in candidates:
        if _has_binary(home):
            os.environ["SUMO_HOME"] = str(home)
            return home
    raise SumoNotFoundError(
        "SUMO not found. Install it with `pip install eclipse-sumo` or set SUMO_HOME "
        f"to a SUMO installation (checked: {[str(c) for c in candidates] or 'nothing'})."
    )


def binary(name: str = "sumo") -> str:
    """Absolute path of a SUMO executable such as ``sumo``, ``sumo-gui`` or ``netconvert``."""
    home = find_sumo_home()
    exe = name + (".exe" if sys.platform == "win32" else "")
    path = home / "bin" / exe
    if not path.is_file():
        raise SumoNotFoundError(f"SUMO executable {exe} not found in {home / 'bin'}")
    return str(path)


def tool(relative: str) -> Path:
    """Path of a script from SUMO's ``tools`` directory, e.g. ``tlsCycleAdaptation.py``."""
    home = find_sumo_home()
    matches = [home / "tools" / relative] + list((home / "tools").rglob(Path(relative).name))
    for path in matches:
        if path.is_file():
            return path
    raise SumoNotFoundError(f"SUMO tool {relative} not found under {home / 'tools'}")


def use_libsumo(gui: bool = False) -> bool:
    """libsumo is much faster than TraCI but cannot drive sumo-gui."""
    if gui:
        return False
    if os.environ.get("LIBSUMO_AS_TRACI", "0") in ("", "0", "false", "False"):
        return False
    return importlib.util.find_spec("libsumo") is not None


def backend(gui: bool = False) -> ModuleType:
    """Import the simulation binding. Both modules expose the same API."""
    find_sumo_home()
    if use_libsumo(gui):
        import libsumo

        return libsumo
    import traci

    return traci
