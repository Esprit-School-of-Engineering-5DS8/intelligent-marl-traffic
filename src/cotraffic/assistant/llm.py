"""Local language model served by Ollama (free, runs on the laptop, no account or quota).

Only the HTTP API of the Ollama server is used, with the standard library, so the project
gains no dependency. Settings come from the environment:

    COTRAFFIC_LLM_URL     server address (default http://localhost:11434)
    COTRAFFIC_LLM_MODEL   model name (default qwen2.5:3b)
    COTRAFFIC_LLM_TIMEOUT seconds before a request is abandoned (default 90)

Every failure - server not running, model missing, timeout, output that does not match
the expected JSON schema - raises :class:`LLMUnavailableError`; callers then use their
deterministic fallback.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

DEFAULT_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5:3b"


class LLMUnavailableError(RuntimeError):
    """The model could not give a usable answer; use the fallback."""


def validate(value: Any, schema: Mapping[str, Any], path: str = "$") -> list[str]:
    """Problems of ``value`` against the subset of JSON Schema we use (type, enum,
    required, properties, items, minimum, maximum, additionalProperties: false)."""
    problems: list[str] = []
    kind = schema.get("type")
    types = {
        "object": dict,
        "array": list,
        "string": str,
        "boolean": bool,
        "integer": int,
        "number": (int, float),
        "null": type(None),
    }
    allowed = kind if isinstance(kind, list) else [kind] if kind else []
    if allowed:
        ok = False
        for k in allowed:
            t = types[k]
            if k in ("integer", "number") and isinstance(value, bool):
                continue
            if isinstance(value, t):
                ok = True
        if not ok:
            return [f"{path}: expected {kind}, got {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        problems.append(f"{path}: {value!r} not in {schema['enum']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            problems.append(f"{path}: {value} < {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            problems.append(f"{path}: {value} > {schema['maximum']}")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                problems.append(f"{path}: missing {key!r}")
        for key, item in value.items():
            if key in props:
                problems += validate(item, props[key], f"{path}.{key}")
            elif schema.get("additionalProperties") is False:
                problems.append(f"{path}: unexpected {key!r}")
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            problems += validate(item, schema["items"], f"{path}[{i}]")
    return problems


@dataclass
class LocalLLM:
    url: str = field(default_factory=lambda: os.environ.get("COTRAFFIC_LLM_URL", DEFAULT_URL))
    model: str = field(default_factory=lambda: os.environ.get("COTRAFFIC_LLM_MODEL", DEFAULT_MODEL))
    timeout_s: float = field(
        default_factory=lambda: float(os.environ.get("COTRAFFIC_LLM_TIMEOUT", "90"))
    )

    def _request(self, path: str, payload: dict | None, timeout: float) -> dict:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.url.rstrip("/") + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method="GET" if payload is None else "POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as err:
            raise LLMUnavailableError(f"{self.url}{path}: {err}") from err

    def status(self) -> tuple[bool, str]:
        """(usable, message) - whether the server answers and has the model."""
        try:
            tags = self._request("/api/tags", None, timeout=3.0)
        except LLMUnavailableError:
            return False, (
                f"no Ollama server at {self.url}: install Ollama (https://ollama.com) "
                f"and run `ollama pull {self.model}`"
            )
        names = {m.get("name", "") for m in tags.get("models", [])}
        wanted = {self.model, f"{self.model}:latest"}
        if not names & wanted:
            return (
                False,
                f"Ollama is running but {self.model} is missing: `ollama pull {self.model}`",
            )
        return True, f"{self.model} on {self.url}"

    def chat(
        self,
        messages: Sequence[Mapping[str, str]],
        schema: Mapping[str, Any] | None = None,
        max_tokens: int = 400,
    ) -> str:
        """One reply, deterministic settings (temperature 0, fixed seed)."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": list(messages),
            "stream": False,
            "keep_alive": "15m",
            "options": {"temperature": 0, "seed": 0, "num_predict": max_tokens},
        }
        if schema is not None:
            payload["format"] = dict(schema)  # constrained decoding to this JSON schema
        reply = self._request("/api/chat", payload, timeout=self.timeout_s)
        content = reply.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise LLMUnavailableError("empty reply")
        return content

    def chat_json(
        self,
        messages: Sequence[Mapping[str, str]],
        schema: Mapping[str, Any],
        attempts: int = 2,
    ) -> dict:
        """A reply that parses as JSON and satisfies ``schema``, or LLMUnavailableError."""
        history = list(messages)
        last = ""
        for _ in range(attempts):
            text = self.chat(history, schema=schema)
            try:
                value = json.loads(text)
            except ValueError:
                last = f"not JSON: {text[:80]!r}"
            else:
                problems = validate(value, schema)
                if not problems:
                    return value
                last = "; ".join(problems[:3])
            # decoding is deterministic, so a retry must change the input: say what was wrong
            history += [
                {"role": "assistant", "content": text},
                {
                    "role": "user",
                    "content": f"Invalid answer ({last}). Reply again with JSON "
                    "that matches the schema exactly, using only the allowed values.",
                },
            ]
        raise LLMUnavailableError(f"invalid structured output ({last})")
