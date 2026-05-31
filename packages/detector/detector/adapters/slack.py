from __future__ import annotations

import httpx


class SlackAdapter:
    def __init__(self, *, webhook_url: str, client: httpx.AsyncClient) -> None:
        self._webhook_url = webhook_url
        self._client = client

    async def send(self, message: str) -> None:
        resp = await self._client.post(self._webhook_url, json={"text": message})
        resp.raise_for_status()
