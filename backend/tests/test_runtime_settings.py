"""Tests for runtime settings that should avoid environment-location surprises."""

from pathlib import Path

import pytest

from school_safety_validator import inspection_runtime_settings


def test_get_settings_loads_absolute_backend_env_path(monkeypatch) -> None:
    captured = {}

    def fake_load_dotenv(dotenv_path: Path, override: bool) -> None:
        captured["dotenv_path"] = Path(dotenv_path)
        captured["override"] = override

    monkeypatch.setattr(inspection_runtime_settings, "load_dotenv", fake_load_dotenv)

    inspection_runtime_settings.get_settings()

    assert captured["override"] is False
    assert captured["dotenv_path"].is_absolute()
    assert captured["dotenv_path"].name == ".env"
    assert captured["dotenv_path"].parent.name == "backend"


def test_get_settings_can_explicitly_override_from_dotenv(monkeypatch) -> None:
    captured = {}

    def fake_load_dotenv(dotenv_path: Path, override: bool) -> None:
        captured["override"] = override

    monkeypatch.setattr(inspection_runtime_settings, "load_dotenv", fake_load_dotenv)

    inspection_runtime_settings.get_settings(dotenv_override=True)

    assert captured["override"] is True


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [(None, False), ("false", False), ("true", True)],
)
def test_get_settings_reads_langsmith_tracing_as_an_explicit_opt_in(monkeypatch, raw_value, expected) -> None:
    monkeypatch.setattr(inspection_runtime_settings, "load_dotenv", lambda **_kwargs: False)
    if raw_value is None:
        monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    else:
        monkeypatch.setenv("LANGSMITH_TRACING", raw_value)

    settings = inspection_runtime_settings.get_settings()

    assert settings.langsmith_tracing is expected
