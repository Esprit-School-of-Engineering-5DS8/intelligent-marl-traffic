"""
environment/_bootstrap.py
Shared SUMO_HOME/tools bootstrap so `import traci` works on classic installs.
pip-installed SUMO (eclipse-sumo) does not need this, but it is harmless there.
"""

import os
import sys


def ensure_sumo_on_path() -> str:
    """Locate SUMO_HOME if unset and put its tools/ directory on sys.path."""
    if "SUMO_HOME" not in os.environ:
        if sys.platform == "win32":
            default_win = r"C:\Program Files (x86)\Eclipse\Sumo"
            if os.path.exists(default_win):
                os.environ["SUMO_HOME"] = default_win
        else:
            default_linux = "/usr/share/sumo"
            if os.path.exists(default_linux):
                os.environ["SUMO_HOME"] = default_linux

    sumo_home = os.environ.get("SUMO_HOME", "")
    tools_dir = os.path.join(sumo_home, "tools") if sumo_home else ""
    if tools_dir and os.path.isdir(tools_dir) and tools_dir not in sys.path:
        sys.path.append(tools_dir)
    return sumo_home
