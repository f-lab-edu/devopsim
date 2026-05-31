from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from typing import Any

from .k8s_events import (
    TriggerContext,
    _build_pipeline,
    _dedup_and_invoke,
)

WATCHED_ALERTNAMES: frozenset[str] = frozenset(
    {
        "DBPoolWaiting",
        "HighCPU",
        "HighErrorRate",
    }
)


def _parse_alert_list(raw: str) -> list[dict[str, Any]] | None:
    try:
        alerts = json.loads(raw)
    except Exception:
        return None
    if not isinstance(alerts, list):
        return None
    return alerts


def make_poll_once(
    *,
    alertmanager,
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
) -> Callable[[], Awaitable[None]]:
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

    async def poll_once() -> None:
        try:
            raw = await alertmanager.list_alerts(None, "active")
        except Exception:
            return

        alerts = _parse_alert_list(raw)
        if alerts is None:
            return

        for alert in alerts:
            labels: dict[str, Any] = alert.get("labels", {}) or {}
            alertname = labels.get("alertname")
            namespace = labels.get("namespace")
            if alertname not in WATCHED_ALERTNAMES:
                continue
            if namespace not in allowed_namespaces:
                continue
            trigger = {
                "source": "alertmanager",
                "alertname": alertname,
                "namespace": namespace,
                "labels": labels,
                "annotations": alert.get("annotations", {}) or {},
            }
            await _dedup_and_invoke(
                pipeline=pipeline,
                context=context,
                now_fn=now_fn,
                dedup_key=f"alert:{alertname}:{namespace}",
                trigger=trigger,
            )

    return poll_once
