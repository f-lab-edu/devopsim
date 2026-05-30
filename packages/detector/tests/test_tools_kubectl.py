import pytest

from detector.agent.tools import (
    make_kubectl_describe_tool,
    make_kubectl_events_tool,
    make_kubectl_get_tool,
    make_kubectl_logs_tool,
)


class FakeK8s:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def get(self, kind, namespace, name):
        self.calls.append(("get", kind, namespace, name))
        return f"yaml-{kind}-{namespace}-{name}"

    async def describe(self, kind, namespace, name):
        self.calls.append(("describe", kind, namespace, name))
        return f"desc-{kind}-{namespace}-{name}"

    async def logs(self, namespace, pod, container, tail_lines, previous):
        self.calls.append(("logs", namespace, pod, container, tail_lines, previous))
        return "log-content"

    async def list_events(self, namespace, field_selector):
        self.calls.append(("events", namespace, field_selector))
        return "events"


async def test_get_tool_calls_port():
    k8s = FakeK8s()
    tool = make_kubectl_get_tool(k8s)
    out = await tool.run({"kind": "Pod", "namespace": "api", "name": "p1"})
    assert out == "yaml-Pod-api-p1"
    assert k8s.calls == [("get", "Pod", "api", "p1")]


async def test_get_tool_name_optional():
    k8s = FakeK8s()
    tool = make_kubectl_get_tool(k8s)
    await tool.run({"kind": "Pod", "namespace": "api"})
    assert k8s.calls == [("get", "Pod", "api", None)]


async def test_get_tool_validation_error():
    k8s = FakeK8s()
    tool = make_kubectl_get_tool(k8s)
    out = await tool.run({"kind": "Pod"})
    assert "Error: ValidationError" in out
    assert k8s.calls == []


async def test_describe_tool_calls_port():
    k8s = FakeK8s()
    tool = make_kubectl_describe_tool(k8s)
    await tool.run({"kind": "Pod", "namespace": "api", "name": "p1"})
    assert k8s.calls == [("describe", "Pod", "api", "p1")]


async def test_logs_tool_defaults():
    k8s = FakeK8s()
    tool = make_kubectl_logs_tool(k8s)
    await tool.run({"namespace": "api", "pod": "p1"})
    assert k8s.calls == [("logs", "api", "p1", None, 200, False)]


async def test_logs_tool_previous():
    k8s = FakeK8s()
    tool = make_kubectl_logs_tool(k8s)
    await tool.run({"namespace": "api", "pod": "p1", "previous": True, "tail_lines": 50})
    assert k8s.calls == [("logs", "api", "p1", None, 50, True)]


async def test_events_tool_with_filter():
    k8s = FakeK8s()
    tool = make_kubectl_events_tool(k8s)
    await tool.run({"namespace": "api", "field_selector": "reason=BackOff"})
    assert k8s.calls == [("events", "api", "reason=BackOff")]


async def test_anthropic_schema_shape():
    tool = make_kubectl_get_tool(FakeK8s())
    schema = tool.to_anthropic_schema()
    assert schema["name"] == "kubectl_get"
    assert "kind" in schema["input_schema"]["properties"]
    assert set(schema["input_schema"]["required"]) == {"kind", "namespace"}
