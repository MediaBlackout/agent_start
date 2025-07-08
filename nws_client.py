```python
"""
nws_client.py
Enterprise-grade asynchronous client for the National Weather Service (NWS) API.
"""

import asyncio
import json
import hashlib
import logging
import math
import socket
import aiohttp
import redis.asyncio as redis

from typing import Optional, Dict, Any, List, Tuple, Union
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta
from aiohttp import ClientSession, ClientTimeout
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from functools import wraps

### Constants ###
BASE_URL = "https://api.weather.gov"
RATE_LIMIT = 5  # Max 5 requests per second
CACHE_EXPIRATION = 300  # Default TTL in seconds

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

#############
# Utilities #
#############

class Units(Enum):
    US = "us"
    SI = "si"

class NWSClientError(Exception):
    pass

class RateLimitExceeded(NWSClientError):
    pass

class NotFoundError(NWSClientError):
    pass

class ServiceUnavailable(NWSClientError):
    pass

def cache_key(url: str, params: Dict[str, str] = None) -> str:
    if params:
        param_str = json.dumps(params, sort_keys=True)
        key = f"{url}?{param_str}"
    else:
        key = url
    return hashlib.sha256(key.encode("utf-8")).hexdigest()

def rate_limited(semaphore):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            async with semaphore:
                return await func(*args, **kwargs)
        return wrapper
    return decorator

##############
# Middleware #
##############

def standard_headers() -> Dict[str, str]:
    return {
        'User-Agent': 'nws-client/1.0 (+https://your-enterprise-domain.com)',
        'Accept': 'application/ld+json',
    }

def is_retryable_status(status_code):
    return status_code in (429, 500, 502, 503, 504)

##############
# HTTP Layer #
##############

class NWSHTTPClient:
    def __init__(self, redis_url: str = "redis://localhost", cache_enabled: bool = True):
        self.session: Optional[ClientSession] = None
        self.redis = redis.from_url(redis_url)
        self.cache_enabled = cache_enabled
        self.semaphore = asyncio.Semaphore(RATE_LIMIT)

    async def __aenter__(self):
        timeout = ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(timeout=timeout, headers=standard_headers(), connector=aiohttp.TCPConnector(limit=100))
        await self.redis.ping()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.session.close()
        await self.redis.close()

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError, socket.gaierror)),
        reraise=True
    )
    @rate_limited(semaphore=asyncio.Semaphore(RATE_LIMIT))
    async def get(self, endpoint: str, params: Dict[str, Any] = None, ttl: int = CACHE_EXPIRATION) -> Dict[str, Any]:
        url = f"{BASE_URL}{endpoint}"
        key = cache_key(url, params)

        if self.cache_enabled:
            cached = await self.redis.get(key)
            if cached:
                log.debug(f"[CACHE HIT] {url}")
                return json.loads(cached)

        response = await self.session.get(url, params=params)
        if response.status == 404:
            raise NotFoundError(f"Endpoint not found: {url}")
        elif response.status == 429:
            raise RateLimitExceeded("Rate limit exceeded.")
        elif is_retryable_status(response.status):
            raise NWSClientError(f"Retryable status: {response.status} for {url}")
        elif not response.ok:
            raise NWSClientError(f"HTTP error: {response.status}")

        data = await response.json()

        # Validate or transform data as needed...
        if self.cache_enabled:
            await self.redis.set(key, json.dumps(data), ex=ttl)

        return data

###############
# Main Client #
###############

class NWSClient:
    def __init__(self, http_client: NWSHTTPClient):
        self.http = http_client

    # 1. Points API
    async def get_point_info(self, lat: float, lon: float) -> Dict[str, Any]:
        return await self.http.get(f"/points/{lat},{lon}")

    # 2. Gridpoints API
    async def get_gridpoints(self, office: str, gridX: int, gridY: int) -> Dict[str, Any]:
        return await self.http.get(f"/gridpoints/{office}/{gridX},{gridY}")

    # 3. Forecast API
    async def get_forecast(self, office: str, gridX: int, gridY: int) -> Dict[str, Any]:
        return await self.http.get(f"/gridpoints/{office}/{gridX},{gridY}/forecast")

    # 4. Hourly Forecast API
    async def get_hourly_forecast(self, office: str, gridX: int, gridY: int) -> Dict[str, Any]:
        return await self.http.get(f"/gridpoints/{office}/{gridX},{gridY}/forecast/hourly")

    # 5. Stations
    async def list_stations(self, limit: int = 100) -> Dict[str, Any]:
        return await self.http.get("/stations", params={"limit": limit})

    async def get_station(self, station_id: str) -> Dict[str, Any]:
        return await self.http.get(f"/stations/{station_id}")

    # 6. Observations
    async def get_latest_observation(self, station_id: str) -> Dict[str, Any]:
        return await self.http.get(f"/stations/{station_id}/observations/latest")

    # 7. Products
    async def list_products(self) -> Dict[str, Any]:
        return await self.http.get("/products")

    async def get_product(self, product_id: str) -> Dict[str, Any]:
        return await self.http.get(f"/products/{product_id}")

    # 8. Offices
    async def list_offices(self) -> Dict[str, Any]:
        return await self.http.get("/offices")

    async def get_office(self, office_id: str) -> Dict[str, Any]:
        return await self.http.get(f"/offices/{office_id}")

    # 9. Zones
    async def list_zones(self) -> Dict[str, Any]:
        return await self.http.get("/zones")

    async def get_zone(self, zone_id: str) -> Dict[str, Any]:
        return await self.http.get(f"/zones/{zone_id}")

    # 10. Alerts
    async def get_alerts(self, status: str = "actual") -> Dict[str, Any]:
        return await self.http.get("/alerts", params={"status": status})

    # 11. Glossary
    async def get_glossary(self) -> Dict[str, Any]:
        return await self.http.get("/glossary")

    #####################
    # Advanced Features #
    #####################

    async def resolve_location(self, address: str) -> Tuple[float, float]:
        """
        Use a 3rd-party geocoder like OpenStreetMap. Placeholder here.
        """
        # In production, integrate with geopy or Google Geocoding
        raise NotImplementedError("Geocoding not implemented.")

    async def multi_forecast(self, locations: List[Tuple[float, float]]) -> List[Dict[str, Any]]:
        """
        Perform parallel forecast retrieval for multiple (lat, lon).
        """
        results = []

        async def get_forecast_coords(lat, lon):
            point = await self.get_point_info(lat, lon)
            props = point["properties"]
            forecast = await self.get_forecast(props["cwa"], props["gridX"], props["gridY"])
            return forecast

        tasks = [get_forecast_coords(lat, lon) for lat, lon in locations]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results

    async def monitor_alerts(self, callback):
        """
        Periodically poll alerts and invoke callback.
        """
        seen_ids = set()
        while True:
            alerts = await self.get_alerts()
            for alert in alerts.get("features", []):
                if alert["id"] not in seen_ids:
                    seen_ids.add(alert["id"])
                    await callback(alert)
            await asyncio.sleep(60)

    ####################
    # Cache Management #
    ####################

    async def invalidate_cache(self, url: str):
        key = cache_key(url)
        await self.http.redis.delete(key)

##################
# Test Example   #
##################

async def main():
    async with NWSHTTPClient() as http_client:
        nws = NWSClient(http_client)
        forecast = await nws.get_forecast("LWX", 97, 71)
        print(json.dumps(forecast, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
```
