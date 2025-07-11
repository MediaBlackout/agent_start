"""Command line interface for weather agent."""

from __future__ import annotations

import argparse
import asyncio

from .weather_agent import WeatherAgent


async def _run(zipcode: str) -> None:
    agent = WeatherAgent()
    data = await agent.get_forecast(zipcode)
    print(data)


def main(argv: list[str] | None = None, prog_name: str | None = None) -> None:
    parser = argparse.ArgumentParser(prog=prog_name)
    parser.add_argument("zipcode")
    args = parser.parse_args(argv)
    asyncio.run(_run(args.zipcode))


if __name__ == "__main__":
    main()
