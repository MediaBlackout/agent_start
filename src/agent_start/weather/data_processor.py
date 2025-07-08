"""Weather data processing utilities."""

from __future__ import annotations

from typing import Dict

import structlog

logger = structlog.get_logger(__name__)


class WeatherProcessor:
    def process_current(self, data: Dict) -> Dict:
        logger.debug("process_current")
        return data

    def process_forecast(self, data: Dict) -> Dict:
        logger.debug("process_forecast")
        return data


def _test() -> None:
    p = WeatherProcessor()
    assert p.process_current({"a": 1}) == {"a": 1}
    assert p.process_forecast({"b": 2}) == {"b": 2}


if __name__ == "__main__":  # pragma: no cover - manual testing
    _test()
