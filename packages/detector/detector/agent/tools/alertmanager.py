from typing import Literal, Protocol

from pydantic import BaseModel, Field

from .base import Tool


class AlertmanagerPort(Protocol):
    async def list_alerts(self, matchers: list[str] | None, state: str) -> str: ...


class AlertmanagerListAlertsInput(BaseModel):
    matchers: list[str] | None = Field(
        default=None,
        description="Optional Alertmanager matchers (e.g. ['severity=critical']).",
    )
    state: Literal["active", "silenced", "inhibited"] = Field(
        default="active",
        description="Alert state filter: active, silenced, or inhibited.",
    )

    model_config = {"json_schema_extra": {"required": []}}


def make_alertmanager_list_alerts_tool(am: AlertmanagerPort) -> Tool:
    async def handler(input: AlertmanagerListAlertsInput) -> str:
        return await am.list_alerts(input.matchers, input.state)

    return Tool(
        name="alertmanager_list_alerts",
        description="List alerts from Alertmanager filtered by matchers and state.",
        input_model=AlertmanagerListAlertsInput,
        handler=handler,
    )
