import json
from unittest.mock import AsyncMock, MagicMock

from detector.agent.loop import InvestigationResult
from detector.triggers.alertmanager_poller import WATCHED_ALERTNAMES, make_poll_once
from detector.triggers.k8s_events import TriggerContext


class FakeAlertmanager:
    """In-test fake satisfying AlertmanagerPort."""

    def __init__(
        self,
        responses: list[str] | None = None,
        raise_exc: Exception | None = None,
    ):
        self._responses = list(responses or [])
        self._raise_exc = raise_exc
        self.calls: list[dict] = []

    async def list_alerts(self, matchers, state):
        self.calls.append({"matchers": matchers, "state": state})
        if self._raise_exc is not None:
            raise self._raise_exc
        if self._responses:
            return self._responses.pop(0)
        return "[]"


def _make_investigation_result() -> InvestigationResult:
    return InvestigationResult(
        final_text="rca summary",
        stop_reason="end_turn",
        tool_calls=[],
    )


def _alert(
    alertname: str,
    namespace: str = "api",
    severity: str = "warning",
    extra_labels: dict | None = None,
) -> dict:
    labels = {
        "alertname": alertname,
        "namespace": namespace,
        "severity": severity,
    }
    if extra_labels:
        labels.update(extra_labels)
    return {
        "labels": labels,
        "status": {"state": "active"},
        "annotations": {"summary": f"{alertname} summary"},
    }


