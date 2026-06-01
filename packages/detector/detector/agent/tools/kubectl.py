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
    async def rollout_history(
        self,
        kind: str,
        namespace: str,
        name: str,
        revision: int | None,
    ) -> str: ...
    async def restart_deployment(self, namespace: str, name: str, *, dry_run: bool) -> str: ...
    async def scale_deployment(self, namespace: str, name: str, replicas: int, *, dry_run: bool) -> str: ...
    async def delete_pod(self, namespace: str, name: str, *, dry_run: bool) -> str: ...


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
        return await k8s.logs(input.namespace, input.pod, input.container, input.tail_lines, input.previous)

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


class KubectlRolloutHistoryInput(BaseModel):
    kind: str = Field(default="deployment", description="Workload kind: deployment / statefulset / daemonset")
    namespace: str
    name: str
    revision: int | None = Field(
        default=None,
        description=(
            "Specific revision number to inspect (returns pod template with image/env). Omit for revision list."
        ),
    )


def make_kubectl_rollout_history_tool(k8s: KubernetesPort) -> Tool:
    async def handler(input: KubectlRolloutHistoryInput) -> str:
        return await k8s.rollout_history(input.kind, input.namespace, input.name, input.revision)

    return Tool(
        name="kubectl_rollout_history",
        description=(
            "kubectl rollout history. Without revision: revision list with CHANGE-CAUSE. "
            "With revision: that revision's pod template (image, env). Use to compare current vs prior deploy."
        ),
        input_model=KubectlRolloutHistoryInput,
        handler=handler,
    )
