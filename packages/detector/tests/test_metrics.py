"""Tests for detector.metrics — Prometheus metrics for the detector agent.

TDD Red phase: covers AC-1..AC-6 + EC-1 from
.plan/specs/detector-metrics.md (7 tests total).
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry

from detector.agent.loop import InvestigationResult, ToolCallLog
from detector.metrics import DetectorMetrics, start_metrics_server


def _make_result(
    *,
    stop_reason: str = "end_turn",
    duration_seconds: float = 0.0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    tool_calls: list[ToolCallLog] | None = None,
) -> InvestigationResult:
    """Build an InvestigationResult with metric-relevant attrs.

    The dataclass in detector.agent.loop has total_input_tokens/total_output_tokens
    and no duration_seconds/cache_read_input_tokens fields, but the spec requires
    record_investigation to consume duration_seconds + input/output/cache_read token
    counts. We set them as instance attrs so DetectorMetrics can read them.
    """
    result = InvestigationResult(
        final_text="",
        stop_reason=stop_reason,
        tool_calls=list(tool_calls or []),
        steps=1,
        total_input_tokens=input_tokens,
        total_output_tokens=output_tokens,
    )
    # Extra fields the spec requires record_investigation to read.
    result.duration_seconds = duration_seconds  # type: ignore[attr-defined]
    result.input_tokens = input_tokens  # type: ignore[attr-defined]
    result.output_tokens = output_tokens  # type: ignore[attr-defined]
    result.cache_read_input_tokens = cache_read_tokens  # type: ignore[attr-defined]
    return result


# ---------- AC-1 ----------
def test_ac1_four_metrics_registered_on_registry() -> None:
    registry = CollectorRegistry()
    DetectorMetrics(registry=registry)

    names: set[str] = set()
    for collector in list(registry._names_to_collectors.values()):
        for metric in collector.collect():
            names.add(metric.name)

    assert "detector_investigations" in names or "detector_investigations_total" in names
    assert "detector_tool_calls" in names or "detector_tool_calls_total" in names
    assert "detector_investigation_duration_seconds" in names
    assert "detector_tokens_used" in names or "detector_tokens_used_total" in names


# ---------- AC-2 ----------
def test_ac2_record_investigation_increments_investigations_total() -> None:
    registry = CollectorRegistry()
    metrics = DetectorMetrics(registry=registry)
    result = _make_result(stop_reason="end_turn")

    metrics.record_investigation(result, trigger_source="k8s_event")

    value = registry.get_sample_value(
        "detector_investigations_total",
        {"trigger": "k8s_event", "result": "end_turn"},
    )
    assert value == 1.0


# ---------- AC-3 ----------
def test_ac3_record_investigation_observes_duration_histogram() -> None:
    registry = CollectorRegistry()
    metrics = DetectorMetrics(registry=registry)
    result = _make_result(stop_reason="end_turn", duration_seconds=2.5)

    metrics.record_investigation(result, trigger_source="k8s_event")

    count = registry.get_sample_value("detector_investigation_duration_seconds_count", {})
    total = registry.get_sample_value("detector_investigation_duration_seconds_sum", {})
    assert count == 1.0
    assert total == 2.5


# ---------- AC-4 ----------
def test_ac4_record_investigation_adds_token_counters() -> None:
    registry = CollectorRegistry()
    metrics = DetectorMetrics(registry=registry)
    result = _make_result(
        stop_reason="end_turn",
        input_tokens=100,
        output_tokens=50,
        cache_read_tokens=20,
    )

    metrics.record_investigation(result, trigger_source="k8s_event")

    input_v = registry.get_sample_value("detector_tokens_used_total", {"type": "input"})
    output_v = registry.get_sample_value("detector_tokens_used_total", {"type": "output"})
    cache_v = registry.get_sample_value("detector_tokens_used_total", {"type": "cache_read"})
    assert input_v == 100.0
    assert output_v == 50.0
    assert cache_v == 20.0


# ---------- AC-5 ----------
def test_ac5_record_investigation_inc_tool_calls_with_status() -> None:
    registry = CollectorRegistry()
    metrics = DetectorMetrics(registry=registry)
    result = _make_result(
        stop_reason="end_turn",
        tool_calls=[
            ToolCallLog(name="kubectl_get_pods", input={}, output="ok-output"),
            ToolCallLog(name="kubectl_logs", input={}, output="Error: ValueError: x"),
        ],
    )

    metrics.record_investigation(result, trigger_source="k8s_event")

    ok_v = registry.get_sample_value(
        "detector_tool_calls_total",
        {"tool": "kubectl_get_pods", "status": "ok"},
    )
    err_v = registry.get_sample_value(
        "detector_tool_calls_total",
        {"tool": "kubectl_logs", "status": "error"},
    )
    assert ok_v == 1.0
    assert err_v == 1.0


# ---------- AC-6 ----------
def test_ac6_start_metrics_server_calls_prometheus_start_http_server(monkeypatch) -> None:
    captured: dict[str, int] = {}

    def fake_start(port: int, *args, **kwargs) -> None:
        captured["port"] = port

    import prometheus_client

    monkeypatch.setattr(prometheus_client, "start_http_server", fake_start)
    # Also patch the module-local reference if metrics.py imported the symbol directly.
    import detector.metrics as metrics_mod

    if hasattr(metrics_mod, "start_http_server"):
        monkeypatch.setattr(metrics_mod, "start_http_server", fake_start)

    start_metrics_server(port=9999)

    assert captured.get("port") == 9999


# ---------- EC-1 ----------
def test_ec1_record_investigation_handles_empty_tool_calls() -> None:
    registry = CollectorRegistry()
    metrics = DetectorMetrics(registry=registry)
    result = _make_result(stop_reason="end_turn", tool_calls=[])

    # Should not raise.
    metrics.record_investigation(result, trigger_source="k8s_event")

    # No tool_calls samples should be present.
    samples: list[tuple[str, dict[str, str], float]] = []
    for collector in list(registry._names_to_collectors.values()):
        for metric in collector.collect():
            if metric.name == "detector_tool_calls":
                for sample in metric.samples:
                    if sample.name == "detector_tool_calls_total":
                        samples.append((sample.name, dict(sample.labels), sample.value))

    assert samples == []
