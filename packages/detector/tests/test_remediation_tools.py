import asyncio

import pytest

from detector.adapters.k8s import K8sAdapter
from detector.agent.tools import (
    make_delete_pod_tool,
    make_restart_deployment_tool,
    make_scale_deployment_tool,
)


class FakeK8s:
    """Fake KubernetesPort implementation — extends existing read methods with
    the 3 new write methods (restart_deployment / scale_deployment / delete_pod)."""

    def __init__(self, *, raise_exc: Exception | None = None) -> None:
        self.calls: list[tuple] = []
        self._raise_exc = raise_exc

    # existing read methods (kept for protocol completeness, not used here)
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

    # new write methods (spec §3 In Scope)
    async def restart_deployment(self, namespace, name, *, dry_run):
        self.calls.append(("restart_deployment", namespace, name, dry_run))
        if self._raise_exc:
            raise self._raise_exc
        return f"restarted-{namespace}-{name}-dry={dry_run}"

    async def scale_deployment(self, namespace, name, replicas, *, dry_run):
        self.calls.append(("scale_deployment", namespace, name, replicas, dry_run))
        if self._raise_exc:
            raise self._raise_exc
        return f"scaled-{namespace}-{name}-{replicas}-dry={dry_run}"

    async def delete_pod(self, namespace, name, *, dry_run):
        self.calls.append(("delete_pod", namespace, name, dry_run))
        if self._raise_exc:
            raise self._raise_exc
        return f"deleted-{namespace}-{name}-dry={dry_run}"


# ---------------------------------------------------------------------------
# AC-1 / AC-2 / AC-3 — happy-path: factory → port method called + return passthrough
# ---------------------------------------------------------------------------


async def test_restart_deployment_tool_calls_port():
    """AC-1: restart_deployment factory dispatches to k8s.restart_deployment and returns its result."""
    k8s = FakeK8s()
    tool = make_restart_deployment_tool(k8s, allowed_namespaces=("api",), dry_run=False)
    out = await tool.run({"namespace": "api", "name": "api"})
    assert out == "restarted-api-api-dry=False"
    assert k8s.calls == [("restart_deployment", "api", "api", False)]


async def test_scale_deployment_tool_calls_port():
    """AC-2: scale_deployment factory dispatches to k8s.scale_deployment and returns its result."""
    k8s = FakeK8s()
    tool = make_scale_deployment_tool(k8s, allowed_namespaces=("api",), dry_run=False)
    out = await tool.run({"namespace": "api", "name": "api", "replicas": 3})
    assert out == "scaled-api-api-3-dry=False"
    assert k8s.calls == [("scale_deployment", "api", "api", 3, False)]


async def test_delete_pod_tool_calls_port():
    """AC-3: delete_pod factory dispatches to k8s.delete_pod and returns its result."""
    k8s = FakeK8s()
    tool = make_delete_pod_tool(k8s, allowed_namespaces=("api",), dry_run=False)
    out = await tool.run({"namespace": "api", "name": "api-xxx"})
    assert out == "deleted-api-api-xxx-dry=False"
    assert k8s.calls == [("delete_pod", "api", "api-xxx", False)]


# ---------------------------------------------------------------------------
# AC-4 — namespace whitelist enforcement (parametrize across 3 factories)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("factory", "raw_input"),
    [
        (make_restart_deployment_tool, {"namespace": "kube-system", "name": "x"}),
        (
            make_scale_deployment_tool,
            {"namespace": "kube-system", "name": "x", "replicas": 2},
        ),
        (make_delete_pod_tool, {"namespace": "kube-system", "name": "x"}),
    ],
)
async def test_namespace_not_in_whitelist_returns_error(factory, raw_input):
    """AC-4: input.namespace outside allowed_namespaces returns formatted error
    string and never reaches the port."""
    k8s = FakeK8s()
    tool = factory(k8s, allowed_namespaces=("api",), dry_run=False)
    out = await tool.run(raw_input)
    assert out == "Error: namespace 'kube-system' not in allowed_namespaces"
    assert k8s.calls == []


# ---------------------------------------------------------------------------
# AC-5 — ScaleDeploymentInput replicas range (1..10)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("replicas", [0, 11])
async def test_scale_deployment_replicas_out_of_range(replicas):
    """AC-5: replicas < 1 or > 10 → pydantic ValidationError, port not called."""
    k8s = FakeK8s()
    tool = make_scale_deployment_tool(k8s, allowed_namespaces=("api",), dry_run=False)
    out = await tool.run({"namespace": "api", "name": "api", "replicas": replicas})
    assert "Error: ValidationError" in out
    assert k8s.calls == []


# ---------------------------------------------------------------------------
# AC-6 — dry_run=True propagation (parametrize across 3 factories)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("factory", "raw_input", "expected_call"),
    [
        (
            make_restart_deployment_tool,
            {"namespace": "api", "name": "api"},
            ("restart_deployment", "api", "api", True),
        ),
        (
            make_scale_deployment_tool,
            {"namespace": "api", "name": "api", "replicas": 4},
            ("scale_deployment", "api", "api", 4, True),
        ),
        (
            make_delete_pod_tool,
            {"namespace": "api", "name": "api-xxx"},
            ("delete_pod", "api", "api-xxx", True),
        ),
    ],
)
async def test_dry_run_true_propagates_to_port(factory, raw_input, expected_call):
    """AC-6: factory dry_run=True flag is forwarded to port as keyword arg."""
    k8s = FakeK8s()
    tool = factory(k8s, allowed_namespaces=("api",), dry_run=True)
    await tool.run(raw_input)
    assert k8s.calls == [expected_call]


