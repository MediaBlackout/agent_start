"""Formatting helpers for weather data."""

from __future__ import annotations

from typing import Dict

import structlog

logger = structlog.get_logger(__name__)


class ResponseFormatter:
    def format_current(self, data: Dict) -> Dict:
        logger.debug("format_current")
        return data

    def format_forecast(self, data: Dict) -> Dict:
        logger.debug("format_forecast")
        return data

    def format_alerts(self, data: Dict) -> Dict:
        logger.debug("format_alerts")
        return data


def _test() -> None:
    f = ResponseFormatter()
    assert f.format_current({"a": 1}) == {"a": 1}
    assert f.format_forecast({"b": 2}) == {"b": 2}
    assert f.format_alerts({"c": 3}) == {"c": 3}


if __name__ == "__main__":  # pragma: no cover - manual testing
    _test()
