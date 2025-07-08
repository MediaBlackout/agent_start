import asyncio
import logging
from typing import Dict

import urllib.request
import urllib.parse
import json


class NWSClient:
    """Minimal async client for the National Weather Service API."""

    BASE_URL = "https://api.weather.gov"

    def __init__(self, config: Dict | None = None, logger: logging.Logger | None = None):
        self.config = config or {}
        self.logger = logger or logging.getLogger(__name__)

    async def _get(self, endpoint: str, params: Dict | None = None) -> Dict:
        url = f"{self.BASE_URL}{endpoint}"

        def _request():
            self.logger.debug("Requesting %s", url)
            if params:
                query = urllib.parse.urlencode(params)
                full_url = f"{url}?{query}"
            else:
                full_url = url
            with urllib.request.urlopen(full_url, timeout=10) as resp:
                data = resp.read()
                return json.loads(data)

        return await asyncio.to_thread(_request)

    async def get_current_weather(self, location: str) -> Dict:
        # Placeholder using sample data
        return {"location": location, "temperature": 20, "description": "Clear"}

    async def get_forecast(self, location: str) -> Dict:
        return {"location": location, "forecast": "Sunny"}

    async def get_alerts(self, location: str) -> Dict:
        return {"location": location, "alerts": []}


def _test():
    client = NWSClient()
    loop = asyncio.get_event_loop()
    data = loop.run_until_complete(client.get_current_weather("Test"))
    assert "location" in data
    print("NWSClient test passed")


if __name__ == "__main__":
    _test()
