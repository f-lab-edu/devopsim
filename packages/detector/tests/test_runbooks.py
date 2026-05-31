from pathlib import Path

import pytest

from detector.adapters.runbooks import RunbookFilesystemAdapter
from detector.agent.tools import RunbookPort, make_fetch_runbook_tool


class FakeRunbook:
    def __init__(
        self,
        fetch_response: str = "stub",
        list_response: str = "- stub: stub",
        raise_exc: Exception | None = None,
    ) -> None:
        self.calls: list[tuple] = []
        self._fetch_response = fetch_response
        self._list_response = list_response
        self._raise_exc = raise_exc

    async def fetch(self, name: str) -> str:
        self.calls.append(("fetch", name))
        if self._raise_exc is not None:
            raise self._raise_exc
        return self._fetch_response

    async def list_runbooks(self) -> str:
        self.calls.append(("list_runbooks",))
        if self._raise_exc is not None:
            raise self._raise_exc
        return self._list_response


# ---------- Port behavior (AC-1 ~ AC-2, EC-1 ~ EC-2) ----------


async def test_fetch_runbook_handler_calls_port_fetch_with_name_and_returns_response():
    """AC-1"""
    rb: RunbookPort = FakeRunbook(fetch_response="# pod-oom-killed\n\nbody")
    tool = make_fetch_runbook_tool(rb)
    out = await tool.run({"name": "pod-oom-killed"})
    assert out == "# pod-oom-killed\n\nbody"
    assert rb.calls == [("fetch", "pod-oom-killed")]


async def test_fetch_runbook_tool_anthropic_schema_shape():
    """AC-2"""
    tool = make_fetch_runbook_tool(FakeRunbook())
    schema = tool.to_anthropic_schema()
    assert schema["name"] == "fetch_runbook"
    assert schema["input_schema"]["required"] == ["name"]


async def test_fetch_runbook_missing_name_returns_validation_error_and_no_port_call():
    """EC-1"""
    rb = FakeRunbook()
    tool = make_fetch_runbook_tool(rb)
    out = await tool.run({})
    assert "Error: ValidationError" in out
    assert rb.calls == []


async def test_fetch_runbook_port_exception_is_wrapped_in_error_string():
    """EC-2"""
    rb = FakeRunbook(raise_exc=RuntimeError("boom"))
    tool = make_fetch_runbook_tool(rb)
    out = await tool.run({"name": "pod-oom-killed"})
    assert out.startswith("Error: ")
    assert "RuntimeError" in out
    assert "boom" in out


# ---------- Adapter behavior (AC-3 ~ AC-5) ----------


RUNBOOK_NAMES = [
    "pod-oom-killed",
    "pod-crashloopbackoff",
    "alert-db-pool-waiting",
    "alert-high-cpu",
    "alert-high-error-rate",
]


@pytest.fixture
def runbook_root(tmp_path: Path) -> Path:
    catalog = (
        "[\n"
        + ",\n".join(f'  {{"name": "{name}", "description": "stub description for {name}"}}' for name in RUNBOOK_NAMES)
        + "\n]\n"
    )
    (tmp_path / "catalog.json").write_text(catalog)
    (tmp_path / "_default.md").write_text("# _default\n\n## Goal\n\nTBD\n")
    for name in RUNBOOK_NAMES:
        (tmp_path / f"{name}.md").write_text(f"# {name}\n\n## Goal\n\nTBD\n")
    return tmp_path


@pytest.mark.parametrize(
    "name",
    [
        "pod-oom-killed",
        "pod-crashloopbackoff",
        "alert-db-pool-waiting",
        "alert-high-cpu",
        "alert-high-error-rate",
    ],
)
async def test_runbook_filesystem_adapter_fetch_returns_non_empty_body_for_known_name(runbook_root: Path, name: str):
    """AC-3"""
    adapter = RunbookFilesystemAdapter(root_dir=runbook_root)
    body = await adapter.fetch(name)
    assert isinstance(body, str)
    assert body.strip() != ""


async def test_runbook_filesystem_adapter_fetch_unknown_name_returns_default_body(
    runbook_root: Path,
):
    """AC-4"""
    adapter = RunbookFilesystemAdapter(root_dir=runbook_root)
    body = await adapter.fetch("unknown_name")
    assert isinstance(body, str)
    assert body.strip() != ""
    default_body = (runbook_root / "_default.md").read_text()
    assert body == default_body


async def test_runbook_filesystem_adapter_list_runbooks_returns_bullet_list_with_all_names(
    runbook_root: Path,
):
    """AC-5"""
    adapter = RunbookFilesystemAdapter(root_dir=runbook_root)
    out = await adapter.list_runbooks()
    assert isinstance(out, str)
    for name in RUNBOOK_NAMES:
        # 각 줄 `- <name>: <description>` 패턴
        matching = [line for line in out.splitlines() if line.startswith(f"- {name}:")]
        assert matching, f"missing bullet for {name} in: {out!r}"
        # description 비어있지 않음
        line = matching[0]
        _, _, desc = line.partition(":")
        assert desc.strip() != ""
