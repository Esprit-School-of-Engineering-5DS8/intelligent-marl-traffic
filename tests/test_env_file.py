import os

from agents.llm.env import load_env_file, parse_env_file


def test_parse_env_file(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        "# comment\n"
        "\n"
        "LLM_MODEL=deepseek-v4.1-flash\n"
        "export LLM_TIMEOUT_S=90\n"
        "LLM_API_KEY=\"quoted value\"\n"
        "SINGLE='single quoted'\n"
        "NO_EQUALS_LINE\n"
        "EMPTY=\n",
        encoding="utf-8")
    values = parse_env_file(str(path))
    assert values["LLM_MODEL"] == "deepseek-v4.1-flash"
    assert values["LLM_TIMEOUT_S"] == "90"
    assert values["LLM_API_KEY"] == "quoted value"
    assert values["SINGLE"] == "single quoted"
    assert values["EMPTY"] == ""
    assert "NO_EQUALS_LINE" not in values


def test_load_env_file_env_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "from-env")
    monkeypatch.delenv("LLM_TEST_ONLY", raising=False)
    path = tmp_path / ".env"
    path.write_text("LLM_MODEL=from-file\nLLM_TEST_ONLY=yes\n", encoding="utf-8")
    loaded = load_env_file(str(path))
    assert os.environ["LLM_MODEL"] == "from-env"
    assert os.environ["LLM_TEST_ONLY"] == "yes"
    assert loaded == 1


def test_load_env_file_override(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "from-env")
    path = tmp_path / ".env"
    path.write_text("LLM_MODEL=from-file\n", encoding="utf-8")
    load_env_file(str(path), override=True)
    assert os.environ["LLM_MODEL"] == "from-file"


def test_load_env_file_missing():
    assert load_env_file("/nonexistent/nowhere/.env") == 0
