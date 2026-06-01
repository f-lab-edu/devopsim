import pytest

from detector.prompts import load_cluster_context, render_prompt


def test_render_prompt_system_substitutes_cluster_context() -> None:
    # system 프롬프트는 한국어 강제 정책을 직접 포함하므로 cluster_context 하나만 받는다.
    result = render_prompt("system", cluster_context="X")
    assert "X" in result
    assert "{cluster_context}" not in result


def test_render_prompt_investigation_substitutes_trigger_summary_and_runbook_catalog() -> None:
    # 초기 user message는 trigger + runbook catalog만 — runbook body는 fetch_runbook tool로 받는다.
    result = render_prompt(
        "investigation",
        trigger_summary="X",
        runbook_catalog="Y",
    )
    assert "X" in result
    assert "Y" in result
    assert "{trigger_summary}" not in result
    assert "{runbook_catalog}" not in result


def test_render_prompt_slack_report_substitutes_rca_actions_taken_and_links() -> None:
    result = render_prompt(
        "slack_report",
        rca="X",
        actions_taken="Y",
        links="Z",
    )
    assert "X" in result
    assert "Y" in result
    assert "Z" in result
    assert "{rca}" not in result
    assert "{actions_taken}" not in result
    assert "{links}" not in result


def test_load_cluster_context_returns_non_empty_string() -> None:
    result = load_cluster_context()
    assert isinstance(result, str)
    assert result.strip() != ""


def test_render_prompt_nonexistent_name_raises_file_not_found_error() -> None:
    with pytest.raises(FileNotFoundError):
        render_prompt("nonexistent_name")


def test_render_prompt_missing_required_placeholder_raises_key_error() -> None:
    with pytest.raises(KeyError):
        # investigation은 trigger_summary + runbook_catalog 둘 다 필요 — runbook_catalog 누락
        render_prompt("investigation", trigger_summary="X")
