from typing import Protocol

from pydantic import BaseModel, Field

from .base import Tool


class LokiPort(Protocol):
    async def query(self, query: str) -> str: ...
    async def query_range(self, query: str, lookback: str, limit: int, direction: str) -> str: ...


class LokiQueryInput(BaseModel):
    query: str = Field(description="LogQL instant query expression.")


class LokiQueryRangeInput(BaseModel):
    query: str = Field(description="LogQL range query expression.")
    lookback: str = Field(default="10m", description="Lookback window (e.g. 10m, 1h).")
    limit: int = Field(default=200, description="Maximum number of entries to return.")
    direction: str = Field(default="backward", description="Sort direction: forward or backward.")


def make_loki_query_tool(loki: LokiPort) -> Tool:
    async def handler(input: LokiQueryInput) -> str:
        return await loki.query(input.query)

    return Tool(
        name="loki_query",
        description="Execute a LogQL instant query against Loki.",
        input_model=LokiQueryInput,
        handler=handler,
    )


def make_loki_query_range_tool(loki: LokiPort) -> Tool:
    async def handler(input: LokiQueryRangeInput) -> str:
        return await loki.query_range(input.query, input.lookback, input.limit, input.direction)

    return Tool(
        name="loki_query_range",
        description="Execute a LogQL range query against Loki.",
        input_model=LokiQueryRangeInput,
        handler=handler,
    )
