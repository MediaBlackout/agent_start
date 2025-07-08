import logging
from typing import Dict


class WeatherProcessor:
    """Simple data processor for weather payloads."""

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(__name__)

    def process_current(self, data: Dict) -> Dict:
        self.logger.debug("Processing current weather data")
        return data

    def process_forecast(self, data: Dict) -> Dict:
        self.logger.debug("Processing forecast data")
        return data


def _test():
    proc = WeatherProcessor()
    assert proc.process_current({"a": 1})["a"] == 1
    assert proc.process_forecast({"b": 2})["b"] == 2
    print("WeatherProcessor test passed")


if __name__ == "__main__":
    _test()