def _build_poll_once(
    *,
    alertmanager,
    investigate_fn,
    notify_fn,
    context: TriggerContext,
    allowed_namespaces: tuple[str, ...] = ("api",),
    now_fn=lambda: 100.0,
):
    return make_poll_once(
        alertmanager=alertmanager,
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


# ---------- AC-1: list_alerts called exactly with matchers=None, state="active" ----------


async def test_when_poll_once_called_the_system_invokes_list_alerts_with_matchers_none_and_state_active():
    """AC-1"""
    am = FakeAlertmanager(responses=["[]"])
    investigate_fn = AsyncMock(return_value=_make_investigation_result())
    notify_fn = AsyncMock(return_value=None)
    poll_once = _build_poll_once(
        alertmanager=am,
        investigate_fn=investigate_fn,
        notify_fn=notify_fn,
        context=TriggerContext(),
    )

    await poll_once()

    assert len(am.calls) == 1
    assert am.calls[0] == {"matchers": None, "state": "active"}


# ---------- AC-2: empty response → no investigate / notify ----------


async def test_when_alertmanager_returns_empty_list_the_system_does_not_call_investigate_or_notify():
    """AC-2"""
    am = FakeAlertmanager(responses=["[]"])
    investigate_fn = AsyncMock(return_value=_make_investigation_result())
    notify_fn = AsyncMock(return_value=None)
    poll_once = _build_poll_once(
        alertmanager=am,
        investigate_fn=investigate_fn,
        notify_fn=notify_fn,
        context=TriggerContext(),
    )

    await poll_once()

    assert investigate_fn.await_count == 0
    assert notify_fn.await_count == 0


# ---------- AC-3: non-watched alertname → no investigate / notify ----------


async def test_when_alertmanager_returns_only_non_watched_alertname_the_system_does_not_call_investigate_or_notify():
    """AC-3"""
    # "Watchdog" is intentionally NOT in WATCHED_ALERTNAMES.
    assert "Watchdog" not in WATCHED_ALERTNAMES
    payload = json.dumps([_alert("Watchdog", namespace="api")])
    am = FakeAlertmanager(responses=[payload])
    investigate_fn = AsyncMock(return_value=_make_investigation_result())
    notify_fn = AsyncMock(return_value=None)
    poll_once = _build_poll_once(
        alertmanager=am,
        investigate_fn=investigate_fn,
        notify_fn=notify_fn,
        context=TriggerContext(),
    )

    await poll_once()

    assert investigate_fn.await_count == 0
    assert notify_fn.await_count == 0


# ---------- AC-4: watched + allowed_ns → investigate + notify with payload ----------


async def test_when_alertmanager_returns_watched_alert_in_allowed_namespace_the_system_calls_investigate_and_notify():
    """AC-4"""
    alert = _alert("DBPoolWaiting", namespace="api", severity="warning")
    payload = json.dumps([alert])
    am = FakeAlertmanager(responses=[payload])
    investigate_fn = AsyncMock(return_value=_make_investigation_result())
    notify_fn = AsyncMock(return_value=None)
    poll_once = _build_poll_once(
        alertmanager=am,
        investigate_fn=investigate_fn,
        notify_fn=notify_fn,
        context=TriggerContext(),
        allowed_namespaces=("api",),
    )

    await poll_once()

    assert investigate_fn.await_count == 1
    assert notify_fn.await_count == 1

    trigger_payload = investigate_fn.await_args.kwargs.get("trigger")
    if trigger_payload is None:
        trigger_payload = investigate_fn.await_args.args[0]

    assert trigger_payload["source"] == "alertmanager"
    assert trigger_payload["alertname"] == "DBPoolWaiting"
    assert trigger_payload["namespace"] == "api"
    assert trigger_payload["labels"] == alert["labels"]


# ---------- AC-5: watched but namespace not in allowed → skip ----------


async def test_when_watched_alert_namespace_not_in_allowed_the_system_skips_investigate_and_notify():
    """AC-5"""
    payload = json.dumps([_alert("DBPoolWaiting", namespace="kube-system")])
    am = FakeAlertmanager(responses=[payload])
    investigate_fn = AsyncMock(return_value=_make_investigation_result())
    notify_fn = AsyncMock(return_value=None)
    poll_once = _build_poll_once(
        alertmanager=am,
        investigate_fn=investigate_fn,
        notify_fn=notify_fn,
        context=TriggerContext(),
        allowed_namespaces=("api",),
    )

    await poll_once()

    assert investigate_fn.await_count == 0
    assert notify_fn.await_count == 0


# ---------- AC-6: dedup across cycles within cooldown ----------


async def test_when_same_alertname_namespace_repeats_within_cooldown_across_two_cycles_the_system_dedups_second_cycle():
    """AC-6"""
    payload = json.dumps([_alert("DBPoolWaiting", namespace="api")])
    # Same response on both cycles.
    am = FakeAlertmanager(responses=[payload, payload])
    investigate_fn = AsyncMock(return_value=_make_investigation_result())
    notify_fn = AsyncMock(return_value=None)
    clock = {"t": 100.0}
    poll_once = _build_poll_once(
        alertmanager=am,
        investigate_fn=investigate_fn,
        notify_fn=notify_fn,
        context=TriggerContext(),
        allowed_namespaces=("api",),
        now_fn=lambda: clock["t"],
    )

    await poll_once()
    # Less than 5min later → dedup must skip.
    clock["t"] = 200.0
    await poll_once()

    assert investigate_fn.await_count == 1
    assert notify_fn.await_count == 1
    # Confirm alertmanager was polled both cycles.
    assert len(am.calls) == 2


# ---------- AC-7: two watched alerts in one cycle → 2 invocations sequentially ----------


async def test_when_two_watched_alerts_in_one_cycle_the_system_calls_investigate_and_notify_twice():
    """AC-7"""
    payload = json.dumps(
        [
            _alert("DBPoolWaiting", namespace="api"),
            _alert("HighCPU", namespace="api"),
        ]
    )
    am = FakeAlertmanager(responses=[payload])
    investigate_fn = AsyncMock(return_value=_make_investigation_result())
    notify_fn = AsyncMock(return_value=None)
    poll_once = _build_poll_once(
        alertmanager=am,
        investigate_fn=investigate_fn,
        notify_fn=notify_fn,
        context=TriggerContext(),
        allowed_namespaces=("api",),
    )

    await poll_once()

    assert investigate_fn.await_count == 2
    assert notify_fn.await_count == 2

    # Sequential order: DBPoolWaiting first, HighCPU second.
    first_call = investigate_fn.await_args_list[0]
    second_call = investigate_fn.await_args_list[1]

    first_trigger = first_call.kwargs.get("trigger") or first_call.args[0]
    second_trigger = second_call.kwargs.get("trigger") or second_call.args[0]

    assert first_trigger["alertname"] == "DBPoolWaiting"
    assert second_trigger["alertname"] == "HighCPU"


# ---------- EC-1: list_alerts raises → swallow, no investigate / notify ----------


async def test_when_list_alerts_raises_the_system_swallows_exception_and_does_not_call_investigate_or_notify():
    """EC-1"""
    am = FakeAlertmanager(raise_exc=RuntimeError("boom"))
    investigate_fn = AsyncMock(return_value=_make_investigation_result())
    notify_fn = AsyncMock(return_value=None)
    poll_once = _build_poll_once(
        alertmanager=am,
        investigate_fn=investigate_fn,
        notify_fn=notify_fn,
        context=TriggerContext(),
        allowed_namespaces=("api",),
    )

    # Must NOT raise.
    await poll_once()

    assert investigate_fn.await_count == 0
    assert notify_fn.await_count == 0
    # list_alerts was still attempted exactly once.
    assert len(am.calls) == 1
