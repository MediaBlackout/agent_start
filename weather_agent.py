import asyncio
import logging
from typing import List, Dict

from nws_client import NWSClient
from data_processor import WeatherProcessor
from response_formatter import ResponseFormatter


class WeatherAgent:
    """High level orchestrator for weather data retrieval and formatting."""

    def __init__(self, client: NWSClient | None = None,
                 processor: WeatherProcessor | None = None,
                 formatter: ResponseFormatter | None = None,
                 logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(__name__)
        self.client = client or NWSClient(logger=self.logger)
        self.processor = processor or WeatherProcessor(logger=self.logger)
        self.formatter = formatter or ResponseFormatter()

    async def get_current_weather(self, location: str) -> Dict:
        self.logger.info("Fetching weather for %s", location)
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
        data = await self.client.get_radar_url(location)
        return data

    async def batch_weather(self, locations: List[str]) -> List[Dict]:
        tasks = [self.get_current_weather(loc) for loc in locations]
        return await asyncio.gather(*tasks, return_exceptions=True)

    def start(self) -> None:
        """Placeholder for autonomous operation."""
        self.logger.info("WeatherAgent started")


def _test():
    agent = WeatherAgent()
    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(agent.get_current_weather("10001"))
    assert "properties" in result
    print("WeatherAgent test passed")


if __name__ == "__main__":
    _test()
