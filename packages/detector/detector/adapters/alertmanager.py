import httpx


class AlertmanagerAdapter:
    def __init__(self, base_url: str, client: httpx.AsyncClient) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client

    async def list_alerts(self, matchers: list[str] | None, state: str) -> str:
        params: dict[str, str | list[str]] = {
            "active": "true" if state == "active" else "false",
            "silenced": "true" if state == "silenced" else "false",
            "inhibited": "true" if state == "inhibited" else "false",
        }
        if matchers:
            params["filter"] = matchers
        resp = await self._client.get(
            f"{self._base_url}/api/v2/alerts",
            params=params,
        )
        resp.raise_for_status()
        return resp.text