# ---------------------------------------------------------------------------
# AC-7 — to_anthropic_schema() shape across 3 factories
# ---------------------------------------------------------------------------


async def test_anthropic_schema_shapes():
    """AC-7: schema name + required fields for all 3 factories."""
    k8s = FakeK8s()

    restart_schema = make_restart_deployment_tool(k8s, allowed_namespaces=("api",)).to_anthropic_schema()
    assert restart_schema["name"] == "restart_deployment"
    assert set(restart_schema["input_schema"]["required"]) == {"namespace", "name"}

    scale_schema = make_scale_deployment_tool(k8s, allowed_namespaces=("api",)).to_anthropic_schema()
    assert scale_schema["name"] == "scale_deployment"
    assert set(scale_schema["input_schema"]["required"]) == {"namespace", "name", "replicas"}

    delete_schema = make_delete_pod_tool(k8s, allowed_namespaces=("api",)).to_anthropic_schema()
    assert delete_schema["name"] == "delete_pod"
    assert set(delete_schema["input_schema"]["required"]) == {"namespace", "name"}


# ---------------------------------------------------------------------------
# subprocess mock helper for adapter tests (AC-8 ~ AC-11)
# ---------------------------------------------------------------------------


class _FakeProc:
    """Minimal asyncio subprocess stand-in: returncode + awaitable communicate()."""

    def __init__(self, stdout: bytes = b"ok\n", stderr: bytes = b"", returncode: int = 0) -> None:
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr


def _install_subprocess_capture(monkeypatch) -> list[tuple[str, ...]]:
    """Patch asyncio.create_subprocess_exec; return a list that accumulates
    the positional args each call received."""
    captured: list[tuple[str, ...]] = []

    async def fake_exec(*args, **kwargs):  # signature mirrors asyncio.create_subprocess_exec
        captured.append(tuple(args))
        return _FakeProc()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    return captured


# ---------------------------------------------------------------------------
# AC-8 / AC-9 / AC-10 — adapter command shapes (dry_run=False)
# ---------------------------------------------------------------------------


async def test_adapter_restart_deployment_command(monkeypatch):
    """AC-8: K8sAdapter.restart_deployment → `kubectl rollout restart deployment api -n api`."""
    captured = _install_subprocess_capture(monkeypatch)
    adapter = K8sAdapter()
    await adapter.restart_deployment("api", "api", dry_run=False)
    assert len(captured) == 1
    cmd = captured[0]
    assert cmd[0] == "kubectl"
    assert "rollout" in cmd
    assert "restart" in cmd
    assert "deployment" in cmd
    assert "api" in cmd
    assert "-n" in cmd
    # namespace flag pair appears together
    ns_idx = cmd.index("-n")
    assert cmd[ns_idx + 1] == "api"
    # no dry-run when flag is False
    assert not any("--dry-run" in c for c in cmd)


async def test_adapter_scale_deployment_command(monkeypatch):
    """AC-9: K8sAdapter.scale_deployment → `kubectl scale deployment api --replicas=5 -n api`."""
    captured = _install_subprocess_capture(monkeypatch)
    adapter = K8sAdapter()
    await adapter.scale_deployment("api", "api", 5, dry_run=False)
    assert len(captured) == 1
    cmd = captured[0]
    assert cmd[0] == "kubectl"
    assert "scale" in cmd
    assert "deployment" in cmd
    assert "api" in cmd
    assert "--replicas=5" in cmd
    ns_idx = cmd.index("-n")
    assert cmd[ns_idx + 1] == "api"
    assert not any("--dry-run" in c for c in cmd)


async def test_adapter_delete_pod_command(monkeypatch):
    """AC-10: K8sAdapter.delete_pod → `kubectl delete pod api-xxx -n api`."""
    captured = _install_subprocess_capture(monkeypatch)
    adapter = K8sAdapter()
    await adapter.delete_pod("api", "api-xxx", dry_run=False)
    assert len(captured) == 1
    cmd = captured[0]
    assert cmd[0] == "kubectl"
    assert "delete" in cmd
    assert "pod" in cmd
    assert "api-xxx" in cmd
    ns_idx = cmd.index("-n")
    assert cmd[ns_idx + 1] == "api"
    assert not any("--dry-run" in c for c in cmd)


# ---------------------------------------------------------------------------
# AC-11 — dry_run=True appends --dry-run=server (3 adapter methods)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method_name", "args"),
    [
        ("restart_deployment", ("api", "api")),
        ("scale_deployment", ("api", "api", 3)),
        ("delete_pod", ("api", "api-xxx")),
    ],
)
async def test_adapter_dry_run_adds_server_flag(monkeypatch, method_name, args):
    """AC-11: dry_run=True → kubectl args contain '--dry-run=server'."""
    captured = _install_subprocess_capture(monkeypatch)
    adapter = K8sAdapter()
    method = getattr(adapter, method_name)
    await method(*args, dry_run=True)
    assert len(captured) == 1
    cmd = captured[0]
    assert "--dry-run=server" in cmd


# ---------------------------------------------------------------------------
# EC-1 — port raises → Tool.run wraps into "Error: <type>: <msg>"
# ---------------------------------------------------------------------------


async def test_port_exception_wrapped_as_error_string():
    """EC-1: when port method raises, Tool.run returns 'Error: <type>: <msg>'."""
    k8s = FakeK8s(raise_exc=RuntimeError("kubectl boom"))
    tool = make_restart_deployment_tool(k8s, allowed_namespaces=("api",), dry_run=False)
    out = await tool.run({"namespace": "api", "name": "api"})
    assert out.startswith("Error: RuntimeError")
    assert "kubectl boom" in out
