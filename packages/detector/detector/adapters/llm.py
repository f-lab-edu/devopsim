from __future__ import annotations

import logging
from typing import Any

from anthropic import APIStatusError, AsyncAnthropic

from detector.agent.loop import LLMResponse

logger = logging.getLogger(__name__)


def _content_block_to_dict(block: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"type": block.type}
    if block.type == "text":
        base["text"] = block.text
    elif block.type == "tool_use":
        base["id"] = block.id
        base["name"] = block.name
        base["input"] = block.input
    return base


class AnthropicAdapter:
    def __init__(
        self,
        *,
        api_key: str,
        client: AsyncAnthropic | None = None,
    ) -> None:
        self._client = client if client is not None else AsyncAnthropic(api_key=api_key)

    async def create_message(
        self,
        *,
        model: str,
        system: list[dict],
        tools: list[dict],
        messages: list[dict],
        max_tokens: int,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
        try:
            response = await self._client.messages.create(**kwargs)
        except APIStatusError as e:
            logger.error("anthropic API error status=%s body=%s", e.status_code, getattr(e, "body", None))
            raise
        return LLMResponse(
            stop_reason=response.stop_reason or "",
            content=[_content_block_to_dict(b) for b in response.content],
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cache_read_input_tokens=response.usage.cache_read_input_tokens or 0,
        )
