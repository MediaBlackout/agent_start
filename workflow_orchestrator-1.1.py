#!/usr/bin/env python3
"""
AI Workflow Orchestrator Platform

A production-ready AI workflow orchestration system that provides:
- Dynamic tool discovery and execution
- OpenAI API integration with streaming
- Real-time SSE communication
- Parallel task execution
- Scheduled job management
- Health monitoring and metrics
- Graceful shutdown handling

Dependencies: fastapi, sse-starlette, pyyaml, openai, apscheduler, psutil, uvicorn

Usage:
    python workflow_orchestrator.py start-server --port 8000
    python workflow_orchestrator.py run-task --name "data_sync"
    python workflow_orchestrator.py list-tools
    python workflow_orchestrator.py health-check
"""

# === Imports === #
import os, sys, json, yaml, argparse, logging, asyncio, signal, time, threading, queue
import importlib.util, inspect, traceback
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, Union
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed

import psutil
import openai
import uvicorn

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from sse_starlette.sse import EventSourceResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# === Constants and Globals === #
DEFAULT_CONFIG_PATH = os.path.expanduser("~/orchestrator/config.yaml")
FALLBACK_CONFIG_PATH = "./config.yaml"
CONFIG: Dict[str, Any] = {}
TOOL_REGISTRY: Dict[str, Callable] = {}
EXECUTOR = ThreadPoolExecutor(max_workers=16)
SCHEDULER = AsyncIOScheduler()
APP = FastAPI()
LOG = logging.getLogger("orchestrator")

# === Configuration Management === #
class ConfigManager:
    @staticmethod
    def load_config(path: str = "") -> Dict[str, Any]:
        path = path or DEFAULT_CONFIG_PATH
        final_path = Path(path)
        if not final_path.exists():
            final_path = Path(FALLBACK_CONFIG_PATH)
        with open(final_path, "r") as f:
            cfg = yaml.safe_load(f)
        return ConfigManager.merge_env_vars(cfg)

    @staticmethod
    def merge_env_vars(cfg: Dict[str, Any]) -> Dict[str, Any]:
        def replace_env(val):
            if isinstance(val, str) and val.startswith("${") and val.endswith("}"):
                return os.getenv(val[2:-1], "")
            return val

        def recurse(obj):
            if isinstance(obj, dict):
                return {k: recurse(replace_env(v)) for k,v in obj.items()}
            return obj

        return recurse(cfg)

    @staticmethod
    def validate_config(cfg: Dict[str, Any]):
        keys = ["server", "openai", "tools", "logging"]
        for k in keys:
            if k not in cfg:
                raise ValueError(f"Missing configuration section: {k}")

# === Logging Setup === #
class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_record = {
            "level": record.levelname,
            "timestamp": self.formatTime(record),
            "message": record.getMessage(),
            "name": record.name,
        }
        if record.exc_info:
            log_record["error"] = self.formatException(record.exc_info)
        return json.dumps(log_record)

class LoggerSetup:
    @staticmethod
    def setup_logging(cfg: Dict[str, Any]):
        log_cfg = cfg.get("logging", {})
        level = getattr(logging, log_cfg.get("level", "INFO").upper(), logging.INFO)
        log_path = log_cfg.get("file", "./logs/orchestrator.log")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        handler = logging.FileHandler(log_path)
        handler.setFormatter(JSONFormatter())
        LOG.setLevel(level)
        LOG.addHandler(handler)

# === CLI Manager === #
class CLIManager:
    @staticmethod
    def setup_argparse():
        parser = argparse.ArgumentParser(description="AI Workflow Orchestrator CLI")
        sub = parser.add_subparsers(dest="command", required=True)

        srv = sub.add_parser("start-server")
        srv.add_argument("--port", type=int, default=8000)
        srv.add_argument("--host", type=str, default="0.0.0.0")
        srv.add_argument("--verbose", action="store_true")

        run = sub.add_parser("run-task")
        run.add_argument("--name", required=True)
        run.add_argument("--params", type=str, default="{}")

        sub.add_parser("list-tools")
        sub.add_parser("health-check")

        val = sub.add_parser("validate-config")
        val.add_argument("--config", type=str, default="")

        return parser

    @staticmethod
    def handle_cli_commands(args, config):
        if args.command == "start-server":
            LOG.info("Starting server...")
            uvicorn.run("workflow_orchestrator:APP", host=args.host, port=args.port, reload=False)
        elif args.command == "run-task":
            task = TOOL_REGISTRY.get(args.name)
            if not task:
                print("Tool not found.")
                return
            params = json.loads(args.params)
            result = asyncio.run(task(**params))
            print(json.dumps(result, indent=2))
        elif args.command == "list-tools":
            print(json.dumps(list(TOOL_REGISTRY.keys()), indent=2))
        elif args.command == "health-check":
            ok, metrics = HealthChecker.system_health()
            print(json.dumps(metrics, indent=2))
        elif args.command == "validate-config":
            try:
                cfg = ConfigManager.load_config(args.config)
                ConfigManager.validate_config(cfg)
                print("Configuration is valid.")
            except Exception as e:
                print(f"Config Error: {str(e)}")

