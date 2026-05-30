import asyncio
from typing import Protocol

from pydantic import BaseModel, Field

from .base import Tool


class KubernetesPort(Protocol):
    async def get(self, kind: str, namespace: str, name: str | None) -> str: ...
    async def describe(self, kind: str, namespace: str, name: str) -> str: ...
    async def logs(
        self,
        namespace: str,
        pod: str,
        container: str | None,
        tail_lines: int,
        previous: bool,
    ) -> str: ...
    async def list_events(self, namespace: str, field_selector: str | None) -> str: ...


class K8sAdapter:
    async def _run(self, *args: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "kubectl",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            return f"kubectl exit {proc.returncode}\n{stderr.decode().strip()}"
        return stdout.decode()

    async def get(self, kind: str, namespace: str, name: str | None) -> str:
        args = ["get", kind]
        if name:
            args.append(name)
        args += ["-n", namespace, "-o", "yaml"]
        return await self._run(*args)

    async def describe(self, kind: str, namespace: str, name: str) -> str:
        return await self._run("describe", kind, name, "-n", namespace)

    async def logs(
        self,
        namespace: str,
        pod: str,
        container: str | None,
        tail_lines: int,
        previous: bool,
    ) -> str:
        args = ["logs", pod, "-n", namespace, f"--tail={tail_lines}"]
        if container:
            args += ["-c", container]
        if previous:
            args.append("--previous")
        return await self._run(*args)

    async def list_events(self, namespace: str, field_selector: str | None) -> str:
        args = ["get", "events", "-n", namespace, "--sort-by=.lastTimestamp"]
        if field_selector:
            args += ["--field-selector", field_selector]
        return await self._run(*args)


class KubectlGetInput(BaseModel):
    kind: str = Field(description="K8s kind (Pod, Deployment, Service, ConfigMap, ReplicaSet, ...)")
    namespace: str
    name: str | None = Field(default=None, description="Resource name. Omit to list all in namespace.")


def make_kubectl_get_tool(k8s: KubernetesPort) -> Tool:
    async def handler(input: KubectlGetInput) -> str:
        return await k8s.get(input.kind, input.namespace, input.name)

    return Tool(
        name="kubectl_get",
        description="Fetch a K8s resource by kind/namespace/[name]. Returns YAML.",
        input_model=KubectlGetInput,
        handler=handler,
    )


class KubectlDescribeInput(BaseModel):
    kind: str
    namespace: str
    name: str


def make_kubectl_describe_tool(k8s: KubernetesPort) -> Tool:
    async def handler(input: KubectlDescribeInput) -> str:
        return await k8s.describe(input.kind, input.namespace, input.name)

    return Tool(
        name="kubectl_describe",
        description="kubectl describe <kind> <name> -n <namespace>. Returns events + status detail.",
        input_model=KubectlDescribeInput,
        handler=handler,
    )


class KubectlLogsInput(BaseModel):
    namespace: str
    pod: str
    container: str | None = Field(default=None, description="Container name if multi-container pod.")
    tail_lines: int = Field(default=200, description="Number of recent lines to fetch.")
    previous: bool = Field(
        default=False,
        description="True to fetch logs from previous terminated container (post-OOM/crash).",
    )


def make_kubectl_logs_tool(k8s: KubernetesPort) -> Tool:
    async def handler(input: KubectlLogsInput) -> str:
        return await k8s.logs(
            input.namespace, input.pod, input.container, input.tail_lines, input.previous
        )

    return Tool(
        name="kubectl_logs",
        description="Fetch container logs. Use previous=true to inspect logs of a crashed container.",
        input_model=KubectlLogsInput,
        handler=handler,
    )


class KubectlEventsInput(BaseModel):
    namespace: str
    field_selector: str | None = Field(
        default=None,
        description="kubectl --field-selector. e.g. 'reason=BackOff' or 'involvedObject.name=mypod' or 'type=Warning'.",
    )


def make_kubectl_events_tool(k8s: KubernetesPort) -> Tool:
    async def handler(input: KubectlEventsInput) -> str:
        return await k8s.list_events(input.namespace, input.field_selector)

    return Tool(
        name="kubectl_events",
        description="List K8s events sorted by lastTimestamp. Use field_selector to filter (e.g. reason=BackOff).",
        input_model=KubectlEventsInput,
        handler=handler,
    )
