"""Weather data processing utilities."""
from __future__ import annotations

import structlog
from typing import Dict

logger = structlog.get_logger(__name__)


class WeatherProcessor:
    def process_current(self, data: Dict) -> Dict:
        logger.debug("process_current")
        return data

    def process_forecast(self, data: Dict) -> Dict:
        logger.debug("process_forecast")
        return data
