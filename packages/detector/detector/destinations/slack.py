from __future__ import annotations

from typing import Any, Protocol

from detector.agent.loop import InvestigationResult
from detector.prompts import render_prompt

_SLACK_REPORT_PROMPT = "slack_report"
_NO_TOOL_CALLS_PLACEHOLDER = "(no tool calls)"


class SlackPort(Protocol):
    async def send(self, message: str) -> None: ...


def _render_actions_taken(result: InvestigationResult) -> str:
    if not result.tool_calls:
        return _NO_TOOL_CALLS_PLACEHOLDER
    return "\n".join(f"- {call.name} {call.input!r}" for call in result.tool_calls)


def _render_links(grafana_url: str) -> str:
    return f"<{grafana_url}|Grafana dashboard>"


async def notify_investigation(
    result: InvestigationResult,
    slack: SlackPort,
    *,
    trigger: dict[str, Any],
    grafana_url: str,
) -> None:
    del trigger  # reserved for future per-alert formatting
    message = render_prompt(
        _SLACK_REPORT_PROMPT,
        rca=result.final_text,
        actions_taken=_render_actions_taken(result),
        links=_render_links(grafana_url),
    )
    await slack.send(message)
