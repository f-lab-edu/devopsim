import re
import time

import httpx

_DURATION_RE = re.compile(r"^(\d+)(s|m|h|d)$")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def _parse_duration_seconds(value: str) -> int:
    m = _DURATION_RE.match(value)
    if not m:
        raise ValueError(f"Invalid duration format: {value!r}")
    amount, unit = m.groups()
    return int(amount) * _UNIT_SECONDS[unit]


class LokiAdapter:
    def __init__(self, base_url: str, client: httpx.AsyncClient) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client

    async def query(self, query: str) -> str:
        resp = await self._client.get(
            f"{self._base_url}/loki/api/v1/query",
            params={"query": query},
        )
        resp.raise_for_status()
        return resp.text

    async def query_range(self, query: str, lookback: str, limit: int, direction: str) -> str:
        lookback_s = _parse_duration_seconds(lookback)
        end_ns = time.time_ns()
        start_ns = end_ns - lookback_s * 10**9
        resp = await self._client.get(
            f"{self._base_url}/loki/api/v1/query_range",
            params={
                "query": query,
                "start": str(start_ns),
                "end": str(end_ns),
                "limit": str(limit),
                "direction": direction,
            },
        )
        resp.raise_for_status()
        return resp.text
