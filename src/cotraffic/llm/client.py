"""Client of the local Ollama server: constrained JSON output, timing, model fingerprint.

Nothing leaves the machine: the server runs on localhost. Every call returns its measured
latency and token counts, which the advisor turns into a delay in simulated time.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any

DEFAULT_URL = "http://localhost:11434"  # [Exigence 2] modèle local : rien ne sort


@dataclass(frozen=True)
class Options:  # [Exigence 3] hyperparamètres envoyés à Ollama (configs/llm.yaml)
    """Inference settings. The values and their justification are in configs/llm.yaml
    (llm.settings reads it; the defaults here match it, see tests/test_llm_settings.py)."""

    temperature: float = 0.0
    top_p: float = 1.0
    top_k: int = 1
    repeat_penalty: float = 1.0
    num_ctx: int = 4096
    num_predict: int = 96
    seed: int = 0
    timeout_s: float = 60.0
    keep_alive: str = "30m"

    def ollama(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("timeout_s")
        d.pop("keep_alive")
        return d


@dataclass
class Reply:
    text: str
    latency_s: float
    prompt_tokens: int
    output_tokens: int
    done_reason: str


@dataclass
class ToolReply:
    message: dict[str, Any]  # role, content, tool_calls
    latency_s: float
    prompt_tokens: int
    output_tokens: int


class LLMError(RuntimeError):
    """No usable answer: server down, timeout or empty reply."""


class Ollama:
    def __init__(self, model: str, options: Options | None = None, url: str = DEFAULT_URL):
        self.model = model
        self.options = options or Options()
        self.url = url.rstrip("/")

    def _post(self, path: str, body: dict[str, Any], timeout: float) -> dict[str, Any]:
        req = urllib.request.Request(
            self.url + path, json.dumps(body).encode("utf-8"), {"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:  # [Exigence 9] timeout
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as err:
            raise LLMError(f"{self.model}: {err}") from err

    def chat(self, messages: list[dict[str, str]], schema: dict[str, Any] | None = None) -> Reply:
        body: dict[str, Any] = {  # [Exigence 2] requête au modèle choisi, via Ollama
            "model": self.model,
            "messages": messages,
            "stream": False,
            "keep_alive": self.options.keep_alive,
            "options": self.options.ollama(),
        }
        if schema is not None:
            body["format"] = schema  # [Exigence 4] sortie contrainte par le schéma JSON
        if self.model.startswith("qwen3"):
            body["think"] = False  # no hidden reasoning: it would multiply the latency
        start = time.perf_counter()
        out = self._post("/api/chat", body, self.options.timeout_s)
        latency = time.perf_counter() - start
        text = (out.get("message") or {}).get("content") or ""
        if not text.strip():
            raise LLMError(f"{self.model}: empty reply")
        return Reply(
            text=text,
            latency_s=latency,
            prompt_tokens=int(out.get("prompt_eval_count") or 0),
            output_tokens=int(out.get("eval_count") or 0),
            done_reason=str(out.get("done_reason") or ""),
        )

    def chat_tools(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ToolReply:
        """One model turn with function calling: the reply may hold ``tool_calls``."""
        body: dict[str, Any] = {  # [Exigence 5] requête avec les outils (function calling)
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "stream": False,
            "keep_alive": self.options.keep_alive,
            "options": self.options.ollama(),
        }
        if self.model.startswith("qwen3"):
            body["think"] = False
        start = time.perf_counter()
        out = self._post("/api/chat", body, self.options.timeout_s)
        return ToolReply(
            message=out.get("message") or {},
            latency_s=time.perf_counter() - start,
            prompt_tokens=int(out.get("prompt_eval_count") or 0),
            output_tokens=int(out.get("eval_count") or 0),
        )

    def warm_up(self) -> None:
        """Load the model in memory (the first call also pays the loading time)."""
        self.chat([{"role": "user", "content": "ok"}])

    def fingerprint(self) -> dict[str, Any]:
        """Digest, size, parameters and quantisation of the installed model."""
        req = urllib.request.Request(self.url + "/api/tags")
        with urllib.request.urlopen(req, timeout=10) as response:
            tags = json.loads(response.read().decode("utf-8"))
        for m in tags.get("models", []):
            if m.get("name") in (self.model, f"{self.model}:latest"):
                details = m.get("details") or {}
                return {
                    "model": self.model,
                    "digest": m.get("digest", ""),
                    "size_bytes": m.get("size", 0),
                    "parameters": details.get("parameter_size", ""),
                    "quantization": details.get("quantization_level", ""),
                    "family": details.get("family", ""),
                }
        raise LLMError(f"model {self.model} is not installed (ollama pull {self.model})")
