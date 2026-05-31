from __future__ import annotations

from typing import Any, Protocol

from detector.agent.loop import InvestigationResult
from detector.prompts import render_prompt

_SLACK_REPORT_PROMPT = "slack_report"
_NO_TOOL_CALLS_PLACEHOLDER = "(도구 호출 없음)"

_NAMESPACE_DASHBOARD_UID: dict[str, str] = {
    "api": "devopsim-api",
    "detector": "devopsim-detector",
    "monitoring": "devopsim-prometheus-cardinality",
}
_DASHBOARD_TIME_RANGE = "from=now-1h&to=now"


class SlackPort(Protocol):
    async def send(self, message: str) -> None: ...


def _render_actions_taken(result: InvestigationResult) -> str:
    if not result.tool_calls:
        return _NO_TOOL_CALLS_PLACEHOLDER
    return "\n".join(f"- {call.name} {call.input!r}" for call in result.tool_calls)


def _dashboard_url(grafana_url: str, namespace: str | None) -> str:
    uid = _NAMESPACE_DASHBOARD_UID.get(namespace or "")
    base = grafana_url.rstrip("/")
    if uid is None:
        return base
    return f"{base}/d/{uid}/?{_DASHBOARD_TIME_RANGE}"


def _render_links(grafana_url: str, trigger: dict[str, Any]) -> str:
    namespace = trigger.get("namespace")
    url = _dashboard_url(grafana_url, namespace)
    label = f"Grafana - {namespace}" if namespace and namespace in _NAMESPACE_DASHBOARD_UID else "Grafana"
    return f"<{url}|{label}>"


async def notify_investigation(
    result: InvestigationResult,
    slack: SlackPort,
    *,
    trigger: dict[str, Any],
    grafana_url: str,
) -> None:
    message = render_prompt(
        _SLACK_REPORT_PROMPT,
        rca=result.final_text,
        actions_taken=_render_actions_taken(result),
        links=_render_links(grafana_url, trigger),
    )
    await slack.send(message)
