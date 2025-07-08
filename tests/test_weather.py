import asyncio

from agent_start.weather.weather_agent import WeatherAgent


class DummyClient:
    async def get_current_weather(self, loc):
        return {"temp": 1}

    async def get_forecast(self, loc):
        return {"forecast": "sunny"}

    async def get_alerts(self, loc):
        return {}

    async def get_radar_url(self, loc):
        return {"url": "http://example.com"}


def test_agent_current():
    agent = WeatherAgent(client=DummyClient())
    result = asyncio.run(agent.get_current_weather("00000"))
    assert result["temp"] == 1
