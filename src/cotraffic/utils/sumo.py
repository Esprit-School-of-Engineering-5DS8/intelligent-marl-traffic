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
    """Absolute path of a SUMO executable such as ``sumo``, ``sumo-gui`` or ``netconvert``.

    A system install puts the executables in ``$SUMO_HOME/bin``. The pip wheel installs
    them into the environment's script directory instead, and on Windows an application
    control policy can block the system copy while leaving the wheel usable, so fall back
    to the interpreter's own directory and then to PATH.
    """
    home = find_sumo_home()
    exe = name + (".exe" if sys.platform == "win32" else "")
    candidates = [Path(sys.executable).resolve().parent / exe, home / "bin" / exe]
    on_path = shutil.which(name)
    if on_path:
        candidates.append(Path(on_path))
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    raise SumoNotFoundError(
        f"SUMO executable {exe} not found in {home / 'bin'} or next to the interpreter"
    )


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
    if os.environ.get("COTRAFFIC_FORCE_TRACI", "0") not in ("", "0", "false", "False"):
        # Some managed Windows machines block the libsumo DLL outright (application
        # control policy). The pure-python TraCI binding is slower but always loads.
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
    # SUMO's own ``traci`` package aliases itself to libsumo as soon as
    # LIBSUMO_AS_TRACI is *present* (even as "0"), and libsumo has no
    # ``getConnection``. Drop a false value before importing so the value, not
    # the presence, decides the binding — see ``cotraffic.env.load_dotenv``.
    os.environ.pop("LIBSUMO_AS_TRACI", None)
    import traci

    return traci
