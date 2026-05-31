import json
import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from detector.adapters.loki import LokiAdapter
from detector.agent.tools import (
    LokiPort,
    make_loki_query_range_tool,
    make_loki_query_tool,
)


class FakeLoki:
    def __init__(
        self,
        query_response: str = '{"status":"success","data":{"resultType":"vector","result":[]}}',
        range_response: str = '{"status":"success","data":{"resultType":"streams","result":[]}}',
        raise_exc: Exception | None = None,
    ) -> None:
        self.calls: list[tuple] = []
        self._query_response = query_response
        self._range_response = range_response
        self._raise_exc = raise_exc

    async def query(self, query: str) -> str:
        self.calls.append(("query", query))
        if self._raise_exc is not None:
            raise self._raise_exc
        return self._query_response

    async def query_range(self, query: str, lookback: str, limit: int, direction: str) -> str:
        self.calls.append(("query_range", query, lookback, limit, direction))
        if self._raise_exc is not None:
            raise self._raise_exc
        return self._range_response


# ---------- Port behavior (AC-1 ~ AC-5, EC-1 ~ EC-3) ----------


async def test_loki_query_handler_calls_port_query_and_returns_response():
    """AC-1"""
    loki: LokiPort = FakeLoki(query_response='{"status":"success","data":{"result":[1]}}')
    tool = make_loki_query_tool(loki)
    out = await tool.run({"query": 'count_over_time({namespace="api"}[5m])'})
    assert out == '{"status":"success","data":{"result":[1]}}'
    assert loki.calls == [("query", 'count_over_time({namespace="api"}[5m])')]


async def test_loki_query_range_handler_calls_port_query_range_and_returns_response():
    """AC-2"""
    loki = FakeLoki(range_response='{"status":"success","data":{"result":[42]}}')
    tool = make_loki_query_range_tool(loki)
    out = await tool.run(
        {
            "query": '{namespace="api"} |~ "OOM|error"',
            "lookback": "1h",
            "limit": 500,
            "direction": "forward",
        }
    )
    assert out == '{"status":"success","data":{"result":[42]}}'
    assert loki.calls == [
        ("query_range", '{namespace="api"} |~ "OOM|error"', "1h", 500, "forward"),
    ]


async def test_loki_query_range_defaults_lookback_10m_limit_200_direction_backward():
    """AC-3"""
    loki = FakeLoki()
    tool = make_loki_query_range_tool(loki)
    await tool.run({"query": '{namespace="api"}'})
    assert loki.calls == [("query_range", '{namespace="api"}', "10m", 200, "backward")]


async def test_loki_query_tool_anthropic_schema_shape():
    """AC-4"""
    tool = make_loki_query_tool(FakeLoki())
    schema = tool.to_anthropic_schema()
    assert schema["name"] == "loki_query"
    assert schema["input_schema"]["required"] == ["query"]
    assert "query" in schema["input_schema"]["properties"]


async def test_loki_query_range_tool_anthropic_schema_shape():
    """AC-5"""
    tool = make_loki_query_range_tool(FakeLoki())
    schema = tool.to_anthropic_schema()
    assert schema["name"] == "loki_query_range"
    assert schema["input_schema"]["required"] == ["query"]
    props = schema["input_schema"]["properties"]
    assert "query" in props
    assert "lookback" in props
    assert "limit" in props
    assert "direction" in props


async def test_loki_query_missing_query_returns_validation_error_and_no_port_call():
    """EC-1"""
    loki = FakeLoki()
    tool = make_loki_query_tool(loki)
    out = await tool.run({})
    assert "Error: ValidationError" in out
    assert loki.calls == []


async def test_loki_port_exception_is_wrapped_in_error_string():
    """EC-2"""
    loki = FakeLoki(raise_exc=RuntimeError("boom"))
    tool = make_loki_query_tool(loki)
    out = await tool.run({"query": '{namespace="api"}'})
    assert out.startswith("Error: ")
    assert "RuntimeError" in out
    assert "boom" in out


async def test_loki_query_returns_error_response_body_verbatim():
    """EC-3"""
    err_body = '{"status":"error","errorType":"bad_data","error":"parse error at ..."}'
    loki = FakeLoki(query_response=err_body)
    tool = make_loki_query_tool(loki)
    out = await tool.run({"query": "invalid{{"})
    assert out == err_body


# ---------- Adapter behavior (AC-6 ~ AC-8, EC-4 ~ EC-5) ----------


async def test_loki_adapter_query_issues_get_with_urlencoded_query():
    """AC-6"""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            json={"status": "success", "data": {"resultType": "vector", "result": []}},
        )

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    adapter = LokiAdapter(base_url="http://loki:3100", client=client)

    out = await adapter.query('count_over_time({namespace="api"}[5m])')

    assert captured["method"] == "GET"
    parsed = urlparse(captured["url"])
    assert parsed.scheme == "http"
    assert parsed.netloc == "loki:3100"
    assert parsed.path == "/loki/api/v1/query"
    qs = parse_qs(parsed.query)
    assert qs["query"] == ['count_over_time({namespace="api"}[5m])']
    # stringified JSON 반환
    assert json.loads(out)["status"] == "success"


async def test_loki_adapter_query_range_sends_query_start_end_limit_direction():
    """AC-7"""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            json={"status": "success", "data": {"resultType": "streams", "result": []}},
        )

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    adapter = LokiAdapter(base_url="http://loki:3100", client=client)

    before_ns = time.time_ns()
    await adapter.query_range('{namespace="api"}', "10m", 200, "backward")
    after_ns = time.time_ns()

    assert captured["method"] == "GET"
    parsed = urlparse(captured["url"])
    assert parsed.path == "/loki/api/v1/query_range"
    qs = parse_qs(parsed.query)
    assert qs["query"] == ['{namespace="api"}']
    # start, end는 unix nanoseconds
    start = int(qs["start"][0])
    end = int(qs["end"][0])
    assert before_ns - 10**9 <= end <= after_ns + 10**9
    assert start == end - 600 * 10**9
    assert qs["limit"] == ["200"]
    assert qs["direction"] == ["backward"]


async def test_loki_adapter_query_range_lookback_10m_yields_600_billion_ns_span():
    """AC-8"""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            json={"status": "success", "data": {"resultType": "streams", "result": []}},
        )

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    adapter = LokiAdapter(base_url="http://loki:3100", client=client)

    await adapter.query_range('{namespace="api"}', "10m", 200, "backward")

    parsed = urlparse(captured["url"])
    qs = parse_qs(parsed.query)
    start = int(qs["start"][0])
    end = int(qs["end"][0])
    assert end - start == 600 * 10**9


async def test_loki_adapter_raises_on_http_5xx():
    """EC-4"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    adapter = LokiAdapter(base_url="http://loki:3100", client=client)

    with pytest.raises(httpx.HTTPStatusError):
        await adapter.query('{namespace="api"}')


async def test_loki_adapter_query_range_invalid_lookback_format_raises_value_error():
    """EC-5"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"status": "success", "data": {"resultType": "streams", "result": []}},
        )

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    adapter = LokiAdapter(base_url="http://loki:3100", client=client)

    with pytest.raises(ValueError):
        await adapter.query_range('{namespace="api"}', "abc", 200, "backward")
    with pytest.raises(ValueError):
        await adapter.query_range('{namespace="api"}', "10", 200, "backward")
