"""Signal programs are written by parallel runs: identical concurrent writes must not fail."""

import multiprocessing as mp
from pathlib import Path

from cotraffic.controllers.programs import _atomic_write

TEXT = "same plan\n" * 2000


def _writer(path: str) -> None:
    for _ in range(30):
        _atomic_write(Path(path), TEXT)


def test_parallel_identical_writes_succeed(tmp_path):
    path = tmp_path / "plan.json"
    procs = [mp.get_context("spawn").Process(target=_writer, args=(str(path),)) for _ in range(6)]
    for p in procs:
        p.start()
    for p in procs:
        p.join()
    assert [p.exitcode for p in procs] == [0] * 6
    assert path.read_text(encoding="utf-8") == TEXT
    assert not [f for f in tmp_path.iterdir() if ".tmp" in f.name]
