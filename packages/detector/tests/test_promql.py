import json
import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from detector.adapters.prometheus import PrometheusAdapter

from detector.agent.tools import (
    PrometheusPort,
    make_promql_query_tool,
    make_promql_range_tool,
)


class FakePrometheus:
    def __init__(
        self,
        query_response: str = '{"status":"success","data":{"resultType":"vector","result":[]}}',
        range_response: str = '{"status":"success","data":{"resultType":"matrix","result":[]}}',
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

    async def query_range(self, query: str, lookback: str, step: str) -> str:
        self.calls.append(("query_range", query, lookback, step))
        if self._raise_exc is not None:
            raise self._raise_exc
        return self._range_response


# ---------- Port behavior (AC-1 ~ AC-5, EC-1 ~ EC-3) ----------


async def test_promql_query_handler_calls_port_query_and_returns_response():
    """AC-1"""
    prom: PrometheusPort = FakePrometheus(query_response='{"status":"success","data":{"result":[1]}}')
    tool = make_promql_query_tool(prom)
    out = await tool.run({"query": 'up{job="api"}'})
    assert out == '{"status":"success","data":{"result":[1]}}'
    assert prom.calls == [("query", 'up{job="api"}')]


async def test_promql_range_handler_calls_port_query_range_and_returns_response():
    """AC-2"""
    prom = FakePrometheus(range_response='{"status":"success","data":{"result":[42]}}')
    tool = make_promql_range_tool(prom)
    out = await tool.run({"query": "rate(http_requests_total[1m])", "lookback": "1h", "step": "1m"})
    assert out == '{"status":"success","data":{"result":[42]}}'
    assert prom.calls == [("query_range", "rate(http_requests_total[1m])", "1h", "1m")]


async def test_promql_range_defaults_lookback_10m_step_30s():
    """AC-3"""
    prom = FakePrometheus()
    tool = make_promql_range_tool(prom)
    await tool.run({"query": "up"})
    assert prom.calls == [("query_range", "up", "10m", "30s")]


async def test_promql_query_tool_anthropic_schema_shape():
    """AC-4"""
    tool = make_promql_query_tool(FakePrometheus())
    schema = tool.to_anthropic_schema()
    assert schema["name"] == "promql_query"
    assert schema["input_schema"]["required"] == ["query"]
    assert "query" in schema["input_schema"]["properties"]


async def test_promql_range_tool_anthropic_schema_shape():
    """AC-5"""
    tool = make_promql_range_tool(FakePrometheus())
    schema = tool.to_anthropic_schema()
    assert schema["name"] == "promql_range"
    assert schema["input_schema"]["required"] == ["query"]
    props = schema["input_schema"]["properties"]
    assert "query" in props
    assert "lookback" in props
    assert "step" in props


async def test_promql_query_missing_query_returns_validation_error_and_no_port_call():
    """EC-1"""
    prom = FakePrometheus()
    tool = make_promql_query_tool(prom)
    out = await tool.run({})
    assert "Error: ValidationError" in out
    assert prom.calls == []


async def test_promql_port_exception_is_wrapped_in_error_string():
    """EC-2"""
    prom = FakePrometheus(raise_exc=RuntimeError("boom"))
    tool = make_promql_query_tool(prom)
    out = await tool.run({"query": "up"})
    assert out.startswith("Error: ")
    assert "RuntimeError" in out
    assert "boom" in out


async def test_promql_query_returns_error_response_body_verbatim():
    """EC-3"""
    err_body = '{"status":"error","errorType":"bad_data","error":"parse error at ..."}'
    prom = FakePrometheus(query_response=err_body)
    tool = make_promql_query_tool(prom)
    out = await tool.run({"query": "invalid{{"})
    assert out == err_body


# ---------- Adapter behavior (AC-6 ~ AC-8, EC-4 ~ EC-5) ----------


async def test_prometheus_adapter_query_issues_get_with_urlencoded_query():
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
    adapter = PrometheusAdapter(base_url="http://prom:9090", client=client)

    out = await adapter.query('up{job="api"}')

    assert captured["method"] == "GET"
    parsed = urlparse(captured["url"])
    assert parsed.scheme == "http"
    assert parsed.netloc == "prom:9090"
    assert parsed.path == "/api/v1/query"
    qs = parse_qs(parsed.query)
    assert qs["query"] == ['up{job="api"}']
    # stringified JSON 반환
    assert json.loads(out)["status"] == "success"


async def test_prometheus_adapter_query_range_sends_query_start_end_step():
    """AC-7"""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            json={"status": "success", "data": {"resultType": "matrix", "result": []}},
        )

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    adapter = PrometheusAdapter(base_url="http://prom:9090", client=client)

    before = int(time.time())
    await adapter.query_range("rate(http_requests_total[1m])", "10m", "30s")
    after = int(time.time())

    assert captured["method"] == "GET"
    parsed = urlparse(captured["url"])
    assert parsed.path == "/api/v1/query_range"
    qs = parse_qs(parsed.query)
    assert qs["query"] == ["rate(http_requests_total[1m])"]
    # start, end는 unix epoch seconds
    start = int(qs["start"][0])
    end = int(qs["end"][0])
    assert before - 1 <= end <= after + 1
    assert start == end - 600
    # step은 seconds 정수
    assert qs["step"] == ["30"]


async def test_prometheus_adapter_query_range_lookback_10m_yields_600s_span():
    """AC-8"""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            json={"status": "success", "data": {"resultType": "matrix", "result": []}},
        )

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    adapter = PrometheusAdapter(base_url="http://prom:9090", client=client)

    await adapter.query_range("up", "10m", "30s")

    parsed = urlparse(captured["url"])
    qs = parse_qs(parsed.query)
    start = int(qs["start"][0])
    end = int(qs["end"][0])
    assert end - start == 600


async def test_prometheus_adapter_raises_on_http_5xx():
    """EC-4"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    adapter = PrometheusAdapter(base_url="http://prom:9090", client=client)

    with pytest.raises(httpx.HTTPStatusError):
        await adapter.query("up")


async def test_prometheus_adapter_query_range_invalid_lookback_format_raises_value_error():
    """EC-5"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"status": "success", "data": {"resultType": "matrix", "result": []}},
        )

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    adapter = PrometheusAdapter(base_url="http://prom:9090", client=client)

    with pytest.raises(ValueError):
        await adapter.query_range("up", "abc", "30s")
    with pytest.raises(ValueError):
        await adapter.query_range("up", "10", "30s")
