import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from detector.adapters.alertmanager import AlertmanagerAdapter
from detector.agent.tools import (
    AlertmanagerPort,
    make_alertmanager_list_alerts_tool,
)


class FakeAlertmanager:
    def __init__(
        self,
        response: str = "[]",
        raise_exc: Exception | None = None,
    ) -> None:
        self.calls: list[tuple] = []
        self._response = response
        self._raise_exc = raise_exc

    async def list_alerts(self, matchers: list[str] | None, state: str) -> str:
        self.calls.append(("list_alerts", matchers, state))
        if self._raise_exc is not None:
            raise self._raise_exc
        return self._response


# ---------- Port behavior (AC-1 ~ AC-3, EC-1 ~ EC-2) ----------


async def test_alertmanager_list_alerts_handler_calls_port_with_matchers_and_state_and_returns_response():
    """AC-1"""
    am: AlertmanagerPort = FakeAlertmanager(response='[{"labels":{"alertname":"X"}}]')
    tool = make_alertmanager_list_alerts_tool(am)
    out = await tool.run({"matchers": ["severity=warning"], "state": "active"})
    assert out == '[{"labels":{"alertname":"X"}}]'
    assert am.calls == [("list_alerts", ["severity=warning"], "active")]


async def test_alertmanager_list_alerts_defaults_matchers_none_and_state_active():
    """AC-2"""
    am = FakeAlertmanager()
    tool = make_alertmanager_list_alerts_tool(am)
    await tool.run({})
    assert am.calls == [("list_alerts", None, "active")]


async def test_alertmanager_list_alerts_tool_anthropic_schema_shape():
    """AC-3"""
    tool = make_alertmanager_list_alerts_tool(FakeAlertmanager())
    schema = tool.to_anthropic_schema()
    assert schema["name"] == "alertmanager_list_alerts"
    assert schema["input_schema"]["required"] == []
    props = schema["input_schema"]["properties"]
    assert "matchers" in props
    assert "state" in props


async def test_alertmanager_list_alerts_invalid_state_returns_validation_error_and_no_port_call():
    """EC-1"""
    am = FakeAlertmanager()
    tool = make_alertmanager_list_alerts_tool(am)
    out = await tool.run({"state": "firing"})
    assert "Error: ValidationError" in out
    assert am.calls == []


async def test_alertmanager_port_exception_is_wrapped_in_error_string():
    """EC-2"""
    am = FakeAlertmanager(raise_exc=RuntimeError("boom"))
    tool = make_alertmanager_list_alerts_tool(am)
    out = await tool.run({})
    assert out.startswith("Error: ")
    assert "RuntimeError" in out
    assert "boom" in out


# ---------- Adapter behavior (AC-4 ~ AC-7, EC-3) ----------


async def test_alertmanager_adapter_list_alerts_default_state_active():
    """AC-4"""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    adapter = AlertmanagerAdapter(base_url="http://alertmanager:9093", client=client)

    out = await adapter.list_alerts(None, "active")

    assert captured["method"] == "GET"
    parsed = urlparse(captured["url"])
    assert parsed.scheme == "http"
    assert parsed.netloc == "alertmanager:9093"
    assert parsed.path == "/api/v2/alerts"
    qs = parse_qs(parsed.query)
    assert qs["active"] == ["true"]
    assert qs["silenced"] == ["false"]
    assert qs["inhibited"] == ["false"]
    # stringified JSON 반환
    assert json.loads(out) == []


async def test_alertmanager_adapter_list_alerts_includes_filter_param_twice_for_two_matchers():
    """AC-5"""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    adapter = AlertmanagerAdapter(base_url="http://alertmanager:9093", client=client)

    await adapter.list_alerts(["alertname=X", "severity=warning"], "active")

    parsed = urlparse(captured["url"])
    assert parsed.path == "/api/v2/alerts"
    qs = parse_qs(parsed.query)
    assert qs["filter"] == ["alertname=X", "severity=warning"]


async def test_alertmanager_adapter_list_alerts_state_silenced_flags():
    """AC-6"""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    adapter = AlertmanagerAdapter(base_url="http://alertmanager:9093", client=client)

    await adapter.list_alerts(None, "silenced")

    parsed = urlparse(captured["url"])
    qs = parse_qs(parsed.query)
    assert qs["active"] == ["false"]
    assert qs["silenced"] == ["true"]
    assert qs["inhibited"] == ["false"]


async def test_alertmanager_adapter_list_alerts_state_inhibited_flags():
    """AC-7"""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    adapter = AlertmanagerAdapter(base_url="http://alertmanager:9093", client=client)

    await adapter.list_alerts(None, "inhibited")

    parsed = urlparse(captured["url"])
    qs = parse_qs(parsed.query)
    assert qs["active"] == ["false"]
    assert qs["silenced"] == ["false"]
    assert qs["inhibited"] == ["true"]


async def test_alertmanager_adapter_raises_on_http_5xx():
    """EC-3"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    adapter = AlertmanagerAdapter(base_url="http://alertmanager:9093", client=client)

    with pytest.raises(httpx.HTTPStatusError):
        await adapter.list_alerts(None, "active")
