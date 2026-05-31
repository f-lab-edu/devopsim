import httpx
import pytest

from detector.adapters.slack import SlackAdapter
from detector.agent.loop import InvestigationResult, ToolCallLog
from detector.destinations.slack import SlackPort, notify_investigation


class FakeSlack:
    def __init__(self, raise_exc: Exception | None = None) -> None:
        self.sent_messages: list[str] = []
        self._raise_exc = raise_exc

    async def send(self, message: str) -> None:
        self.sent_messages.append(message)
        if self._raise_exc is not None:
            raise self._raise_exc


# ---------- notify_investigation behavior (AC-1 ~ AC-5) ----------


async def test_when_notify_investigation_is_called_the_system_shall_call_slack_port_send_exactly_once():
    """AC-1"""
    slack: SlackPort = FakeSlack()
    result = InvestigationResult(
        final_text="root cause: pod OOMKilled",
        stop_reason="end_turn",
        tool_calls=[],
    )

    await notify_investigation(
        result,
        slack,
        trigger={"alertname": "PodOOM"},
        grafana_url="https://grafana.example.com/d/abc",
    )

    assert len(slack.sent_messages) == 1


async def test_when_send_is_called_the_message_includes_result_final_text_substring():
    """AC-2"""
    slack = FakeSlack()
    result = InvestigationResult(
        final_text="UNIQUE_RCA_MARKER_xyz123 pod restarted",
        stop_reason="end_turn",
        tool_calls=[],
    )

    await notify_investigation(
        result,
        slack,
        trigger={"alertname": "PodOOM"},
        grafana_url="https://grafana.example.com/d/abc",
    )

    assert "UNIQUE_RCA_MARKER_xyz123 pod restarted" in slack.sent_messages[0]


async def test_when_tool_calls_has_items_actions_taken_renders_each_as_dash_name_input_dict_format():
    """AC-3"""
    slack = FakeSlack()
    tool_calls = [
        ToolCallLog(
            name="kubectl_get_pods",
            input={"namespace": "default"},
            output="pod1 Running",
        ),
        ToolCallLog(
            name="promql_query",
            input={"query": "up"},
            output="1",
        ),
    ]
    result = InvestigationResult(
        final_text="rca",
        stop_reason="end_turn",
        tool_calls=tool_calls,
    )

    await notify_investigation(
        result,
        slack,
        trigger={"alertname": "X"},
        grafana_url="https://grafana.example.com/d/abc",
    )

    message = slack.sent_messages[0]
    assert "kubectl_get_pods" in message
    assert repr({"namespace": "default"}) in message
    assert "promql_query" in message
    assert repr({"query": "up"}) in message


async def test_when_tool_calls_is_empty_actions_taken_is_filled_with_no_tool_calls_string():
    """AC-4"""
    slack = FakeSlack()
    result = InvestigationResult(
        final_text="rca",
        stop_reason="end_turn",
        tool_calls=[],
    )

    await notify_investigation(
        result,
        slack,
        trigger={"alertname": "X"},
        grafana_url="https://grafana.example.com/d/abc",
    )

    assert "(도구 호출 없음)" in slack.sent_messages[0]


async def test_when_grafana_url_is_passed_links_include_slack_mrkdwn_grafana_dashboard_link():
    """AC-5"""
    slack = FakeSlack()
    result = InvestigationResult(
        final_text="rca",
        stop_reason="end_turn",
        tool_calls=[],
    )
    grafana_url = "https://grafana.example.com/d/abc?var-ns=default"

    await notify_investigation(
        result,
        slack,
        trigger={"alertname": "X"},
        grafana_url=grafana_url,
    )

    # trigger에 namespace가 없으면 root URL + 단순 'Grafana' 라벨로 폴백
    assert f"<{grafana_url}|Grafana>" in slack.sent_messages[0]


# ---------- Adapter behavior (AC-6 ~ AC-7) ----------


async def test_when_slack_adapter_send_is_called_it_posts_webhook_url_with_text_json_payload():
    """AC-6"""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["body"] = request.content
        return httpx.Response(200, text="ok")

    webhook_url = "https://hooks.slack.com/services/T000/B000/XXXX"
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    adapter = SlackAdapter(webhook_url=webhook_url, client=client)

    await adapter.send("hello world")

    assert captured["method"] == "POST"
    assert captured["url"] == webhook_url
    import json as _json

    body = _json.loads(captured["body"])
    assert body == {"text": "hello world"}


async def test_when_slack_returns_http_5xx_adapter_send_raises_http_status_error():
    """AC-7"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    adapter = SlackAdapter(
        webhook_url="https://hooks.slack.com/services/T000/B000/XXXX",
        client=client,
    )

    with pytest.raises(httpx.HTTPStatusError):
        await adapter.send("hello")


# ---------- Error & Edge Cases (EC-1) ----------


async def test_when_slack_port_send_raises_notify_investigation_propagates_the_exception():
    """EC-1"""
    slack = FakeSlack(raise_exc=ValueError("boom"))
    result = InvestigationResult(
        final_text="rca",
        stop_reason="end_turn",
        tool_calls=[],
    )

    with pytest.raises(ValueError, match="boom"):
        await notify_investigation(
            result,
            slack,
            trigger={"alertname": "X"},
            grafana_url="https://grafana.example.com/d/abc",
        )
