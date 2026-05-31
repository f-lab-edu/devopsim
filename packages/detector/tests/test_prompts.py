import pytest

from detector.prompts import load_cluster_context, render_prompt


def test_render_prompt_system_substitutes_cluster_context_available_tools_and_policy() -> None:
    result = render_prompt(
        "system",
        cluster_context="X",
        available_tools="Y",
        policy="Z",
    )
    assert "X" in result
    assert "Y" in result
    assert "Z" in result
    assert "{cluster_context}" not in result
    assert "{available_tools}" not in result
    assert "{policy}" not in result


def test_render_prompt_investigation_substitutes_trigger_summary_and_runbook_body() -> None:
    result = render_prompt(
        "investigation",
        trigger_summary="X",
        runbook_body="Y",
    )
    assert "X" in result
    assert "Y" in result
    assert "{trigger_summary}" not in result
    assert "{runbook_body}" not in result


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
        render_prompt("system", cluster_context="X")
