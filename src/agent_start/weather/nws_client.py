"""Async client for the National Weather Service API."""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional

import httpx
import pgeocode

from ..config import get_settings


class NWSClient:
    BASE_URL = "https://api.weather.gov"

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger or logging.getLogger(__name__)
        self.settings = get_settings()
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, read=10.0),
            headers={"User-Agent": self.settings.weather_ua},
        )

    async def _get(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        url = endpoint if endpoint.startswith("http") else f"{self.BASE_URL}{endpoint}"
        delay = 1.0
        for _ in range(3):
            try:
                resp = await self.client.get(url, params=params)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                self.logger.warning("NWS request failed: %s", e)
                await asyncio.sleep(delay)
                delay *= 2
        raise RuntimeError(f"Failed to fetch {url}")

    def _geocode_zip(self, zip_code: str) -> Optional[tuple[float, float]]:
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


async def _test() -> None:
    client = NWSClient()
    data = await client.get_current_weather("10001")
    assert "properties" in data


if __name__ == "__main__":
    asyncio.run(_test())
