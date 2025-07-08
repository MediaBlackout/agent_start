import argparse
import asyncio
import json
import logging
import signal
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import psutil
import yaml
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.responses import StreamingResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import openai
import sse_starlette.sse as sse

# ------------------------------ Configuration ------------------------------

class Config:
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.load()

    def load(self):
        with open(self.config_path, 'r') as f:
            data = yaml.safe_load(f)
        # Example: parse essential config
        self.tool_path = data.get('tool_path', 'tools')
        self.api_keys = data.get('api_keys', {})
        self.port = data.get('port', 8000)
        self.log_level = data.get('log_level', 'INFO')
        self.cron_jobs = data.get('cron_jobs', [])

# ------------------------------ Logging Setup ------------------------------

def setup_logging(log_level: str):
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level.upper(), 'INFO'))
    handler = logging.StreamHandler()
    formatter = json.dumps({
        'timestamp': '%(asctime)s',
        'level': '%(levelname)s',
        'message': '%(message)s',
        'name': '%(name)s'
    })
    handler.setFormatter(logging.Formatter(formatter))
    logger.addHandler(handler)
    return logger

logger = None  # will initialize later

def get_logger(name: str):
    return logging.getLogger(name)

# ------------------------------ Tool Discovery & Registry ------------------------------

def discover_tools(tool_dir: Path) -> Dict[str, Callable]:
    tools = {}
    for script in tool_dir.glob('**/*.py'):
        module_name = script.stem
        spec = None
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(module_name, str(script))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            # Register callables
            for attr in dir(module):
                obj = getattr(module, attr)
                if callable(obj):
                    tools[attr] = obj
        except Exception as e:
            get_logger('ToolDiscovery').error(f'Failed to load {script}: {e}')
    return tools

# ------------------------------ OpenAI API Proxy ------------------------------

def stream_openai_response(messages: List[Dict[str, Any]]):
    # Wrap OpenAI call with retries and error handling
    import openai
    max_retries = 3
    delay = 2
    for attempt in range(max_retries):
        try:
            response = openai.ChatCompletion.create(
                model='gpt-4',
                messages=messages,
                stream=True
            )
            return response
        except openai.error.OpenAIError as e:
            get_logger('OpenAI').warning(f'OpenAI error: {e}, retrying...')
            time.sleep(delay)
    raise RuntimeError('Failed to get response from OpenAI after retries')

# ------------------------------ Parallel Tool Executor ------------------------------

async def execute_tool(fn: Callable, args: List[Any]) -> Any:
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: fn(*args))
    return result

# ------------------------------ Task Scheduler ------------------------------

class JobScheduler:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()

    def start(self):
        self.scheduler.start()

    def shutdown(self):
        self.scheduler.shutdown()

    def schedule_job(self, task_fn: Callable, cron: str):
        self.scheduler.add_job(task_fn, 'cron', **self.parse_cron(cron))

    @staticmethod
    def parse_cron(cron_str: str) -> Dict[str, Any]:
        # Simple parser for cron expression
        parts = cron_str.split()
        keys = ['minute', 'hour', 'day', 'month', 'day_of_week']
        return {k: v for k, v in zip(keys, parts)}

# ------------------------------ Health & Metrics ------------------------------

def get_health_snapshot() -> Dict[str, Any]:
    process = psutil.Process()
    cpu = psutil.cpu_percent()
    mem = psutil.virtual_memory()
    uptime = time.time() - psutil.boot_time()
    return {
        'cpu_percent': cpu,
        'virtual_memory': mem._asdict(),
        'process_uptime': uptime,
        'memory_info': process.memory_info()._asdict()
    }

# ------------------------------ Signal Handling & Shutdown ------------------------------

shutdown_event = asyncio.Event()

def setup_signal_handlers():
    def handle_signal(signum, frame):
        get_logger('Signal').info(f'Received signal {signum}, shutting down...')
        shutdown_event.set()
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

# ------------------------------ FastAPI Setup ------------------------------

app = FastAPI()
config = None
tools_registry: Dict[str, Callable] = {}
scheduler = JobScheduler()

@app.on_event("startup")
def startup_event():
    global config, tools_registry
    config = Config(Path.home() / 'orchestrator' / 'config.yaml')
    global logger
    logger = setup_logging(config.log_level)
    get_logger('Startup').info('Starting up...')
    # Discover tools
    tools_registry.update(discover_tools(Path(config.tool_path)))
    # Setup scheduled jobs
    for job in config.cron_jobs:
        cron_expr = job.get('schedule')
        task_name = job.get('task')
        # Assuming task is in tools
        task_fn = tools_registry.get(task_name)
        if task_fn:
            scheduler.schedule_job(lambda: run_in_threadpool(task_fn), cron_expr)
    scheduler.start()

@app.on_event("shutdown")
def shutdown_event():
    get_logger('Shutdown').info('Shutting down...')
    scheduler.shutdown()

# ------------------------------ CLI Commands ------------------------------

def parse_cli_args():
    parser = argparse.ArgumentParser(description='Workflow Orchestrator CLI')
    subparsers = parser.add_subparsers(dest='command')

    start_parser = subparsers.add_parser('start', help='Start the server')
    start_parser.add_argument('--port', type=int, default=8000, help='Port to run the server on')

    run_parser = subparsers.add_parser('run', help='Run a specific tool')
    run_parser.add_argument('tool_name', type=str, help='Name of the tool to run')
    run_parser.add_argument('args', nargs='*', help='Arguments for the tool')

    list_parser = subparsers.add_parser('list', help='List available tools')

    health_parser = subparsers.add_parser('health', help='Check system health')

    return parser.parse_args()

def start_server(port: int):
    import uvicorn
    uvicorn.run('workflow_orchestrator:app', host='0.0.0.0', port=port, reload=False)

def run_tool_cli(tool_name: str, args: List[str]):
    fn = tools_registry.get(tool_name)
    if not fn:
        print(f"Tool '{tool_name}' not found")
        return
    result = fn(*args)
    print(f"Result: {result}")

def list_tools():
    print("Available tools:")
    for name in tools_registry.keys():
        print(f"- {name}")

def health_check_cli():
    health = get_health_snapshot()
    print(json.dumps(health, indent=2))

# ------------------------------ API Endpoints ------------------------------

from fastapi import Path as FastAPIPath

@app.post('/function/{name}')
async def invoke_tool(name: str, request: Request):
    data = await request.json()
    args = data.get('args', [])
    fn = tools_registry.get(name)
    if not fn:
        return JSONResponse(status_code=404, content={'error': 'Tool not found'})
    result = await execute_tool(fn, args)
    return {'result': result}

@app.get('/agent-stream')
async def agent_stream(request: Request):
    # Accept messages and stream responses
    async def event_generator():
        # For demonstration, stream a dummy message
        message = {'message': 'Hello from agent!'}
        yield sse.SSEvent(data=json.dumps(message)).encode()
        await asyncio.sleep(1)
    return StreamingResponse(event_generator(), media_type='text/event-stream')

@app.get('/health')
async def health():
    health_data = get_health_snapshot()
    return JSONResponse(content=health_data)

# ------------------------------ Main Entry Point ------------------------------

def main():
    args = parse_cli_args()
    if args.command == 'start':
        start_server(args.port)
    elif args.command == 'run':
        run_tool_cli(args.tool_name, args.args)
    elif args.command == 'list':
        list_tools()
    elif args.command == 'health':
        health_check_cli()
    else:
        print('Unknown command. Use --help for options.')

if __name__ == '__main__':
    setup_signal_handlers()
    main()
