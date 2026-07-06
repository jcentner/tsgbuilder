"""Tests for web_app import-time side effects."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest


@pytest.mark.unit
def test_import_web_app_does_not_create_env_file(tmp_path):
    """Importing web_app should not create .env as a side effect."""
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()
    env.pop("PROJECT_ENDPOINT", None)
    env.pop("MODEL_DEPLOYMENT_NAME", None)
    env.pop("TSG_TEST_MODE", None)

    result = subprocess.run(
        [sys.executable, "-c", "import web_app"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not (tmp_path / ".env").exists()


@pytest.mark.unit
def test_import_web_app_loads_existing_env_file(tmp_path):
    """Importing web_app should load an existing app-dir .env file."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "PROJECT_ENDPOINT=https://example.test/api/projects/test\nMODEL_DEPLOYMENT_NAME=gpt-5.2\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()
    env.pop("PROJECT_ENDPOINT", None)
    env.pop("MODEL_DEPLOYMENT_NAME", None)
    env.pop("TSG_TEST_MODE", None)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os, web_app; print(os.environ.get('PROJECT_ENDPOINT', ''))",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "https://example.test/api/projects/test"
    assert env_file.read_text(encoding="utf-8").startswith("PROJECT_ENDPOINT=https://example.test")


@pytest.mark.unit
def test_import_error_utils_does_not_import_pipeline(tmp_path):
    """Importing error_utils should not import pipeline orchestration."""
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, error_utils; print('pipeline' in sys.modules)",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"


@pytest.mark.unit
def test_main_creates_env_file(tmp_path, monkeypatch):
    """main() should create .env for first-run app startup."""
    import web_app

    monkeypatch.setattr(web_app, "_get_app_dir", lambda: tmp_path)
    monkeypatch.setattr(web_app.app, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(web_app, "_open_browser", lambda url: None)
    monkeypatch.setattr(web_app.telemetry, "is_telemetry_enabled", lambda: False)

    class ImmediateTimer:
        def __init__(self, *_args, **_kwargs):
            pass

        def start(self):
            return None

    class NoopThread:
        def __init__(self, *_args, **_kwargs):
            pass

        def start(self):
            return None

    monkeypatch.setattr(web_app.threading, "Timer", ImmediateTimer)
    monkeypatch.setattr(web_app.threading, "Thread", NoopThread)

    web_app.main()

    env_file = tmp_path / ".env"
    assert env_file.exists()
    assert "MODEL_DEPLOYMENT_NAME=gpt-5.2" in env_file.read_text(encoding="utf-8")
