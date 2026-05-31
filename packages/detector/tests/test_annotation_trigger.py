from unittest.mock import AsyncMock, MagicMock

import pytest

from detector.agent.loop import InvestigationResult
from detector.triggers.annotations import (
    ANNOTATION_KEY,
    ANNOTATION_TRIGGER_VALUE,
    make_annotation_handler,
)
from detector.triggers.k8s_events import TriggerContext


def _make_investigation_result() -> InvestigationResult:
    return InvestigationResult(
        final_text="rca summary",
        stop_reason="end_turn",
        tool_calls=[],
    )


def _build_annotation_handler(
    *,
    investigate_fn,
    notify_fn,
    context: TriggerContext,
    allowed_namespaces: tuple[str, ...] = ("api",),
    now_fn=lambda: 100.0,
):
    return make_annotation_handler(
        investigate_fn=investigate_fn,
        notify_fn=notify_fn,
        tools=[],
        llm=MagicMock(),
        runbook_catalog="stub catalog",
        cluster_context="stub context",
        slack=MagicMock(),
        grafana_url="https://grafana.example.com",
        context=context,
        allowed_namespaces=allowed_namespaces,
        now_fn=now_fn,
    )


# ---------- Constants (AC-1) ----------


def test_annotation_constants_have_exact_expected_values():
    """AC-1: exact-match for ANNOTATION_KEY and ANNOTATION_TRIGGER_VALUE."""
    assert ANNOTATION_KEY == "detector.devopsim.cloud/investigate"
    assert ANNOTATION_TRIGGER_VALUE == "true"


# ---------- handler behavior (AC-2 ~ AC-5) ----------


async def test_when_annotation_new_is_true_and_namespace_allowed_the_system_calls_investigate_and_notify():
    """AC-2"""
    investigate_fn = AsyncMock(return_value=_make_investigation_result())
    notify_fn = AsyncMock(return_value=None)
    handler = _build_annotation_handler(
        investigate_fn=investigate_fn,
        notify_fn=notify_fn,
        context=TriggerContext(),
        allowed_namespaces=("api",),
    )
    body = {"metadata": {"namespace": "api", "name": "api-xxx"}}

    await handler(new="true", body=body)

    assert investigate_fn.await_count == 1
    assert notify_fn.await_count == 1

    trigger_payload = investigate_fn.await_args.kwargs.get("trigger")
    if trigger_payload is None:
        trigger_payload = investigate_fn.await_args.args[0]

    assert trigger_payload["source"] == "annotation"
    assert trigger_payload["kind"] == "Pod"
    assert trigger_payload["namespace"] == "api"
    assert trigger_payload["name"] == "api-xxx"


@pytest.mark.parametrize("new", ["false", None, "yes", "1", ""])
async def test_when_annotation_new_is_not_exactly_true_the_system_does_not_call_investigate_or_notify(new):
    """AC-3: parametrize over non-"true" values."""
    investigate_fn = AsyncMock(return_value=_make_investigation_result())
    notify_fn = AsyncMock(return_value=None)
    handler = _build_annotation_handler(
        investigate_fn=investigate_fn,
        notify_fn=notify_fn,
        context=TriggerContext(),
        allowed_namespaces=("api",),
    )
    body = {"metadata": {"namespace": "api", "name": "api-xxx"}}

    await handler(new=new, body=body)

    assert investigate_fn.await_count == 0
    assert notify_fn.await_count == 0


async def test_when_annotation_namespace_not_in_allowed_namespaces_the_system_does_not_call_investigate_or_notify():
    """AC-4"""
    investigate_fn = AsyncMock(return_value=_make_investigation_result())
    notify_fn = AsyncMock(return_value=None)
    handler = _build_annotation_handler(
        investigate_fn=investigate_fn,
        notify_fn=notify_fn,
        context=TriggerContext(),
        allowed_namespaces=("api",),
    )
    body = {"metadata": {"namespace": "kube-system", "name": "pod-x"}}

    await handler(new="true", body=body)

    assert investigate_fn.await_count == 0
    assert notify_fn.await_count == 0


async def test_when_same_namespace_name_arrives_within_cooldown_the_system_dedups_and_skips_second_call():
    """AC-5"""
    investigate_fn = AsyncMock(return_value=_make_investigation_result())
    notify_fn = AsyncMock(return_value=None)
    clock = {"t": 100.0}
    handler = _build_annotation_handler(
        investigate_fn=investigate_fn,
        notify_fn=notify_fn,
        context=TriggerContext(),
        allowed_namespaces=("api",),
        now_fn=lambda: clock["t"],
    )
    body = {"metadata": {"namespace": "api", "name": "api-xxx"}}

    await handler(new="true", body=body)
    # Advance clock by less than 5 minutes (dedup cooldown).
    clock["t"] = 100.0 + 60.0
    await handler(new="true", body=body)

    assert investigate_fn.await_count == 1
    assert notify_fn.await_count == 1


# ---------- Error & Edge Cases (EC-1) ----------


async def test_when_investigate_fn_raises_the_handler_swallows_exception_and_does_not_call_notify():
    """EC-1"""
    investigate_fn = AsyncMock(side_effect=RuntimeError("boom"))
    notify_fn = AsyncMock(return_value=None)
    handler = _build_annotation_handler(
        investigate_fn=investigate_fn,
        notify_fn=notify_fn,
        context=TriggerContext(),
        allowed_namespaces=("api",),
    )
    body = {"metadata": {"namespace": "api", "name": "api-xxx"}}

    # Must NOT raise.
    await handler(new="true", body=body)

    assert investigate_fn.await_count == 1
    assert notify_fn.await_count == 0
