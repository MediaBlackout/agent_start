import os
import json
import asyncio
import importlib
import inspect
import logging
from typing import Dict, Any, List, Callable

from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel
import openai

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load OpenAI API Key
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    raise EnvironmentError("Missing OPENAI_API_KEY environment variable.")

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------------
# Dynamic Tool Loader
# -------------------------------------------------------------
TOOLS_REGISTRY: Dict[str, Callable] = {}

def load_tools():
    tools_package = "tools"
    try:
        package = importlib.import_module(tools_package)
        for finder, name, ispkg in getattr(package, "__path__")._path_importer_cache[package.__path__[0]].iter_modules():
            module_name = f"{tools_package}.{name}"
            module = importlib.import_module(module_name)

            for func_name, obj in inspect.getmembers(module, inspect.isfunction):
                full_name = func_name
                if full_name in TOOLS_REGISTRY:
                    logger.warning(f"Function name '{full_name}' already registered. Skipping duplicate.")
                    continue
                TOOLS_REGISTRY[full_name] = obj
                logger.info(f"Registered tool function: {full_name}")
    except Exception as e:
        logger.error(f"Error loading tools: {e}")

load_tools()

# -------------------------------------------------------------
# Function Execution Endpoint
# -------------------------------------------------------------
class FunctionCall(BaseModel):
    args: List[Any] = []
    kwargs: Dict[str, Any] = {}

@app.post("/function/{name}")
async def call_function(name: str, body: FunctionCall):
    func = TOOLS_REGISTRY.get(name)
    if not func:
        raise HTTPException(status_code=404, detail=f"Function '{name}' not found.")

    try:
        if inspect.iscoroutinefunction(func):
            result = await func(*body.args, **body.kwargs)
        else:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, lambda: func(*body.args, **body.kwargs))
        return JSONResponse(content={"result": result})
    except Exception as e:
        logger.exception(f"Error executing function '{name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------------------------------------------
# /agent-stream SSE Endpoint
# -------------------------------------------------------------
class AgentStreamRequest(BaseModel):
    user_message: str
    context: List[Dict[str, Any]]

async def stream_agent_response(user_message: str, context: List[Dict[str, Any]]):
    """
    SSE stream back OpenAI responses and inject tool results into flow.
    """
    message_history = context + [{"role": "user", "content": user_message}]
    functions_schema = []

    for name, func in TOOLS_REGISTRY.items():
        # Optional: Generate OpenAI-compatible function schema if desired.
        functions_schema.append({
            "name": name,
            "description": func.__doc__ or "",
            "parameters": {
                "type": "object",
                "properties": {},  # Could introspect from signature.__annotations__ for better UX
            },
        })

    # Begin OpenAI stream
    try:
        response = await openai.ChatCompletion.acreate(
            model="gpt-4",
            messages=message_history,
            functions=functions_schema if functions_schema else None,
            stream=True
        )
    except Exception as e:
        logger.exception(f"OpenAI streaming failed: {e}")
        yield f"data: [ERROR] {str(e)}\n\n"
        return

    function_call_buffer = {}
    async for chunk in response:
        choices = chunk.get("choices", [])
        if not choices:
            continue

        delta = choices[0]["delta"]
        finish_reason = choices[0].get("finish_reason")

        if delta.get("function_call"):
            name = delta["function_call"].get("name")
            arguments = delta["function_call"].get("arguments", "")
            if name not in function_call_buffer:
                function_call_buffer[name] = arguments
            else:
                function_call_buffer[name] += arguments
            continue  # Don't emit function_call delta - handled separately below

        if delta.get("content"):
            yield f"data: {json.dumps({'role': 'assistant', 'content': delta['content']})}\n\n"

        # Handle end of function_call and parallel tool execution
        if finish_reason == "function_call" and function_call_buffer:
            for name, arg_str in function_call_buffer.items():
                try:
                    parsed_args = json.loads(arg_str)
                except Exception as e:
                    logger.exception(f"Invalid arguments for function '{name}': {e}")
                    yield f"data: [FUNCTION_ERROR] Failed to parse arguments for {name}\n\n"
                    continue

                async def run_and_stream(name, parsed_args):
                    endpoint = f"/function/{name}"
                    try:
                        result = await call_function(name, FunctionCall(**parsed_args))
                        emit = {"role": "tool", "name": name, "content": result.json()}
                        yield f"data: {json.dumps(emit)}\n\n"
                    except HTTPException as he:
                        yield f"data: [FUNCTION_ERROR] {he.detail}\n\n"
                    except Exception as e:
                        logger.exception(f"Error in tool '{name}': {e}")
                        yield f"data: [FUNCTION_ERROR] {str(e)}\n\n"

                # Stream result into pipeline
                async for tool_chunk in run_and_stream(name, parsed_args):
                    yield tool_chunk

            function_call_buffer.clear()  # Reset buffer and continue loop
            return  # Reinvoke OpenAI to continue chain, or handle loop here.

    yield "event: end\ndata: [DONE]\n\n"

@app.post("/agent-stream")
async def agent_stream(request: AgentStreamRequest):
    return StreamingResponse(
        stream_agent_response(request.user_message, request.context),
        media_type="text/event-stream"
    )
