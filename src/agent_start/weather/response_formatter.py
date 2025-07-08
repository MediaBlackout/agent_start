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
