from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

DEDUP_COOLDOWN_SECONDS = 300.0

WATCHED_EVENT_REASONS: frozenset[str] = frozenset(
    {
        "BackOff",
        "CrashLoopBackOff",
        "Failed",
        "FailedScheduling",
        "Unhealthy",
    }
)

WATCHED_POD_TERMINATION_REASONS: frozenset[str] = frozenset({"OOMKilled"})


@dataclass
class TriggerContext:
    _last_fired: dict[str, float] = field(default_factory=dict)

    def should_fire(self, key: str, *, now: float) -> bool:
        last = self._last_fired.get(key)
        if last is not None and (now - last) < DEDUP_COOLDOWN_SECONDS:
            return False
        self._last_fired[key] = now
        return True


Handler = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass(frozen=True)
class _Pipeline:
    """Bundled investigation + notification dependencies, shared by all handlers."""

    investigate_fn: Any
    notify_fn: Any
    tools: Any
    llm: Any
    runbook_catalog: str
    cluster_context: str
    slack: Any
    grafana_url: str


def _build_pipeline(
    *,
    investigate_fn: Any,
    notify_fn: Any,
    tools: Any,
    llm: Any,
    runbook_catalog: str,
    cluster_context: str,
    slack: Any,
    grafana_url: str,
) -> _Pipeline:
    return _Pipeline(
        investigate_fn=investigate_fn,
        notify_fn=notify_fn,
        tools=tools,
        llm=llm,
        runbook_catalog=runbook_catalog,
        cluster_context=cluster_context,
        slack=slack,
        grafana_url=grafana_url,
    )


async def _safe_invoke(pipeline: _Pipeline, trigger: dict[str, Any]) -> None:
    try:
        result = await pipeline.investigate_fn(
            trigger=trigger,
            tools=pipeline.tools,
            llm=pipeline.llm,
            runbook_catalog=pipeline.runbook_catalog,
            cluster_context=pipeline.cluster_context,
        )
    except Exception:
        return
    try:
        await pipeline.notify_fn(result, pipeline.slack, trigger=trigger, grafana_url=pipeline.grafana_url)
    except Exception:
        return


async def _dedup_and_invoke(
    *,
    pipeline: _Pipeline,
    context: TriggerContext,
    now_fn: Callable[[], float],
    dedup_key: str,
    trigger: dict[str, Any],
) -> None:
    if not context.should_fire(dedup_key, now=now_fn()):
        return
    await _safe_invoke(pipeline, trigger)


def make_event_handler(
    *,
    investigate_fn,
    notify_fn,
    tools,
    llm,
    runbook_catalog: str,
    cluster_context: str,
    slack,
    grafana_url: str,
    context: TriggerContext,
    allowed_namespaces: tuple[str, ...],
    now_fn: Callable[[], float] = time.monotonic,
) -> Handler:
    pipeline = _build_pipeline(
        investigate_fn=investigate_fn,
        notify_fn=notify_fn,
        tools=tools,
        llm=llm,
        runbook_catalog=runbook_catalog,
        cluster_context=cluster_context,
        slack=slack,
        grafana_url=grafana_url,
    )

    async def handler(event_body: dict[str, Any]) -> None:
        reason = event_body.get("reason")
        if reason not in WATCHED_EVENT_REASONS:
            return
        involved = event_body.get("involvedObject", {}) or {}
        namespace = involved.get("namespace")
        name = involved.get("name")
        if namespace not in allowed_namespaces:
            return
        trigger = {
            "source": "k8s_event",
            "reason": reason,
            "namespace": namespace,
            "name": name,
            "kind": involved.get("kind"),
        }
        await _dedup_and_invoke(
            pipeline=pipeline,
            context=context,
            now_fn=now_fn,
            dedup_key=f"event:{reason}:{namespace}:{name}",
            trigger=trigger,
        )

    return handler


def _extract_pod_termination_reason(pod_body: dict[str, Any]) -> str | None:
    status = pod_body.get("status", {}) or {}
    for cs in status.get("containerStatuses", []) or []:
        last_state = cs.get("lastState", {}) or {}
        terminated = last_state.get("terminated", {}) or {}
        reason = terminated.get("reason")
        if reason in WATCHED_POD_TERMINATION_REASONS:
            return reason
    return None


def make_pod_status_handler(
    *,
    investigate_fn,
    notify_fn,
    tools,
    llm,
    runbook_catalog: str,
    cluster_context: str,
    slack,
    grafana_url: str,
    context: TriggerContext,
    allowed_namespaces: tuple[str, ...],
    now_fn: Callable[[], float] = time.monotonic,
) -> Handler:
    pipeline = _build_pipeline(
        investigate_fn=investigate_fn,
        notify_fn=notify_fn,
        tools=tools,
        llm=llm,
        runbook_catalog=runbook_catalog,
        cluster_context=cluster_context,
        slack=slack,
        grafana_url=grafana_url,
    )

    async def handler(pod_body: dict[str, Any]) -> None:
        metadata = pod_body.get("metadata", {}) or {}
        namespace = metadata.get("namespace")
        name = metadata.get("name")
        if namespace not in allowed_namespaces:
            return
        reason = _extract_pod_termination_reason(pod_body)
        if reason is None:
            return
        trigger = {
            "source": "pod_status",
            "reason": reason,
            "namespace": namespace,
            "name": name,
        }
        await _dedup_and_invoke(
            pipeline=pipeline,
            context=context,
            now_fn=now_fn,
            dedup_key=f"pod:{reason}:{namespace}:{name}",
            trigger=trigger,
        )

    return handler
