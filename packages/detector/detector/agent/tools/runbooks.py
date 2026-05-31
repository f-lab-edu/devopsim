from typing import Protocol

from pydantic import BaseModel, Field

from .base import Tool


class RunbookPort(Protocol):
    async def fetch(self, name: str) -> str: ...

    async def list_runbooks(self) -> str: ...


class FetchRunbookInput(BaseModel):
    name: str = Field(..., description="Runbook name (e.g. 'pod-oom-killed').")


def make_fetch_runbook_tool(rb: RunbookPort) -> Tool:
    async def handler(input: FetchRunbookInput) -> str:
        return await rb.fetch(input.name)

    return Tool(
        name="fetch_runbook",
        description="Fetch a runbook markdown body by name.",
        input_model=FetchRunbookInput,
        handler=handler,
    )
