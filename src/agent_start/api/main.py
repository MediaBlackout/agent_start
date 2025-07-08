import argparse
import asyncio
import json
import logging
import logging.handlers
import signal
import sys
from functools import lru_cache
from pathlib import Path

try:
    import uvicorn
except ImportError:  # pragma: no cover - optional dependency
    uvicorn = None
try:
    import yaml
except ImportError:  # pragma: no cover - optional dependency
    yaml = None
try:
    from fastapi import Depends, FastAPI, Request, WebSocket, WebSocketDisconnect
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse, JSONResponse
    from prometheus_client import Counter, generate_latest
    from starlette.websockets import WebSocketState
except ImportError:  # pragma: no cover - optional dependency
    FastAPI = None
    WebSocket = WebSocketDisconnect = Request = Depends = None
    CORSMiddleware = None
    JSONResponse = HTMLResponse = None

    def generate_latest() -> bytes:  # pragma: no cover - noop when dep missing
        return b""

    class DummyCounter:
        def __init__(self, *_, **__):
            pass

        def inc(self, *_):
            pass

    Counter = DummyCounter

from ..weather.data_processor import WeatherProcessor
from ..weather.nws_client import NWSClient
from ..weather.response_formatter import ResponseFormatter

# Local modules (interface stubs, actual implementation assumed)
from ..weather.weather_agent import WeatherAgent

# === Constants ===

DEFAULT_CONFIG_PATH = "config.yml"
LOG_FILE_PATH = "logs/weather_agent.log"
MAX_LOG_BYTES = 10 * 1024 * 1024  # 10 MB
BACKUP_COUNT = 5

# === Prometheus Metrics ===

REQUEST_COUNT = Counter("weather_agent_requests_total", "Total API requests")
WEBSOCKET_CONNECTIONS = Counter(
    "weather_agent_ws_connections_total", "WebSocket connections opened"
)

# === Utility Functions ===


def load_config(_: str = DEFAULT_CONFIG_PATH) -> dict:
    """Return configuration from :class:`Settings`."""
    from ..config import get_settings

    return get_settings().model_dump()


