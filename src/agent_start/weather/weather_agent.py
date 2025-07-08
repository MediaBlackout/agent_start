"""High level orchestrator for weather retrieval."""
from __future__ import annotations

import asyncio
from typing import List, Dict, Optional

import structlog

from .nws_client import NWSClient
from .data_processor import WeatherProcessor
from .response_formatter import ResponseFormatter

logger = structlog.get_logger(__name__)


class WeatherAgent:
    def __init__(self, client: Optional[NWSClient] = None) -> None:
        self.client = client or NWSClient()
        self.processor = WeatherProcessor()
        self.formatter = ResponseFormatter()

    async def get_current_weather(self, location: str) -> Dict:
        raw = await self.client.get_current_weather(location)
        processed = self.processor.process_current(raw)
        return self.formatter.format_current(processed)

    async def get_forecast(self, location: str) -> Dict:
        raw = await self.client.get_forecast(location)
        processed = self.processor.process_forecast(raw)
        return self.formatter.format_forecast(processed)

    async def get_alerts(self, location: str) -> Dict:
        data = await self.client.get_alerts(location)
        return self.formatter.format_alerts(data)

    async def get_radar_url(self, location: str) -> Dict:
        return await self.client.get_radar_url(location)

    async def batch_weather(self, locations: List[str]) -> List[Dict]:
        tasks = [self.get_current_weather(loc) for loc in locations]
        return await asyncio.gather(*tasks)
