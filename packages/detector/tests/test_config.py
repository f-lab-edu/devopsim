import pytest

from detector.config import (
    ALERTMANAGER_DEFAULT,
    LOKI_DEFAULT,
    MODEL_DEFAULT,
    PROMETHEUS_DEFAULT,
    Config,
)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "ANTHROPIC_API_KEY",
        "DETECTOR_MODEL",
        "PROMETHEUS_URL",
        "LOKI_URL",
        "ALERTMANAGER_URL",
        "SLACK_WEBHOOK_URL",
        "ALLOWED_NAMESPACES",
        "MAX_STEPS",
        "DRY_RUN",
    ):
        monkeypatch.delenv(key, raising=False)


def test_anthropic_key_required(clean_env: None) -> None:
    with pytest.raises(KeyError):
        Config.from_env()


def test_defaults(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    cfg = Config.from_env()
    assert cfg.anthropic_api_key == "sk-test"
    assert cfg.model == MODEL_DEFAULT
    assert cfg.prometheus_url == PROMETHEUS_DEFAULT
    assert cfg.loki_url == LOKI_DEFAULT
    assert cfg.alertmanager_url == ALERTMANAGER_DEFAULT
    assert cfg.slack_webhook_url == ""
    assert cfg.allowed_namespaces == ("api",)
    assert cfg.max_steps == 10
    assert cfg.dry_run is False


def test_overrides(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    monkeypatch.setenv("DETECTOR_MODEL", "claude-opus-4-7")
    monkeypatch.setenv("ALLOWED_NAMESPACES", "api, monitoring ,redis")
    monkeypatch.setenv("MAX_STEPS", "5")
    monkeypatch.setenv("DRY_RUN", "true")
    cfg = Config.from_env()
    assert cfg.model == "claude-opus-4-7"
    assert cfg.allowed_namespaces == ("api", "monitoring", "redis")
    assert cfg.max_steps == 5
    assert cfg.dry_run is True


def test_dry_run_false_variants(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    for val in ("false", "False", "0", "no", ""):
        monkeypatch.setenv("DRY_RUN", val)
        assert Config.from_env().dry_run is False
