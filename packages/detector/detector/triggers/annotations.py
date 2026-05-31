from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from .k8s_events import (
    TriggerContext,
    _build_pipeline,
    _dedup_and_invoke,
)

ANNOTATION_KEY = "detector.devopsim.cloud/investigate"
ANNOTATION_TRIGGER_VALUE = "true"


AnnotationHandler = Callable[..., Awaitable[None]]


def make_annotation_handler(
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
) -> AnnotationHandler:
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

    async def handler(*, new: Any, body: dict[str, Any]) -> None:
        if new != ANNOTATION_TRIGGER_VALUE:
            return
        metadata = body.get("metadata", {}) or {}
        namespace = metadata.get("namespace")
        name = metadata.get("name")
        if namespace not in allowed_namespaces:
            return
        trigger = {
            "source": "annotation",
            "kind": "Pod",
            "namespace": namespace,
            "name": name,
        }
        await _dedup_and_invoke(
            pipeline=pipeline,
            context=context,
            now_fn=now_fn,
            dedup_key=f"annotation:{namespace}:{name}",
            trigger=trigger,
        )

    return handler