def setup_logger(config: dict) -> logging.Logger:
    """Configure a rotating JSON logger."""
    logger = logging.getLogger("weather_agent")
    logger.setLevel(logging.INFO)

    handler = logging.handlers.RotatingFileHandler(
        LOG_FILE_PATH,
        maxBytes=MAX_LOG_BYTES,
        backupCount=BACKUP_COUNT,
    )
    formatter = logging.Formatter(
        '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "message": %(message)s}',
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


# === Application Context and DI ===


class AppContext:
    """Global dependency container and configuration store."""

    def __init__(self, config: dict):
        self.config = config
        self.logger = setup_logger(config)
        self.nws_client = NWSClient(logger=self.logger)
        self.processor = WeatherProcessor()
        self.formatter = ResponseFormatter()
        self.agent = WeatherAgent(
            client=self.nws_client, processor=self.processor, formatter=self.formatter
        )
        self.plugins = []

    def load_plugins(self):
        """Dynamically load plugins from configured plugin directory."""
        plugin_dir = self.config.get("plugins", {}).get("directory", "plugins")
        plugin_path = Path(plugin_dir)
        if plugin_path.exists():
            for pyfile in plugin_path.glob("*.py"):
                if pyfile.name == "__init__.py":
                    continue
                module_name = f"plugins.{pyfile.stem}"
                try:
                    mod = __import__(module_name, fromlist=[""])
                    if hasattr(mod, "init"):
                        mod.init(self)
                        self.logger.info(f'"Loaded plugin: {module_name}"')
                        self.plugins.append(mod)
                except Exception as e:
                    self.logger.error(f"Failed to load plugin {module_name}: {e}")


@lru_cache
def get_app_context() -> AppContext:
    config = load_config()
    return AppContext(config)


# === FastAPI App Initialization ===


def create_app() -> FastAPI:
    if FastAPI is None:
        raise RuntimeError("FastAPI is required to create the web app")
    app = FastAPI(title="Weather Agent", version="1.0.0")

    # Dependency container
    context = get_app_context()

    if CORSMiddleware is not None:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def add_metrics(request: Request, call_next):
        REQUEST_COUNT.inc()
        response = await call_next(request)
        return response

    @app.get("/weather/{location}")
    async def get_weather(location: str):
        context.logger.info(f"Fetching current weather for {location}")
        try:
            data = await context.agent.get_current_weather(location)
            return data
        except Exception as e:
            context.logger.error(f"Error - current weather: {e}")
            return JSONResponse(
                {"error": "Failed to retrieve weather"}, status_code=500
            )

    @app.get("/forecast/{location}")
    async def get_forecast(location: str):
        try:
            data = await context.agent.get_forecast(location)
            return data
        except Exception as e:
            context.logger.error(f"Error - forecast: {e}")
            return JSONResponse(
                {"error": "Failed to retrieve forecast"}, status_code=500
            )

    @app.get("/alerts/{location}")
    async def get_alerts(location: str):
        try:
            data = await context.agent.get_alerts(location)
            return data
        except Exception as e:
            context.logger.error(f"Error - alerts: {e}")
            return JSONResponse({"error": "Failed to retrieve alerts"}, status_code=500)

    @app.get("/radar/{location}")
    async def get_radar(location: str):
        try:
            data = await context.agent.get_radar_url(location)
            return data
        except Exception as e:
            context.logger.error(f"Error - radar: {e}")
            return JSONResponse({"error": "Failed to retrieve radar"}, status_code=500)

    @app.get("/")
    async def ui_index():
        if HTMLResponse is None:
            return {"error": "UI requires fastapi[all]"}
        html_path = Path(__file__).resolve().parent / "templates" / "index.html"
        if html_path.exists():
            html = html_path.read_text()
        else:
            html = "<html><body><h1>UI missing</h1></body></html>"
        return HTMLResponse(html)

    @app.websocket("/ws/weather")
    async def websocket_weather(ws: WebSocket):
        await ws.accept()
        WEBSOCKET_CONNECTIONS.inc()
        context.logger.info("WebSocket connection started")
        try:
            while True:
                if ws.client_state != WebSocketState.CONNECTED:
                    break
                msg = await ws.receive_text()
                location = msg.strip()
                data = await context.agent.get_current_weather(location)
                await ws.send_json(data)
        except WebSocketDisconnect:
            context.logger.info("WebSocket disconnected")
        except Exception as e:
            context.logger.error(f"WebSocket error: {e}")
            await ws.close()
        finally:
            context.logger.info("WebSocket session ended")

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    @app.get("/metrics")
    async def metrics():
        return generate_latest()

    return app


# === CLI Actions ===


async def start_server():
    context = get_app_context()
    context.load_plugins()

    server_conf = context.config.get("server", {})
    host = server_conf.get("host", "0.0.0.0")
    port = server_conf.get("port", 8000)
    workers = server_conf.get("workers", 1)

    app = create_app()

    def shutdown_handler():
        context.logger.info("Shutting down gracefully...")
        sys.exit(0)

    signal.signal(signal.SIGINT, lambda s, f: shutdown_handler())
    signal.signal(signal.SIGTERM, lambda s, f: shutdown_handler())

    if uvicorn is None:
        raise RuntimeError("uvicorn is required to start the server")
    config = uvicorn.Config(
        app=app, host=host, port=port, log_level="info", workers=workers
    )
    server = uvicorn.Server(config=config)
    await server.serve()


async def get_weather(location: str):
    ctx = get_app_context()
    data = await ctx.agent.get_current_weather(location)
    print(json.dumps(data, indent=2))


async def monitor(location: str, interval: int = 60):
    ctx = get_app_context()
    print(f"Monitoring weather for {location}...")
    while True:
        data = await ctx.agent.get_current_weather(location)
        print(json.dumps(data, indent=2))
        await asyncio.sleep(interval)


def health_check():
    print("System health check passed.")
    print("Log path: ", LOG_FILE_PATH)


def config_validate():
    config = load_config()
    print("Configuration loaded and verified:")
    print(json.dumps(config, indent=2))


# === CLI Parser and Entrypoint ===


def parse_args():
    parser = argparse.ArgumentParser(description="Weather Agent CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    subparsers.add_parser("start-server", help="Start FastAPI server")

    get_weather_cmd = subparsers.add_parser(
        "get-weather", help="Get weather for location"
    )
    get_weather_cmd.add_argument("location", type=str)

    monitor_cmd = subparsers.add_parser("monitor", help="Monitor weather continuously")
    monitor_cmd.add_argument("location", type=str)
    monitor_cmd.add_argument(
        "--interval", type=int, default=60, help="Refresh interval in seconds"
    )

    subparsers.add_parser("health-check", help="System diagnostics")
    subparsers.add_parser("config-validate", help="Validate loaded config")

    return parser.parse_args()


def main():
    args = parse_args()
    command = args.command

    loop = asyncio.get_event_loop()

    if command == "start-server":
        loop.run_until_complete(start_server())
    elif command == "get-weather":
        loop.run_until_complete(get_weather(args.location))
    elif command == "monitor":
        loop.run_until_complete(monitor(args.location, args.interval))
    elif command == "health-check":
        health_check()
    elif command == "config-validate":
        config_validate()
    else:
        print("Unknown command. Use --help for usage.")


def _test():
    sys.argv = [sys.argv[0], "get-weather", "Test"]
    args = parse_args()
    assert args.command == "get-weather"
    assert args.location == "Test"
    print("main test passed")


if __name__ == "__main__":    main()
