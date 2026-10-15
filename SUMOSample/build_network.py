#!/usr/bin/env python3
"""Regenerate Sample.net.xml from the editable SUMO network source files."""

import shutil
import subprocess
from pathlib import Path


SAMPLE_DIR = Path(__file__).resolve().parent
NETCONVERT = shutil.which("netconvert")

if NETCONVERT is None:
    raise SystemExit("netconvert was not found; install SUMO and add it to PATH.")

subprocess.run(
    [
        NETCONVERT,
        "--node-files", "Sample.nod.xml",
        "--edge-files", "Sample.edg.xml",
        "--connection-files", "Sample.con.xml",
        "--tllogic-files", "Sample.tll.xml",
        "--crossings.guess",
        "--default.crossing-width", "6",
        "--no-turnarounds", "true",
        "--output-file", "Sample.net.xml",
    ],
    cwd=SAMPLE_DIR,
    check=True,
)
