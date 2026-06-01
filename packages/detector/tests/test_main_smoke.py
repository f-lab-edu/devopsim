"""Smoke tests for detector.main.build_app wiring.

1. build_app가 AppContext의 모든 필드를 채워 반환
2. tools 14개가 정확한 이름으로 조립됨
"""

from __future__ import annotations

import pytest
from prometheus_client import CollectorRegistry

import detector.metrics as detector_metrics
from detector.config import Config
from detector.main import build_app

EXPECTED_TOOL_NAMES = {
    "kubectl_get",
    "kubectl_describe",
    "kubectl_logs",
    "kubectl_events",
    "kubectl_rollout_history",
    "promql_query",
    "promql_range",
    "loki_query",
    "loki_query_range",
    "alertmanager_list_alerts",
    "fetch_runbook",
    "restart_deployment",
    "scale_deployment",
    "delete_pod",
}


@pytest.fixture(autouse=True)
def _isolate_metrics_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(detector_metrics, "REGISTRY", CollectorRegistry())


@pytest.fixture
def fake_config() -> Config:
    return Config(
        anthropic_api_key="sk-test",
        model="claude-test",
        prometheus_url="http://localhost:9090",
        loki_url="http://localhost:3100",
        alertmanager_url="http://localhost:9093",
        grafana_url="http://localhost:3000",
        slack_webhook_url="http://localhost:9999",
        allowed_namespaces=("api",),
        max_steps=10,
        dry_run=False,
    )


async def test_build_app_returns_app_context_with_required_fields(fake_config: Config) -> None:
    app = await build_app(fake_config)
    assert app.config is fake_config
    assert app.metrics is not None
    assert callable(app.event_handler)
    assert callable(app.pod_status_handler)
    assert callable(app.annotation_handler)
    assert callable(app.poll_once)


async def test_build_app_assembles_fourteen_tools_with_expected_names(fake_config: Config) -> None:
    app = await build_app(fake_config)
    assert len(app.tools) == 14
    actual_tool_names = {t.name for t in app.tools}
    assert actual_tool_names == EXPECTED_TOOL_NAMES
