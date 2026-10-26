"""Tests for the dependency-free .env loader."""

from __future__ import annotations

import os

from cotraffic.env import load_dotenv, parse_dotenv


def test_parse_dotenv_handles_comments_exports_and_quotes():
    text = """
    # comment
    export KEMETRA_TEST_KEY="from file"
    KEMETRA_TEST_NEW='new value'
    KEMETRA_TEST_EMPTY=
    """
    assert parse_dotenv(text) == {
        "KEMETRA_TEST_KEY": "from file",
        "KEMETRA_TEST_NEW": "new value",
        "KEMETRA_TEST_EMPTY": "",
    }


def test_load_dotenv_does_not_override_shell(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text(
        'KEMETRA_TEST_KEY="from-file"\nKEMETRA_TEST_NEW=from-file\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("KEMETRA_TEST_KEY", "from-shell")
    monkeypatch.delenv("KEMETRA_TEST_NEW", raising=False)

    assert load_dotenv(path) == path
    assert os.environ["KEMETRA_TEST_KEY"] == "from-shell"
    assert os.environ["KEMETRA_TEST_NEW"] == "from-file"
