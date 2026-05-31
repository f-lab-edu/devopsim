"""Tests for detector.agent.loop (Red phase).

Covers AC-1 ~ AC-10 + EC-1 ~ EC-2 from .plan/specs/agent-loop.md.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from anthropic import AsyncAnthropic
from pydantic import BaseModel

from detector.adapters.llm import AnthropicAdapter
from detector.agent.loop import (
    MAX_STEPS,
    MAX_TOTAL_INPUT_TOKENS,
    InvestigationResult,
    LLMPort,
    LLMResponse,
    ToolCallLog,
    investigate,
)
from detector.agent.tools.base import Tool

# ---------- Test helpers ----------


class FakeLLM:
    """In-memory LLMPort double. Returns queued LLMResponse values in order."""

    def __init__(
        self,
        responses: list[LLMResponse] | None = None,
        raise_exc: Exception | None = None,
    ) -> None:
        self._responses: list[LLMResponse] = list(responses or [])
        self._raise_exc = raise_exc
        self.calls: list[dict[str, Any]] = []

    async def create_message(
        self,
        *,
        model: str,
        system: list[dict],
        tools: list[dict],
        messages: list[dict],
        max_tokens: int,
    ) -> LLMResponse:
        self.calls.append(
            {
                "model": model,
                "system": system,
                "tools": tools,
                "messages": messages,
                "max_tokens": max_tokens,
            }
        )
        if self._raise_exc is not None:
            raise self._raise_exc
        if not self._responses:
            # Fallback: keep yielding the last shape (helpful for infinite loops).
            raise AssertionError("FakeLLM exhausted: no more queued responses")
        return self._responses.pop(0)


class EchoInput(BaseModel):
    """Tiny input model for FakeTool."""

    value: str = ""


def make_fake_tool(name: str = "fake_tool", output: str = "fake-output") -> tuple[Tool, list[dict]]:
    """Build a Tool whose handler records every call and returns ``output``."""

    calls: list[dict] = []

    async def handler(parsed: EchoInput) -> str:
        calls.append({"value": parsed.value})
        return output

    tool = Tool(
        name=name,
        description=f"fake tool {name}",
        input_model=EchoInput,
        handler=handler,
    )
    return tool, calls


def text_response(text: str, *, input_tokens: int = 10, output_tokens: int = 5) -> LLMResponse:
    return LLMResponse(
        stop_reason="end_turn",
        content=[{"type": "text", "text": text}],
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_input_tokens=0,
    )


def tool_use_response(
    tool_name: str,
    tool_input: dict,
    *,
    tool_use_id: str = "toolu_1",
    input_tokens: int = 10,
    output_tokens: int = 5,
) -> LLMResponse:
    return LLMResponse(
        stop_reason="tool_use",
        content=[
            {
                "type": "tool_use",
                "id": tool_use_id,
                "name": tool_name,
                "input": tool_input,
            }
        ],
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_input_tokens=0,
    )


# ---------- AC-1 ~ AC-9: investigate() behavior (FakeLLM) ----------


async def test_ac1_end_turn_text_response_is_returned_as_final_text():
    """AC-1: 첫 응답이 end_turn + text이면 final_text에 그 text를 담은 결과 반환."""
    tool, _ = make_fake_tool()
    llm = FakeLLM(responses=[text_response("all good — no action")])

    result = await investigate(
        trigger={"alert": "HighErrorRate", "severity": "warning"},
        tools=[tool],
        llm=llm,
        runbook_catalog="- foo.md",
        cluster_context="prod cluster",
    )

    assert isinstance(result, InvestigationResult)
    assert result.final_text == "all good — no action"
    assert result.stop_reason == "end_turn"
    assert result.tool_calls == []
    assert result.steps >= 1


async def test_ac2_tool_use_then_end_turn_calls_tool_and_appends_tool_result_then_returns_final_text():
    """AC-2: tool_use → tool.run(**input) 호출 → tool_result append → 재호출 후 end_turn."""
    tool, tool_calls = make_fake_tool(name="kubectl_get_pods", output="pod-output-XYZ")
    llm = FakeLLM(
        responses=[
            tool_use_response(
                "kubectl_get_pods",
                {"value": "default"},
                tool_use_id="toolu_abc",
            ),
            text_response("done"),
        ]
    )

    result = await investigate(
        trigger={"alert": "PodPending"},
        tools=[tool],
        llm=llm,
        runbook_catalog="catalog",
        cluster_context="ctx",
    )

    # Tool was actually called with parsed input.
    assert tool_calls == [{"value": "default"}]

    # Two LLM calls: initial + after tool_result.
    assert len(llm.calls) == 2

    # Second call must include the tool_result block in the appended messages.
    second_messages = llm.calls[1]["messages"]
    flat = repr(second_messages)
    assert "tool_result" in flat
    assert "toolu_abc" in flat
    assert "pod-output-XYZ" in flat

    # final_text comes from the second (end_turn) response.
    assert result.final_text == "done"
    assert result.stop_reason == "end_turn"


async def test_ac3_completed_tool_execution_appends_toolcalllog_with_name_input_output():
    """AC-3: tool 실행 완료 → result.tool_calls에 ToolCallLog(name, input, output)."""
    tool, _ = make_fake_tool(name="my_tool", output="result-42")
    llm = FakeLLM(
        responses=[
            tool_use_response("my_tool", {"value": "v1"}),
            text_response("ok"),
        ]
    )

    result = await investigate(
        trigger={"alert": "X"},
        tools=[tool],
        llm=llm,
        runbook_catalog="cat",
        cluster_context="ctx",
    )

    assert len(result.tool_calls) == 1
    log = result.tool_calls[0]
    assert isinstance(log, ToolCallLog)
    assert log.name == "my_tool"
    assert log.input == {"value": "v1"}
    assert log.output == "result-42"


async def test_ac4_unknown_tool_name_emits_error_tool_result_and_continues_loop():
    """AC-4: 알 수 없는 tool name 요청 → 'Error: unknown tool: <name>'를 tool_result로 전송 후 loop 계속."""
    tool, tool_calls = make_fake_tool(name="known_tool")
    llm = FakeLLM(
        responses=[
            tool_use_response("ghost_tool", {"value": "x"}, tool_use_id="toolu_unknown"),
            text_response("recovered"),
        ]
    )

    result = await investigate(
        trigger={"alert": "X"},
        tools=[tool],
        llm=llm,
        runbook_catalog="cat",
        cluster_context="ctx",
    )

    # Real tool was never invoked.
    assert tool_calls == []

    # Loop continued — we have a second LLM call.
    assert len(llm.calls) == 2

    # tool_result with the error string was sent.
    second_messages = llm.calls[1]["messages"]
    flat = repr(second_messages)
    assert "tool_result" in flat
    assert "Error: unknown tool: ghost_tool" in flat

    # Final returned text comes from the second response.
    assert result.final_text == "recovered"
    assert result.stop_reason == "end_turn"


async def test_ac5_loop_exits_with_max_steps_exceeded_after_max_steps_iterations():
    """AC-5: tool_use loop이 MAX_STEPS 회 도달 → stop_reason='max_steps_exceeded'."""
    tool, _ = make_fake_tool(name="loopy", output="x")
    # Queue MAX_STEPS + 5 tool_use responses — loop must stop before exhausting them.
    responses = [
        tool_use_response("loopy", {"value": "i"}, tool_use_id=f"toolu_{i}", input_tokens=1)
        for i in range(MAX_STEPS + 5)
    ]
    llm = FakeLLM(responses=responses)

    result = await investigate(
        trigger={"alert": "Loop"},
        tools=[tool],
        llm=llm,
        runbook_catalog="cat",
        cluster_context="ctx",
    )

    assert result.stop_reason == "max_steps_exceeded"
    assert result.steps == MAX_STEPS
    assert len(llm.calls) == MAX_STEPS


async def test_ac6_cumulative_input_tokens_over_budget_returns_max_tokens_budget_exceeded():
    """AC-6: 누적 input_tokens > MAX_TOTAL_INPUT_TOKENS → 'max_tokens_budget_exceeded'."""
    tool, _ = make_fake_tool(name="big", output="ok")
    # Two responses, each input_tokens > MAX_TOTAL_INPUT_TOKENS/2 → 누적이 MAX 초과.
    huge = MAX_TOTAL_INPUT_TOKENS // 2 + 1
    llm = FakeLLM(
        responses=[
            tool_use_response("big", {"value": "a"}, input_tokens=huge),
            tool_use_response("big", {"value": "b"}, input_tokens=huge),
            # Guard against accidental further iterations.
            text_response("should not reach", input_tokens=1),
        ]
    )

    result = await investigate(
        trigger={"alert": "Big"},
        tools=[tool],
        llm=llm,
        runbook_catalog="cat",
        cluster_context="ctx",
    )

    assert result.stop_reason == "max_tokens_budget_exceeded"
    assert result.total_input_tokens >= MAX_TOTAL_INPUT_TOKENS


async def test_ac7_refusal_or_max_tokens_stop_reason_terminates_immediately_and_is_preserved():
    """AC-7: stop_reason='refusal' / 'max_tokens' → 즉시 종료 + stop_reason 보존."""
    tool, _ = make_fake_tool()

    # refusal
    refusal_resp = LLMResponse(
        stop_reason="refusal",
        content=[{"type": "text", "text": "I cannot help with that"}],
        input_tokens=5,
        output_tokens=3,
        cache_read_input_tokens=0,
    )
    llm_r = FakeLLM(responses=[refusal_resp])
    res_r = await investigate(
        trigger={"alert": "X"},
        tools=[tool],
        llm=llm_r,
        runbook_catalog="cat",
        cluster_context="ctx",
    )
    assert res_r.stop_reason == "refusal"
    assert len(llm_r.calls) == 1

    # max_tokens
    max_resp = LLMResponse(
        stop_reason="max_tokens",
        content=[{"type": "text", "text": "truncated..."}],
        input_tokens=5,
        output_tokens=4096,
        cache_read_input_tokens=0,
    )
    llm_m = FakeLLM(responses=[max_resp])
    res_m = await investigate(
        trigger={"alert": "X"},
        tools=[tool],
        llm=llm_m,
        runbook_catalog="cat",
        cluster_context="ctx",
    )
    assert res_m.stop_reason == "max_tokens"
    assert len(llm_m.calls) == 1


async def test_ac8_system_blocks_last_item_has_cache_control_ephemeral_and_includes_cluster_context():
    """AC-8: system blocks 마지막에 cache_control ephemeral + cluster_context 포함."""
    tool, _ = make_fake_tool()
    llm = FakeLLM(responses=[text_response("ok")])

    await investigate(
        trigger={"alert": "X"},
        tools=[tool],
        llm=llm,
        runbook_catalog="cat",
        cluster_context="CLUSTER-CTX-MARKER-XYZ",
    )

    assert len(llm.calls) == 1
    system_blocks = llm.calls[0]["system"]
    assert isinstance(system_blocks, list)
    assert len(system_blocks) >= 1

    # Last block must carry cache_control: ephemeral.
    last = system_blocks[-1]
    assert last.get("cache_control") == {"type": "ephemeral"}

    # cluster_context value must appear somewhere in the system blocks.
    flat = "".join(str(b.get("text", "")) for b in system_blocks)
    assert "CLUSTER-CTX-MARKER-XYZ" in flat


async def test_ac9_first_user_message_contains_trigger_summary_and_runbook_catalog():
    """AC-9: messages 첫 항목이 user 메시지 + trigger 정보 + runbook_catalog 포함."""
    tool, _ = make_fake_tool()
    llm = FakeLLM(responses=[text_response("ok")])

    trigger = {"alert": "TRIGGER-ALERT-MARKER", "severity": "critical"}
    runbook_catalog = "RUNBOOK-CATALOG-MARKER-LINES"

    await investigate(
        trigger=trigger,
        tools=[tool],
        llm=llm,
        runbook_catalog=runbook_catalog,
        cluster_context="ctx",
    )

    msgs = llm.calls[0]["messages"]
    assert len(msgs) >= 1
    first = msgs[0]
    assert first["role"] == "user"

    flat = repr(first["content"])
    assert "TRIGGER-ALERT-MARKER" in flat
    assert "RUNBOOK-CATALOG-MARKER-LINES" in flat


# ---------- AC-10: AnthropicAdapter boundary (httpx.MockTransport) ----------


async def test_ac10_anthropic_adapter_create_message_posts_to_v1_messages_and_returns_llmresponse():
    """AC-10: AnthropicAdapter.create_message → POST /v1/messages, 응답을 LLMResponse로 변환."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "id": "msg_01",
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-4-6",
                "stop_reason": "end_turn",
                "content": [
                    {"type": "text", "text": "hello from anthropic"},
                ],
                "usage": {
                    "input_tokens": 123,
                    "output_tokens": 45,
                    "cache_read_input_tokens": 7,
                },
            },
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    sdk_client = AsyncAnthropic(api_key="test-key", http_client=http_client)
    adapter = AnthropicAdapter(api_key="test-key", client=sdk_client)

    resp = await adapter.create_message(
        model="claude-sonnet-4-6",
        system=[{"type": "text", "text": "you are an SRE"}],
        tools=[],
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=1024,
    )

    assert captured["method"] == "POST"
    assert captured["url"].endswith("/v1/messages")

    assert isinstance(resp, LLMResponse)
    assert resp.stop_reason == "end_turn"
    assert resp.content == [{"type": "text", "text": "hello from anthropic"}]
    assert resp.input_tokens == 123
    assert resp.output_tokens == 45
    assert resp.cache_read_input_tokens == 7


# ---------- EC-1 ~ EC-2 ----------


async def test_ec1_empty_tools_list_raises_value_error():
    """EC-1: tools=[] → ValueError."""
    llm = FakeLLM(responses=[text_response("nope")])
    with pytest.raises(ValueError):
        await investigate(
            trigger={"alert": "X"},
            tools=[],
            llm=llm,
            runbook_catalog="cat",
            cluster_context="ctx",
        )


async def test_ec2_llm_port_exception_propagates_without_result():
    """EC-2: LLMPort 예외 → InvestigationResult 생성하지 않고 그대로 전파."""
    tool, _ = make_fake_tool()
    boom = RuntimeError("anthropic-down")
    llm = FakeLLM(raise_exc=boom)

    with pytest.raises(RuntimeError) as exc_info:
        await investigate(
            trigger={"alert": "X"},
            tools=[tool],
            llm=llm,
            runbook_catalog="cat",
            cluster_context="ctx",
        )
    assert exc_info.value is boom
