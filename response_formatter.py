import json
import logging
from typing import Dict


class ResponseFormatter:
    """Format weather data for display or transmission."""

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(__name__)

    def format_current(self, data: Dict) -> Dict:
        self.logger.debug("Formatting current weather")
        return data

    def format_forecast(self, data: Dict) -> Dict:
        self.logger.debug("Formatting forecast")
        return data

    def format_alerts(self, data: Dict) -> Dict:
        self.logger.debug("Formatting alerts")
        return data


def _test():
    fmt = ResponseFormatter()
    assert "temp" in fmt.format_current({"temp": 1})
    print("ResponseFormatter test passed")


if __name__ == "__main__":
    _test()
