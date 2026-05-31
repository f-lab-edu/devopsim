from unittest.mock import AsyncMock, MagicMock

from detector.agent.loop import InvestigationResult
from detector.triggers.k8s_events import (
    DEDUP_COOLDOWN_SECONDS,
    WATCHED_EVENT_REASONS,
    WATCHED_POD_TERMINATION_REASONS,
    TriggerContext,
    make_event_handler,
    make_pod_status_handler,
)


def _make_investigation_result() -> InvestigationResult:
    return InvestigationResult(
        final_text="rca summary",
        stop_reason="end_turn",
        tool_calls=[],
    )


def _build_event_handler(
    *,
    investigate_fn,
    notify_fn,
    context: TriggerContext,
    allowed_namespaces: tuple[str, ...] = ("api",),
    now_fn=lambda: 100.0,
):
    return make_event_handler(
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


def _build_pod_handler(
    *,
    investigate_fn,
    notify_fn,
    context: TriggerContext,
    allowed_namespaces: tuple[str, ...] = ("api",),
    now_fn=lambda: 100.0,
):
    return make_pod_status_handler(
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


# ---------- TriggerContext (AC-1 ~ AC-3) ----------


async def test_when_should_fire_is_called_for_the_first_time_with_a_key_the_system_returns_true():
    """AC-1"""
    ctx = TriggerContext()

    assert ctx.should_fire("k", now=10.0) is True


async def test_when_should_fire_called_twice_within_cooldown_the_system_returns_false_on_second_call():
    """AC-2"""
    ctx = TriggerContext()
    ctx.should_fire("k", now=10.0)

    second = ctx.should_fire("k", now=10.0 + DEDUP_COOLDOWN_SECONDS - 1)

    assert second is False


async def test_when_should_fire_called_twice_with_gap_at_least_cooldown_the_system_returns_true_again():
    """AC-3"""
    ctx = TriggerContext()
    ctx.should_fire("k", now=10.0)

    third = ctx.should_fire("k", now=10.0 + DEDUP_COOLDOWN_SECONDS)

    assert third is True


# ---------- Event handler (AC-4 ~ AC-7) ----------


async def test_when_event_reason_not_in_whitelist_the_system_does_not_call_investigate_or_notify():
    """AC-4"""
    investigate_fn = AsyncMock(return_value=_make_investigation_result())
    notify_fn = AsyncMock(return_value=None)
    handler = _build_event_handler(
        investigate_fn=investigate_fn,
        notify_fn=notify_fn,
        context=TriggerContext(),
    )
    # Pick a reason that is definitely not in WATCHED_EVENT_REASONS.
    bogus_reason = "SomeUnwatchedReason"
    assert bogus_reason not in WATCHED_EVENT_REASONS
    event_body = {
        "reason": bogus_reason,
        "involvedObject": {"namespace": "api", "name": "pod-1", "kind": "Pod"},
    }

    await handler(event_body)

    assert investigate_fn.await_count == 0
    assert notify_fn.await_count == 0


async def test_when_event_whitelisted_and_allowed_ns_the_system_calls_investigate_and_notify():
    """AC-5"""
    investigate_fn = AsyncMock(return_value=_make_investigation_result())
    notify_fn = AsyncMock(return_value=None)
    handler = _build_event_handler(
        investigate_fn=investigate_fn,
        notify_fn=notify_fn,
        context=TriggerContext(),
        allowed_namespaces=("api",),
    )
    reason = next(iter(WATCHED_EVENT_REASONS))
    event_body = {
        "reason": reason,
        "involvedObject": {"namespace": "api", "name": "pod-1", "kind": "Pod"},
    }

    await handler(event_body)

    assert investigate_fn.await_count == 1
    assert notify_fn.await_count == 1

    trigger_payload = investigate_fn.await_args.kwargs.get("trigger")
    if trigger_payload is None:
        # Fall back to positional args if implementation passes trigger positionally.
        trigger_payload = investigate_fn.await_args.args[0]

    assert trigger_payload["source"] == "k8s_event"
    assert trigger_payload["reason"] == reason
    assert trigger_payload["namespace"] == "api"
    assert trigger_payload["name"] == "pod-1"


async def test_when_event_namespace_not_in_allowed_namespaces_the_system_does_not_call_investigate_or_notify():
    """AC-6"""
    investigate_fn = AsyncMock(return_value=_make_investigation_result())
    notify_fn = AsyncMock(return_value=None)
    handler = _build_event_handler(
        investigate_fn=investigate_fn,
        notify_fn=notify_fn,
        context=TriggerContext(),
        allowed_namespaces=("api",),
    )
    reason = next(iter(WATCHED_EVENT_REASONS))
    event_body = {
        "reason": reason,
        "involvedObject": {"namespace": "kube-system", "name": "pod-x", "kind": "Pod"},
    }

    await handler(event_body)

    assert investigate_fn.await_count == 0
    assert notify_fn.await_count == 0


async def test_when_same_reason_namespace_name_arrives_within_cooldown_the_system_dedups_and_skips_second_event():
    """AC-7"""
    investigate_fn = AsyncMock(return_value=_make_investigation_result())
    notify_fn = AsyncMock(return_value=None)
    clock = {"t": 100.0}
    handler = _build_event_handler(
        investigate_fn=investigate_fn,
        notify_fn=notify_fn,
        context=TriggerContext(),
        allowed_namespaces=("api",),
        now_fn=lambda: clock["t"],
    )
    reason = next(iter(WATCHED_EVENT_REASONS))
    event_body = {
        "reason": reason,
        "involvedObject": {"namespace": "api", "name": "pod-1", "kind": "Pod"},
    }

    await handler(event_body)
    # Advance clock by less than cooldown.
    clock["t"] = 100.0 + DEDUP_COOLDOWN_SECONDS - 1
    await handler(event_body)

    assert investigate_fn.await_count == 1
    assert notify_fn.await_count == 1


# ---------- Pod status handler (AC-8 ~ AC-9) ----------


async def test_when_pod_status_has_oomkilled_last_state_the_system_calls_investigate_and_notify():
    """AC-8"""
    investigate_fn = AsyncMock(return_value=_make_investigation_result())
    notify_fn = AsyncMock(return_value=None)
    handler = _build_pod_handler(
        investigate_fn=investigate_fn,
        notify_fn=notify_fn,
        context=TriggerContext(),
        allowed_namespaces=("api",),
    )
    oom_reason = next(iter(WATCHED_POD_TERMINATION_REASONS))
    assert oom_reason == "OOMKilled"
    pod_body = {
        "metadata": {"namespace": "api", "name": "pod-1"},
        "status": {
            "containerStatuses": [
                {
                    "name": "api",
                    "lastState": {"terminated": {"reason": "OOMKilled"}},
                }
            ]
        },
    }

    await handler(pod_body)

    assert investigate_fn.await_count == 1
    assert notify_fn.await_count == 1

    trigger_payload = investigate_fn.await_args.kwargs.get("trigger")
    if trigger_payload is None:
        trigger_payload = investigate_fn.await_args.args[0]

    assert trigger_payload["source"] == "pod_status"
    assert trigger_payload["reason"] == "OOMKilled"
    assert trigger_payload["namespace"] == "api"
    assert trigger_payload["name"] == "pod-1"


async def test_when_pod_status_has_no_oomkilled_last_state_the_system_does_not_call_investigate_or_notify():
    """AC-9"""
    investigate_fn = AsyncMock(return_value=_make_investigation_result())
    notify_fn = AsyncMock(return_value=None)
    handler = _build_pod_handler(
        investigate_fn=investigate_fn,
        notify_fn=notify_fn,
        context=TriggerContext(),
        allowed_namespaces=("api",),
    )
    pod_body = {
        "metadata": {"namespace": "api", "name": "pod-1"},
        "status": {
            "containerStatuses": [
                {
                    "name": "api",
                    "lastState": {"terminated": {"reason": "Completed"}},
                }
            ]
        },
    }

    await handler(pod_body)

    assert investigate_fn.await_count == 0
    assert notify_fn.await_count == 0


# ---------- Error & Edge Cases (EC-1) ----------


async def test_when_investigate_fn_raises_the_handler_swallows_exception_and_does_not_call_notify():
    """EC-1"""
    investigate_fn = AsyncMock(side_effect=RuntimeError("boom"))
    notify_fn = AsyncMock(return_value=None)
    handler = _build_event_handler(
        investigate_fn=investigate_fn,
        notify_fn=notify_fn,
        context=TriggerContext(),
        allowed_namespaces=("api",),
    )
    reason = next(iter(WATCHED_EVENT_REASONS))
    event_body = {
        "reason": reason,
        "involvedObject": {"namespace": "api", "name": "pod-1", "kind": "Pod"},
    }

    # Must NOT raise.
    await handler(event_body)

    assert investigate_fn.await_count == 1
    assert notify_fn.await_count == 0
