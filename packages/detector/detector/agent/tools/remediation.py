from collections.abc import Sequence

from pydantic import BaseModel, Field

from .base import Tool
from .kubectl import KubernetesPort


class RestartDeploymentInput(BaseModel):
    namespace: str
    name: str


class ScaleDeploymentInput(BaseModel):
    namespace: str
    name: str
    replicas: int = Field(ge=1, le=10)


class DeletePodInput(BaseModel):
    namespace: str
    name: str


def _check_namespace(namespace: str, allowed: tuple[str, ...]) -> str | None:
    if namespace in allowed:
        return None
    return f"Error: namespace '{namespace}' not in allowed_namespaces"


def make_restart_deployment_tool(
    k8s: KubernetesPort,
    *,
    allowed_namespaces: Sequence[str],
    dry_run: bool = False,
) -> Tool:
    allowed = tuple(allowed_namespaces)

    async def handler(input: RestartDeploymentInput) -> str:
        if (err := _check_namespace(input.namespace, allowed)) is not None:
            return err
        return await k8s.restart_deployment(input.namespace, input.name, dry_run=dry_run)

    return Tool(
        name="restart_deployment",
        description="kubectl rollout restart deployment <name> -n <namespace>.",
        input_model=RestartDeploymentInput,
        handler=handler,
    )


def make_scale_deployment_tool(
    k8s: KubernetesPort,
    *,
    allowed_namespaces: Sequence[str],
    dry_run: bool = False,
) -> Tool:
    allowed = tuple(allowed_namespaces)

    async def handler(input: ScaleDeploymentInput) -> str:
        if (err := _check_namespace(input.namespace, allowed)) is not None:
            return err
        return await k8s.scale_deployment(input.namespace, input.name, input.replicas, dry_run=dry_run)

    return Tool(
        name="scale_deployment",
        description="kubectl scale deployment <name> --replicas=<n> -n <namespace>. replicas: 1..10.",
        input_model=ScaleDeploymentInput,
        handler=handler,
    )


def make_delete_pod_tool(
    k8s: KubernetesPort,
    *,
    allowed_namespaces: Sequence[str],
    dry_run: bool = False,
) -> Tool:
    allowed = tuple(allowed_namespaces)

    async def handler(input: DeletePodInput) -> str:
        if (err := _check_namespace(input.namespace, allowed)) is not None:
            return err
        return await k8s.delete_pod(input.namespace, input.name, dry_run=dry_run)

    return Tool(
        name="delete_pod",
        description="kubectl delete pod <name> -n <namespace>.",
        input_model=DeletePodInput,
        handler=handler,
    )
