from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from detector.agent.tools.base import Tool

MAX_STEPS = 10
MAX_TOTAL_INPUT_TOKENS = 50_000
DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 4096

# Anthropic content block types
_BLOCK_TYPE_TEXT = "text"
_BLOCK_TYPE_TOOL_USE = "tool_use"
_BLOCK_TYPE_TOOL_RESULT = "tool_result"

# stop_reason values
_STOP_TOOL_USE = "tool_use"
_STOP_MAX_STEPS = "max_steps_exceeded"
_STOP_BUDGET_EXCEEDED = "max_tokens_budget_exceeded"


@dataclass
class LLMResponse:
    stop_reason: str
    content: list[dict[str, Any]]
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int = 0


@dataclass
class ToolCallLog:
    name: str
    input: dict[str, Any]
    output: str


@dataclass
class InvestigationResult:
    final_text: str
    stop_reason: str
    tool_calls: list[ToolCallLog] = field(default_factory=list)
    steps: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0


class LLMPort(Protocol):
    async def create_message(
        self,
        *,
        model: str,
        system: list[dict],
        tools: list[dict],
        messages: list[dict],
        max_tokens: int,
    ) -> LLMResponse: ...


def _build_system_blocks(cluster_context: str) -> list[dict[str, Any]]:
    intro = (
        "You are an SRE assistant investigating production alerts. "
        "Use the provided tools to inspect the cluster and explain root causes. "
        "Stop as soon as you can give a concise actionable summary."
    )
    return [
        {"type": _BLOCK_TYPE_TEXT, "text": intro},
        {
            "type": _BLOCK_TYPE_TEXT,
            "text": f"Cluster context:\n{cluster_context}",
            "cache_control": {"type": "ephemeral"},
        },
    ]


def _build_initial_user_message(trigger: dict[str, Any], runbook_catalog: str) -> dict[str, Any]:
    text = f"Trigger:\n{trigger}\n\nRunbook catalog:\n{runbook_catalog}"
    return {"role": "user", "content": [{"type": _BLOCK_TYPE_TEXT, "text": text}]}


def _extract_text(content: list[dict[str, Any]]) -> str:
    parts = [b.get("text", "") for b in content if b.get("type") == _BLOCK_TYPE_TEXT]
    return "".join(parts)


def _find_tool_use(content: list[dict[str, Any]]) -> dict[str, Any] | None:
    for block in content:
        if block.get("type") == _BLOCK_TYPE_TOOL_USE:
            return block
    return None


def _build_tool_result_block(tool_use_id: str, output: str, is_error: bool) -> dict[str, Any]:
    block: dict[str, Any] = {
        "type": _BLOCK_TYPE_TOOL_RESULT,
        "tool_use_id": tool_use_id,
        "content": output,
    }
    if is_error:
        block["is_error"] = True
    return block


async def _run_tool_call(
    tool_use: dict[str, Any],
    tool_by_name: dict[str, Tool],
    tool_call_logs: list[ToolCallLog],
) -> dict[str, Any]:
    """Dispatch a single tool_use block; append a log on success; return the tool_result block."""
    tool_name = tool_use.get("name", "")
    tool_input = tool_use.get("input", {}) or {}
    tool_use_id = tool_use.get("id", "")

    tool = tool_by_name.get(tool_name)
    if tool is None:
        return _build_tool_result_block(tool_use_id, f"Error: unknown tool: {tool_name}", is_error=True)

    output = await tool.run(tool_input)
    tool_call_logs.append(ToolCallLog(name=tool_name, input=dict(tool_input), output=output))
    return _build_tool_result_block(tool_use_id, output, is_error=False)


async def investigate(
    *,
    trigger: dict[str, Any],
    tools: list[Tool],
    llm: LLMPort,
    runbook_catalog: str,
    cluster_context: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> InvestigationResult:
    if not tools:
        raise ValueError("tools must not be empty")

    tool_by_name = {t.name: t for t in tools}
    tool_schemas = [t.to_anthropic_schema() for t in tools]
    system_blocks = _build_system_blocks(cluster_context)

    messages: list[dict[str, Any]] = [_build_initial_user_message(trigger, runbook_catalog)]
    tool_call_logs: list[ToolCallLog] = []
    total_input = 0
    total_output = 0
    steps = 0
    final_text = ""
    stop_reason = ""

    while steps < MAX_STEPS:
        response = await llm.create_message(
            model=model,
            system=system_blocks,
            tools=tool_schemas,
            messages=messages,
            max_tokens=max_tokens,
        )
        steps += 1
        total_input += response.input_tokens
        total_output += response.output_tokens
        stop_reason = response.stop_reason

        if response.stop_reason != _STOP_TOOL_USE:
            final_text = _extract_text(response.content)
            break

        tool_use = _find_tool_use(response.content)
        if tool_use is None:
            final_text = _extract_text(response.content)
            break

        messages.append({"role": "assistant", "content": response.content})
        result_block = await _run_tool_call(tool_use, tool_by_name, tool_call_logs)
        messages.append({"role": "user", "content": [result_block]})

        if total_input > MAX_TOTAL_INPUT_TOKENS:
            stop_reason = _STOP_BUDGET_EXCEEDED
            final_text = ""
            break
    else:
        stop_reason = _STOP_MAX_STEPS
        final_text = ""

    return InvestigationResult(
        final_text=final_text,
        stop_reason=stop_reason,
        tool_calls=tool_call_logs,
        steps=steps,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
    )
