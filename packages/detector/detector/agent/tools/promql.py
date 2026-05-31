from typing import Protocol

from pydantic import BaseModel, Field

from .base import Tool


class PrometheusPort(Protocol):
    async def query(self, query: str) -> str: ...
    async def query_range(self, query: str, lookback: str, step: str) -> str: ...


class PromQLQueryInput(BaseModel):
    query: str = Field(description="PromQL instant query expression.")


class PromQLRangeInput(BaseModel):
    query: str = Field(description="PromQL range query expression.")
    lookback: str = Field(default="10m", description="Lookback window (e.g. 10m, 1h).")
    step: str = Field(default="30s", description="Step interval (e.g. 30s, 1m).")


def make_promql_query_tool(prom: PrometheusPort) -> Tool:
    async def handler(input: PromQLQueryInput) -> str:
        return await prom.query(input.query)

    return Tool(
        name="promql_query",
        description="Execute a PromQL instant query against Prometheus.",
        input_model=PromQLQueryInput,
        handler=handler,
    )


def make_promql_range_tool(prom: PrometheusPort) -> Tool:
    async def handler(input: PromQLRangeInput) -> str:
        return await prom.query_range(input.query, input.lookback, input.step)

    return Tool(
        name="promql_range",
        description="Execute a PromQL range query against Prometheus.",
        input_model=PromQLRangeInput,
        handler=handler,
    )
