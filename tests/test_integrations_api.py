"""Settings → Integrations reports, saves and tests real credentials.

The panel must never show a connection the backend cannot use, saving a key must apply
to the running process (no restart) and persist to ``.env`` — and a secret Mapbox token
must be refused, since the browser can only use a public one. The test endpoint spends a
real provider request; here it is monkeypatched so no network is required.

The tests never touch the developer's ``.env``: the fixture points the module at a
temporary file.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.main import app
from api.routes import assistant, integrations

client = TestClient(app)


@pytest.fixture()
def env_file(tmp_path, monkeypatch):
    target = tmp_path / ".env"
    target.write_text("# kept\nFRONTEND_ORIGIN=http://localhost:5173\n", encoding="utf-8")
    monkeypatch.setattr(integrations, "ENV_FILE", target)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("MAPBOX_TOKEN", raising=False)
    return target


def test_only_real_services_are_listed():
    body = client.get("/api/integrations").json()
    assert [entry["id"] for entry in body["integrations"]] == [
        "groq",
        "gemini",
        "openrouter",
        "mapbox",
        "sumo",
    ]
    assert all("configured" in entry for entry in body["integrations"])
    # Only the LLM providers can be pinged; SUMO is checked locally.
    assert [entry["id"] for entry in body["integrations"] if entry["testable"]] == [
        "groq",
        "gemini",
        "openrouter",
    ]


def test_saving_a_key_applies_without_restart(env_file):
    assert assistant.groq.status()["available"] is False

    response = client.put(
        "/api/integrations", json={"id": "groq", "value": "gsk_test_key_9876543210"}
    )
    assert response.status_code == 200
    groq = next(entry for entry in response.json()["integrations"] if entry["id"] == "groq")
    assert groq["configured"] is True
    assert groq["masked"] == "gsk_…3210"
    assert assistant.groq.status()["available"] is True

    saved = env_file.read_text(encoding="utf-8")
    assert "GROQ_API_KEY=gsk_test_key_9876543210" in saved
    assert "# kept" in saved
    assert "FRONTEND_ORIGIN=http://localhost:5173" in saved


def test_clearing_a_key_turns_it_off(env_file):
    client.put("/api/integrations", json={"id": "gemini", "value": "AIza-test-1234567890"})
    response = client.put("/api/integrations", json={"id": "gemini", "value": ""})
    gemini = next(entry for entry in response.json()["integrations"] if entry["id"] == "gemini")
    assert gemini["configured"] is False
    assert "GEMINI_API_KEY=" in env_file.read_text(encoding="utf-8")


def test_secret_mapbox_token_is_refused(env_file):
    response = client.put(
        "/api/integrations", json={"id": "mapbox", "value": "sk.secret.token.value"}
    )
    assert response.status_code == 422
    assert "public token" in response.json()["detail"]


def test_public_mapbox_token_is_shared_with_the_browser(env_file):
    token = "pk.eyJ1IjoiZGVtbyIsImEiOiJjbHh5In0.abcdef"
    response = client.put("/api/integrations", json={"id": "mapbox", "value": token})
    assert response.status_code == 200
    mapbox = next(entry for entry in response.json()["integrations"] if entry["id"] == "mapbox")
    assert mapbox["configured"] is True
    assert mapbox["token"] == token


def test_unknown_integration_is_refused(env_file):
    response = client.put("/api/integrations", json={"id": "ctecc", "value": "x"})
    assert response.status_code == 422
    assert "unknown integration" in response.json()["detail"]


# --------------------------------------------------------------- connection tests


def test_connection_test_needs_a_saved_key(env_file):
    response = client.post("/api/integrations/groq/test")
    assert response.status_code == 422
    assert "GROQ_API_KEY" in response.json()["detail"]


def test_connection_test_reports_groq_models(env_file, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_live_test")
    seen: dict[str, object] = {}

    def fake_remote(url: str, headers: dict[str, str]) -> dict[str, object]:
        seen["url"] = url
        seen["headers"] = headers
        return {"data": [{"id": "llama-3.1-8b-instant"}, {"id": "openai/gpt-oss-20b"}]}

    monkeypatch.setattr(integrations, "_remote_json", fake_remote)
    response = client.post("/api/integrations/groq/test")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["latencyMs"] >= 0
    assert "2 model(s) visible" in body["detail"]
    assert str(seen["url"]).startswith("https://api.groq.com/")
    assert seen["headers"] == {"Authorization": "Bearer gsk_live_test"}


def test_connection_test_reports_gemini_models(env_file, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-live-test")

    def fake_remote(url: str, headers: dict[str, str]) -> dict[str, object]:
        assert "generativelanguage.googleapis.com" in url
        assert headers == {"x-goog-api-key": "AIza-live-test"}
        return {"models": [{"name": "models/gemini-2.5-flash"}]}

    monkeypatch.setattr(integrations, "_remote_json", fake_remote)
    response = client.post("/api/integrations/gemini/test")
    assert response.status_code == 200
    assert "Gemini accepted the key" in response.json()["detail"]


def test_connection_test_reports_openrouter_models(env_file, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-live")

    def fake_remote(url: str, headers: dict[str, str]) -> dict[str, object]:
        assert url == "https://openrouter.ai/api/v1/models"
        assert headers == {"Authorization": "Bearer sk-or-v1-live"}
        return {"data": [{"id": "google/gemma-4-26b-a4b-it:free"}]}

    monkeypatch.setattr(integrations, "_remote_json", fake_remote)
    response = client.post("/api/integrations/openrouter/test")
    assert response.status_code == 200
    assert "OpenRouter accepted the key" in response.json()["detail"]


def test_connection_test_surfaces_provider_refusal(env_file, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-revoked")

    def fake_remote(url: str, headers: dict[str, str]) -> dict[str, object]:
        raise HTTPException(502, "the provider refused the key (401): API key not valid")

    monkeypatch.setattr(integrations, "_remote_json", fake_remote)
    response = client.post("/api/integrations/gemini/test")
    assert response.status_code == 502
    assert "API key not valid" in response.json()["detail"]


def test_integrations_without_a_key_are_not_testable(env_file):
    assert client.post("/api/integrations/sumo/test").status_code == 422
    assert client.post("/api/integrations/mapbox/test").status_code == 422
