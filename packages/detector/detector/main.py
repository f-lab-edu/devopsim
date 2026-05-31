from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import kopf
from anthropic import AsyncAnthropic

from detector.adapters.alertmanager import AlertmanagerAdapter
from detector.adapters.k8s import K8sAdapter
from detector.adapters.llm import AnthropicAdapter
from detector.adapters.loki import LokiAdapter
from detector.adapters.prometheus import PrometheusAdapter
from detector.adapters.runbooks import RunbookFilesystemAdapter
from detector.adapters.slack import SlackAdapter
from detector.agent.loop import InvestigationResult, investigate
from detector.agent.tools import (
    Tool,
    make_alertmanager_list_alerts_tool,
    make_delete_pod_tool,
    make_fetch_runbook_tool,
    make_kubectl_describe_tool,
    make_kubectl_events_tool,
    make_kubectl_get_tool,
    make_kubectl_logs_tool,
    make_loki_query_range_tool,
    make_loki_query_tool,
    make_promql_query_tool,
    make_promql_range_tool,
    make_restart_deployment_tool,
    make_scale_deployment_tool,
)
from detector.config import Config
from detector.destinations.slack import notify_investigation
from detector.metrics import DetectorMetrics, start_metrics_server
from detector.prompts import load_cluster_context
from detector.triggers.alertmanager_poller import make_poll_once
from detector.triggers.annotations import ANNOTATION_KEY, make_annotation_handler
from detector.triggers.k8s_events import (
    TriggerContext,
    make_event_handler,
    make_pod_status_handler,
)

logger = logging.getLogger("detector")

POLL_INTERVAL_SECONDS = 60
METRICS_PORT = 8000
RUNBOOKS_DIR = Path(__file__).parent / "runbooks"


@dataclass
class AppContext:
    config: Config
    metrics: DetectorMetrics
    event_handler: Callable[[dict], Awaitable[None]]
    pod_status_handler: Callable[[dict], Awaitable[None]]
    annotation_handler: Callable[..., Awaitable[None]]
    poll_once: Callable[[], Awaitable[None]]
    tools: list[Tool]


async def build_app(config: Config) -> AppContext:
    k8s = K8sAdapter()
    prometheus = PrometheusAdapter(base_url=config.prometheus_url, client=httpx.AsyncClient())
    loki = LokiAdapter(base_url=config.loki_url, client=httpx.AsyncClient())
    alertmanager = AlertmanagerAdapter(base_url=config.alertmanager_url, client=httpx.AsyncClient())
    slack = SlackAdapter(webhook_url=config.slack_webhook_url, client=httpx.AsyncClient())
    anthropic_client = AsyncAnthropic(api_key=config.anthropic_api_key)
    llm = AnthropicAdapter(api_key=config.anthropic_api_key, client=anthropic_client)
    runbook = RunbookFilesystemAdapter(root_dir=RUNBOOKS_DIR)

    cluster_context = load_cluster_context()
    runbook_catalog = await runbook.list_runbooks()

    tools: list[Tool] = [
        make_kubectl_get_tool(k8s),
        make_kubectl_describe_tool(k8s),
        make_kubectl_logs_tool(k8s),
        make_kubectl_events_tool(k8s),
        make_promql_query_tool(prometheus),
        make_promql_range_tool(prometheus),
        make_loki_query_tool(loki),
        make_loki_query_range_tool(loki),
        make_alertmanager_list_alerts_tool(alertmanager),
        make_fetch_runbook_tool(runbook),
        make_restart_deployment_tool(k8s, allowed_namespaces=config.allowed_namespaces, dry_run=config.dry_run),
        make_scale_deployment_tool(k8s, allowed_namespaces=config.allowed_namespaces, dry_run=config.dry_run),
        make_delete_pod_tool(k8s, allowed_namespaces=config.allowed_namespaces, dry_run=config.dry_run),
    ]

    metrics = DetectorMetrics()

    async def investigate_with_metrics(
        *,
        trigger: dict,
        tools: list[Tool],
        llm,
        runbook_catalog: str,
        cluster_context: str,
    ) -> InvestigationResult:
        result = await investigate(
            trigger=trigger,
            tools=tools,
            llm=llm,
            runbook_catalog=runbook_catalog,
            cluster_context=cluster_context,
            model=config.model,
        )
        metrics.record_investigation(result, trigger_source=trigger.get("source", "unknown"))
        return result

    trigger_ctx = TriggerContext()

    common_deps: dict = dict(
        investigate_fn=investigate_with_metrics,
        notify_fn=notify_investigation,
        tools=tools,
        llm=llm,
        runbook_catalog=runbook_catalog,
        cluster_context=cluster_context,
        slack=slack,
        grafana_url=config.grafana_url,
        context=trigger_ctx,
        allowed_namespaces=config.allowed_namespaces,
    )

    event_handler = make_event_handler(**common_deps)
    pod_status_handler = make_pod_status_handler(**common_deps)
    annotation_handler = make_annotation_handler(**common_deps)
    poll_once = make_poll_once(alertmanager=alertmanager, **common_deps)

    return AppContext(
        config=config,
        metrics=metrics,
        event_handler=event_handler,
        pod_status_handler=pod_status_handler,
        annotation_handler=annotation_handler,
        poll_once=poll_once,
        tools=tools,
    )


_app: AppContext | None = None
_background_tasks: set[asyncio.Task] = set()


@kopf.on.startup()
async def _on_startup(**_):
    global _app
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    config = Config.from_env()
    logger.info(
        "detector starting model=%s namespaces=%s dry_run=%s",
        config.model,
        config.allowed_namespaces,
        config.dry_run,
    )
    _app = await build_app(config)
    start_metrics_server(METRICS_PORT)
    task = asyncio.create_task(_poll_loop(_app.poll_once, POLL_INTERVAL_SECONDS))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def _kopf_body_to_dict(body: Any) -> dict:
    """kopf의 Body/BodyEssence는 nested 매핑이 dict-subclass라 그대로 read는 가능.
    annotation_handler 내부에서 body.get("metadata", {}).get("annotations") 형태로 접근하므로
    raw body를 그대로 전달한다 (top-level dict 변환은 nested mapping을 깨뜨릴 수 있음)."""
    return body


@kopf.on.event("v1", "events")
async def _on_event(body, **_):
    if _app is not None:
        await _app.event_handler(_kopf_body_to_dict(body))


@kopf.on.update("v1", "pods")
async def _on_pod_update(body, **_):
    if _app is None:
        return
    raw = _kopf_body_to_dict(body)
    metadata = raw.get("metadata") or {}
    name = metadata.get("name")
    annotations = metadata.get("annotations") or {}
    annotation_value = annotations.get(ANNOTATION_KEY)
    logger.info("pod update name=%s annotation=%s", name, annotation_value)
    await _app.pod_status_handler(raw)
    await _app.annotation_handler(new=annotation_value, body=raw)


async def _poll_loop(poll_once: Callable[[], Awaitable[None]], interval_seconds: int) -> None:
    while True:
        try:
            await poll_once()
        except Exception:
            logger.exception("poll_once failed")
        await asyncio.sleep(interval_seconds)


def main() -> int:
    return kopf.run() or 0


if __name__ == "__main__":
    sys.exit(main())
