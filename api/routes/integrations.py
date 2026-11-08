"""``GET/PUT /api/integrations`` and ``POST /api/integrations/<id>/test``.

Settings → Integrations renders from this endpoint, so a card can never claim
"Connected" for something the backend cannot use. A service counts as configured when
its key is present in the environment or in the project ``.env`` (the same file the CLI
loads), SUMO is installed with its networks, or a Mapbox public token is saved.

``PUT`` upserts one key into ``.env`` and the running process, so the change applies
without restarting the backend. Only a Mapbox *public* token (``pk.…``) is accepted and
returned to the browser; a secret token stays server-side and is refused here.

``POST .../test`` spends one real request against the provider's models endpoint, so the
panel distinguishes "a key is saved" from "the provider accepts this key".
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / ".env"
NETWORKS_DIR = ROOT / "configs" / "networks"

router = APIRouter(tags=["integrations"])

# id -> (env var, input placeholder, what is degraded without it)
FIELDS: dict[str, tuple[str, str, str]] = {
    "groq": (
        "GROQ_API_KEY",
        "gsk_…",
        "the assistant and the LLM controller fall back to Max-Pressure",
    ),
    "gemini": (
        "GEMINI_API_KEY",
        "AIza…",
        "the LLM controller cannot use Gemini",
    ),
    "openrouter": (
        "OPENROUTER_API_KEY",
        "sk-or-v1-…",
        "the LLM controllers cannot reach Gemma 4 or any OpenRouter model",
    ),
    "mapbox": (
        "MAPBOX_TOKEN",
        "pk.…",
        "the live map stays offline until a public token is saved",
    ),
}

# Only the LLM providers answer a key check without spending simulation resources.
TESTABLE = ("groq", "gemini", "openrouter")
GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"
GEMINI_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _masked(value: str) -> str | None:
    if not value:
        return None
    return f"{value[:4]}…{value[-4:]}" if len(value) > 10 else f"…{value[-4:]}"


def _write_env(updates: dict[str, str]) -> None:
    """Upsert keys in ``.env``, keeping comments and every other entry in place."""
    try:
        lines = (
            ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.is_file() else []
        )
    except OSError as error:
        raise HTTPException(500, f"cannot read .env: {error}") from error

    pending = dict(updates)
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in pending:
                out.append(f"{key}={pending.pop(key)}")
                continue
        out.append(line)
    if pending:
        if out and out[-1].strip():
            out.append("")
        out.append("# Saved from Settings → Integrations")
        out.extend(f"{key}={value}" for key, value in pending.items())

    try:
        ENV_FILE.write_text("\n".join(out) + "\n", encoding="utf-8")
    except OSError as error:
        raise HTTPException(500, f"cannot write .env: {error}") from error


def _sumo_executable() -> Path | None:
    home = _env("SUMO_HOME")
    if not home:
        return None
    for name in ("sumo.exe", "sumo"):
        candidate = Path(home) / "bin" / name
        if candidate.is_file():
            return candidate
    return None


def _sumo_status() -> dict[str, Any]:
    executable = _sumo_executable()
    try:
        import sumolib  # noqa: F401

        has_library = True
    except ImportError:
        has_library = False
    networks = len(list(NETWORKS_DIR.glob("*.yaml"))) if NETWORKS_DIR.is_dir() else 0

    if executable is None:
        detail = (
            "SUMO_HOME is not set."
            if not _env("SUMO_HOME")
            else "no sumo binary under $SUMO_HOME/bin."
        )
    elif not has_library:
        detail = f"sumo found at {executable}, but sumolib is not installed."
    else:
        detail = f"sumo at {executable} · sumolib loaded · {networks} network configs"

    return {
        "id": "sumo",
        "label": "SUMO",
        "description": "Microscopic traffic simulator behind every scenario.",
        "envVar": "SUMO_HOME",
        "placeholder": None,
        "editable": False,
        "configured": executable is not None and has_library,
        "masked": None,
        "detail": detail,
    }


def statuses() -> list[dict[str, Any]]:
    """The real state of each integration, read from this process right now."""
    groq_key = _env("GROQ_API_KEY")
    gemini_key = _env("GEMINI_API_KEY") or _env("GOOGLE_API_KEY")
    openrouter_key = _env("OPENROUTER_API_KEY")
    mapbox_token = _env("MAPBOX_TOKEN")
    return [
        {
            "id": "groq",
            "label": "Groq",
            "description": "Assistant replies and the LLM traffic controller.",
            "envVar": "GROQ_API_KEY",
            "placeholder": FIELDS["groq"][1],
            "editable": True,
            "configured": bool(groq_key),
            "masked": _masked(groq_key),
            "detail": (
                f"Key {_masked(groq_key)} · model {_env('GROQ_MODEL') or 'openai/gpt-oss-20b'}"
                if groq_key
                else f"No key saved: {FIELDS['groq'][2]}."
            ),
        },
        {
            "id": "gemini",
            "label": "Gemini",
            "description": "Alternative provider for the LLM traffic controller.",
            "envVar": "GEMINI_API_KEY",
            "placeholder": FIELDS["gemini"][1],
            "editable": True,
            "configured": bool(gemini_key),
            "masked": _masked(gemini_key),
            "detail": (
                f"Key {_masked(gemini_key)} · model "
                f"{_env('GEMINI_MODEL') or _env('COTRAFFIC_LLM_MODEL') or 'gemini-2.5-flash'}"
                if gemini_key
                else f"No key saved: {FIELDS['gemini'][2]}."
            ),
        },
        {
            "id": "openrouter",
            "label": "OpenRouter",
            "description": "One key for Gemma 4 and the other hosted open models.",
            "envVar": "OPENROUTER_API_KEY",
            "placeholder": FIELDS["openrouter"][1],
            "editable": True,
            "configured": bool(openrouter_key),
            "masked": _masked(openrouter_key),
            "detail": (
                f"Key {_masked(openrouter_key)} · model "
                f"{_env('COTRAFFIC_LLM_MODEL') or _env('OPENROUTER_MODEL') or 'google/gemma-4-26b-a4b-it:free'}"
                if openrouter_key
                else f"No key saved: {FIELDS['openrouter'][2]}."
            ),
        },
        {
            "id": "mapbox",
            "label": "Mapbox",
            "description": "Street basemap under the live map and the corridor view.",
            "envVar": "MAPBOX_TOKEN",
            "placeholder": FIELDS["mapbox"][1],
            "editable": True,
            "configured": bool(mapbox_token),
            "masked": _masked(mapbox_token),
            # A public token is meant for the browser; a secret one never leaves the server.
            "token": mapbox_token if mapbox_token.startswith("pk.") else None,
            "detail": (
                f"Public token {_masked(mapbox_token)}"
                if mapbox_token.startswith("pk.")
                else (
                    "A secret token is saved; browsers need a public pk. token."
                    if mapbox_token
                    else f"No token saved: {FIELDS['mapbox'][2]}."
                )
            ),
        },
        _sumo_status(),
    ]


def _body() -> dict[str, Any]:
    entries = [{**entry, "testable": entry["id"] in TESTABLE} for entry in statuses()]
    return {"envFile": ".env", "integrations": entries}


class IntegrationUpdate(BaseModel):
    id: str = Field(min_length=1, max_length=20)
    value: str = Field(default="", max_length=400)


@router.get("/api/integrations")
def integrations() -> dict[str, Any]:
    return _body()


@router.put("/api/integrations")
def update_integration(req: IntegrationUpdate) -> dict[str, Any]:
    """Save (or clear, with an empty ``value``) one credential and apply it immediately."""
    if req.id not in FIELDS:
        raise HTTPException(422, f"unknown integration {req.id!r}")
    env_var = FIELDS[req.id][0]
    value = req.value.strip()
    if req.id == "mapbox" and value and not value.startswith("pk."):
        raise HTTPException(
            422,
            "Mapbox needs a public token (starts with pk.); secret tokens stay out of the dashboard",
        )
    if req.id in ("groq", "gemini", "openrouter") and value and any(
        char.isspace() for char in value
    ):
        raise HTTPException(422, "API keys cannot contain spaces")

    if value:
        os.environ[env_var] = value
    else:
        os.environ.pop(env_var, None)
    _write_env({env_var: value})
    return _body()


def _remote_json(url: str, headers: dict[str, str]) -> dict[str, Any]:
    """GET a provider endpoint. A refusal is reported with the provider's own message."""
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", "replace").strip()
        raise HTTPException(
            502, f"the provider refused the key ({error.code}): {body[:200] or error.reason}"
        ) from error
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
        raise HTTPException(502, f"could not reach the provider: {error}") from error


@router.post("/api/integrations/{integration_id}/test")
def test_integration(integration_id: str) -> dict[str, Any]:
    """Spend one real request to prove the saved key works, and time it."""
    if integration_id not in TESTABLE:
        raise HTTPException(422, f"{integration_id} has no key to test")
    env_var = FIELDS[integration_id][0]
    key = _env(env_var)
    if not key:
        raise HTTPException(422, f"save {env_var} first, then test it")

    started = time.perf_counter()
    if integration_id == "groq":
        body = _remote_json(GROQ_MODELS_URL, {"Authorization": f"Bearer {key}"})
        found = len(body.get("data") or [])
        label = "Groq"
    elif integration_id == "openrouter":
        body = _remote_json(OPENROUTER_MODELS_URL, {"Authorization": f"Bearer {key}"})
        found = len(body.get("data") or [])
        label = "OpenRouter"
    else:
        body = _remote_json(GEMINI_MODELS_URL, {"x-goog-api-key": key})
        found = len(body.get("models") or [])
        label = "Gemini"
    elapsed = round((time.perf_counter() - started) * 1000, 1)
    return {
        "id": integration_id,
        "ok": True,
        "latencyMs": elapsed,
        "detail": f"{label} accepted the key · {found} model(s) visible",
    }
