from __future__ import annotations

from typing import TYPE_CHECKING, Any

from prometheus_client import REGISTRY, CollectorRegistry, Counter, Histogram, start_http_server

if TYPE_CHECKING:
    from detector.agent.loop import InvestigationResult

# Token type labels
_TOKEN_TYPE_INPUT = "input"
_TOKEN_TYPE_OUTPUT = "output"
_TOKEN_TYPE_CACHE_READ = "cache_read"

# Tool call status labels
_STATUS_OK = "ok"
_STATUS_ERROR = "error"

# Tool output prefix marking an error (mirrors agent.loop tool_result error convention)
_TOOL_ERROR_PREFIX = "Error: "

# InvestigationResult attribute name fallbacks. The agent currently exposes
# ``total_input_tokens`` / ``total_output_tokens``; older or alternate shapes
# may expose ``input_tokens`` / ``output_tokens``. We accept either.
_INPUT_TOKEN_ATTRS = ("input_tokens", "total_input_tokens")
_OUTPUT_TOKEN_ATTRS = ("output_tokens", "total_output_tokens")
_DURATION_ATTR = "duration_seconds"
_CACHE_READ_ATTR = "cache_read_input_tokens"


def _first_present_int(result: Any, attrs: tuple[str, ...]) -> int:
    """Return ``int(result.<attr>)`` for the first attr whose value is not None, else 0."""
    for attr in attrs:
        value = getattr(result, attr, None)
        if value is not None:
            return int(value)
    return 0


def _safe_float(result: Any, attr: str) -> float:
    return float(getattr(result, attr, 0.0) or 0.0)


def _safe_int(result: Any, attr: str) -> int:
    return int(getattr(result, attr, 0) or 0)


def _tool_call_status(output: str) -> str:
    return _STATUS_ERROR if output.startswith(_TOOL_ERROR_PREFIX) else _STATUS_OK


class DetectorMetrics:
    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        self.registry = registry if registry is not None else REGISTRY

        self.investigations = Counter(
            "detector_investigations",
            "Total investigations run by the detector agent.",
            labelnames=("trigger", "result"),
            registry=self.registry,
        )
        self.tool_calls = Counter(
            "detector_tool_calls",
            "Total tool calls executed during investigations.",
            labelnames=("tool", "status"),
            registry=self.registry,
        )
        self.duration = Histogram(
            "detector_investigation_duration_seconds",
            "Duration of investigations in seconds.",
            registry=self.registry,
        )
        self.tokens_used = Counter(
            "detector_tokens_used",
            "Tokens consumed by the detector agent.",
            labelnames=("type",),
            registry=self.registry,
        )

    def record_investigation(
        self,
        result: InvestigationResult,
        *,
        trigger_source: str,
    ) -> None:
        self.investigations.labels(trigger=trigger_source, result=result.stop_reason).inc()
        self.duration.observe(_safe_float(result, _DURATION_ATTR))
        self._record_tokens(result)
        self._record_tool_calls(result)

    def _record_tokens(self, result: InvestigationResult) -> None:
        input_tokens = _first_present_int(result, _INPUT_TOKEN_ATTRS)
        output_tokens = _first_present_int(result, _OUTPUT_TOKEN_ATTRS)
        cache_read_tokens = _safe_int(result, _CACHE_READ_ATTR)

        self.tokens_used.labels(type=_TOKEN_TYPE_INPUT).inc(input_tokens)
        self.tokens_used.labels(type=_TOKEN_TYPE_OUTPUT).inc(output_tokens)
        self.tokens_used.labels(type=_TOKEN_TYPE_CACHE_READ).inc(cache_read_tokens)

    def _record_tool_calls(self, result: InvestigationResult) -> None:
        for call in result.tool_calls:
            self.tool_calls.labels(tool=call.name, status=_tool_call_status(call.output)).inc()


def start_metrics_server(port: int) -> None:
    start_http_server(port)
