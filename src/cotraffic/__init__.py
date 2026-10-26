"""CoTraffic: cooperative multi-agent traffic signal control on SUMO."""

import logging
import os

from cotraffic.env import load_dotenv

load_dotenv()


def _configure_llm_logging() -> None:
    enabled = os.environ.get("COTRAFFIC_LLM_LOG", "0").lower()
    if enabled in ("", "0", "false", "no", "off"):
        return
    logger = logging.getLogger("cotraffic.llm")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)


_configure_llm_logging()

__version__ = "0.1.0"
