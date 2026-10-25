"""Progress lines in the logs of long runs, read by scripts/llm_watch.py.

PROGRESS <phase> <done>/<total> elapsed=<s> eta=<s>
"""

from __future__ import annotations

import time


class Progress:
    def __init__(self, phase: str, total: int, every: int = 1):
        self.phase = phase
        self.total = max(total, 1)
        self.every = max(every, 1)
        self.done = 0
        self.start = time.monotonic()
        self._print()

    def tick(self, n: int = 1) -> None:
        self.done += n
        if self.done % self.every == 0 or self.done >= self.total:
            self._print()

    def _print(self) -> None:
        elapsed = time.monotonic() - self.start
        eta = elapsed / self.done * (self.total - self.done) if self.done else -1
        print(
            f"PROGRESS {self.phase} {self.done}/{self.total} elapsed={elapsed:.0f} eta={eta:.0f}",
            flush=True,
        )
