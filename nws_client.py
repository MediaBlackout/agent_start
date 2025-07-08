import asyncio
import logging
from typing import Dict

import urllib.request
import urllib.parse
import json
import pgeocode


class NWSClient:
    """Minimal async client for the National Weather Service API."""

    BASE_URL = "https://api.weather.gov"

    def __init__(self, config: Dict | None = None, logger: logging.Logger | None = None):
        self.config = config or {}
        self.logger = logger or logging.getLogger(__name__)

    async def _get(self, endpoint: str, params: Dict | None = None) -> Dict:
        if endpoint.startswith("http"):
            url = endpoint
        else:
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

    def _geocode_zip(self, zip_code: str) -> tuple[float, float] | None:
        nomi = pgeocode.Nominatim("us")
        result = nomi.query_postal_code(zip_code)
        if result is None or result.latitude is None or result.longitude is None:
            return None
        return float(result.latitude), float(result.longitude)

    async def get_current_weather(self, location: str) -> Dict:
        coords = self._geocode_zip(location)
        if not coords:
            return {"error": "Invalid location"}
        lat, lon = coords
        points = await self._get(f"/points/{lat},{lon}")
        stations_url = points["properties"].get("observationStations")
        if not stations_url:
            return {"error": "No station"}
        stations = await self._get(stations_url)
        first = stations["features"][0]["properties"]["stationIdentifier"]
        obs = await self._get(f"/stations/{first}/observations/latest")
        return obs

    async def get_forecast(self, location: str) -> Dict:
        coords = self._geocode_zip(location)
        if not coords:
            return {"error": "Invalid location"}
        lat, lon = coords
        points = await self._get(f"/points/{lat},{lon}")
        forecast_url = points["properties"].get("forecast")
        if not forecast_url:
            return {"error": "No forecast"}
        forecast = await self._get(forecast_url)
        return forecast

    async def get_alerts(self, location: str) -> Dict:
        coords = self._geocode_zip(location)
        if not coords:
            return {"error": "Invalid location"}
        lat, lon = coords
        alerts = await self._get("/alerts/active", {"point": f"{lat},{lon}"})
        return alerts

    async def get_radar_url(self, location: str) -> Dict:
        coords = self._geocode_zip(location)
        if not coords:
            return {"error": "Invalid location"}
        lat, lon = coords
        points = await self._get(f"/points/{lat},{lon}")
        radar = points["properties"].get("radarStation")
        if not radar:
            return {"error": "No radar"}
        url = f"https://radar.weather.gov/ridge/standard/{radar}_0.gif"
        return {"url": url}


def _test():
    client = NWSClient()
    loop = asyncio.get_event_loop()
    data = loop.run_until_complete(client.get_current_weather("10001"))
    assert "properties" in data
    print("NWSClient test passed")


if __name__ == "__main__":
    _test()
