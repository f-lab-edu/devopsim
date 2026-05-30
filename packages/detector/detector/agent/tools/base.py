import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

ToolHandler = Callable[[Any], Awaitable[str]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: ToolHandler

    async def run(self, raw_input: dict[str, Any]) -> str:
        try:
            parsed = self.input_model.model_validate(raw_input)
            return await self.handler(parsed)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"

    def to_anthropic_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_model.model_json_schema(),
        }
