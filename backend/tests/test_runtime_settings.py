"""Tests for runtime settings that should avoid environment-location surprises."""

from pathlib import Path

from school_safety_validator import inspection_runtime_settings


def test_get_settings_loads_absolute_backend_env_path(monkeypatch) -> None:
    captured = {}

    def fake_load_dotenv(dotenv_path: Path, override: bool) -> None:
        captured["dotenv_path"] = Path(dotenv_path)
        captured["override"] = override

    monkeypatch.setattr(inspection_runtime_settings, "load_dotenv", fake_load_dotenv)

    inspection_runtime_settings.get_settings()

    assert captured["override"] is True
    assert captured["dotenv_path"].is_absolute()
    assert captured["dotenv_path"].name == ".env"
    assert captured["dotenv_path"].parent.name == "backend"