# === Tool Registry === #
class ToolRegistry:
    @staticmethod
    def discover_tools(directory: str):
        path = Path(directory)
        if not path.exists():
            return
        for py in path.glob("*.py"):
            try:
                spec = importlib.util.spec_from_file_location(py.stem, py)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                for name, obj in inspect.getmembers(mod):
                    if callable(obj) and getattr(obj, "_is_tool", False):
                        TOOL_REGISTRY[py.stem] = obj
            except Exception as e:
                LOG.warning(f"Failed to load tool {py}: {e}")

    @staticmethod
    def register_tool(func):
        func._is_tool = True
        return func

# === OpenAI API Proxy === #
class OpenAIProxy:
    @staticmethod
    async def handle_request(payload: Dict[str, Any]):
        try:
            completion = await openai.ChatCompletion.acreate(**payload)
            return completion
        except Exception as e:
            LOG.error(f"OpenAI error: {e}")
            raise

# === SSE & Streaming === #
class SSEManager:
    @staticmethod
    async def sse_endpoint():
        async def event_generator():
            while True:
                yield {"event": "ping", "data": json.dumps({"status": "ok"})}
                await asyncio.sleep(2)
        return EventSourceResponse(event_generator())

# === Tool Execution === #
class ToolExecutor:
    @staticmethod
    async def execute_tool_async(name: str, params: Dict[str, Any]):
        if name not in TOOL_REGISTRY:
            raise ValueError("Tool not found")
        func = TOOL_REGISTRY[name]
        return await func(**params)

# === Task Scheduler === #
class JobManager:
    LOG = logging.getLogger("scheduler")
    JOBS: Dict[str, Any] = {}

    @staticmethod
    def schedule_task(name: str, cron: str, params: dict):
        def wrapper():
            try:
                asyncio.run(ToolExecutor.execute_tool_async(name, params))
            except Exception as e:
                LOG.error(f"Scheduled task error: {str(e)}")
        SCHEDULER.add_job(wrapper, "cron", **cron)
        JobManager.JOBS[name] = cron

# === Health Checker === #
class HealthChecker:
    @staticmethod
    def system_health() -> (bool, Dict[str, Any]):
        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        healthy = cpu < 80 and mem.percent < 85
        return healthy, {
            "cpu": cpu,
            "memory": mem.percent,
            "disk": disk.percent
        }

# === Shutdown Handling === #
class ShutdownHandler:
    SHUTDOWN = False

    @staticmethod
    def setup():
        def handler(signum, frame):
            LOG.info("Shutdown signal received.")
            ShutdownHandler.SHUTDOWN = True
            EXECUTOR.shutdown(wait=False)
            SCHEDULER.shutdown(wait=False)

        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)

# === FastAPI Setup === #
def create_app(config: Dict[str, Any]) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_credentials=True,
        allow_methods=["*"], allow_headers=["*"]
    )

    @app.get("/health")
    async def health():
        ok, data = HealthChecker.system_health()
        if not ok:
            raise HTTPException(status_code=500, detail=data)
        return {"status": "ok", "metrics": data}

    @app.get("/tools")
    async def list_tools():
        return {"tools": list(TOOL_REGISTRY.keys())}

    @app.post("/function/{name}")
    async def run_tool(name: str, req: Request):
        try:
            body = await req.json()
            result = await ToolExecutor.execute_tool_async(name, body)
            return {"result": result}
        except Exception as e:
            LOG.error(f"ExecutionError: {e}")
            raise HTTPException(500, detail=str(e))

    @app.get("/metrics")
    async def metrics():
        _, data = HealthChecker.system_health()
        return data

    @app.get("/agent-stream")
    async def stream():
        return await SSEManager.sse_endpoint()

    @app.post("/schedule")
    async def schedule(body: Dict[str, Any]):
        name = body["name"]
        cron = body["cron"]
        params = body.get("params", {})
        JobManager.schedule_task(name, cron, params)
        return {"status": "scheduled"}

    @app.get("/jobs")
    async def jobs():
        return JobManager.JOBS

    return app

# === Main Entry Point === #
if __name__ == "__main__":
    try:
        CONFIG = ConfigManager.load_config()
        ConfigManager.validate_config(CONFIG)
        LoggerSetup.setup_logging(CONFIG)
        ToolRegistry.discover_tools(CONFIG["tools"]["directory"])
        SCHEDULER.start()
        ShutdownHandler.setup()

        parser = CLIManager.setup_argparse()
        args = parser.parse_args()
        CLIManager.handle_cli_commands(args, CONFIG)

    except Exception as e:
        LOG.error(f"Startup Error: {e}")
        sys.exit(1)

# === App Exposed for Uvicorn === #
CONFIG = ConfigManager.load_config()
LoggerSetup.setup_logging(CONFIG)
ToolRegistry.discover_tools(CONFIG.get("tools", {}).get("directory", "./tools"))
APP = create_app(CONFIG)
SCHEDULER.start()
ShutdownHandler.setup()
