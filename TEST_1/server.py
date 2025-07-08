import os
import asyncio
import json
import logging
import importlib
import inspect
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import openai

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("server")

# Initialize OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    raise RuntimeError("OPENAI_API_KEY not set in environment variables.")

# Set up FastAPI app
app = FastAPI()

# Optional CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tool registry
TOOL_REGISTRY: Dict[str, Any] = {}


# Dynamically load all functions from the tools/ folder
def discover_tools():
    tools_path = Path(__file__).parent / "tools"
    if not tools_path.exists():
        logger.warning(f"Tools folder not found at: {tools_path}")
        return

    for py_file in tools_path.glob("*.py"):
        module_name = f"tools.{py_file.stem}"
        try:
            module = importlib.import_module(module_name)
            for name, obj in inspect.getmembers(module):
                if inspect.isfunction(obj) and not name.startswith("_"):
                    TOOL_REGISTRY[name] = obj
                    logger.info(f"Registered tool: {name}")
        except Exception as e:
            logger.error(f"Error loading module {module_name}: {e}")


@app.on_event("startup")
async def startup_event():
    discover_tools()


class FunctionCall(BaseModel):
    args: list = []
    kwargs: dict = {}


@app.post("/function/{name}")
async def call_function(name: str, call: FunctionCall):
    if name not in TOOL_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Function {name} not found")
    try:
        func = TOOL_REGISTRY[name]
        if inspect.iscoroutinefunction(func):
            result = await func(*call.args, **call.kwargs)
        else:
            # Run sync function in thread pool:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, func, *call.args, **call.kwargs)
        return JSONResponse(content=result)
    except Exception as e:
        logger.exception(f"Error calling function {name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class AgentStreamRequest(BaseModel):
    user_message: str
    context: list = []


@app.post("/agent-stream")
async def agent_stream(request: Request, body: AgentStreamRequest):
    async def event_generator():
        try:
            messages = body.context + [{"role": "user", "content": body.user_message}]
            tools_payload = [
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": func.__doc__ or "",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                k: {"type": "string"}  # Naive assumption
                                for k in inspect.signature(func).parameters
                            },
                            "required": list(inspect.signature(func).parameters),
                        }
                    }
                }
                for name, func in TOOL_REGISTRY.items()
            ]

            # Initiate streaming chat completion
            response = await openai.chat.completions.create(
                model="gpt-4",
                messages=messages,
                tools=tools_payload,
                stream=True
            )
            async for chunk in response:
                delta = chunk.choices[0].delta
                finish_reason = chunk.choices[0].finish_reason
                if hasattr(delta, "content") and delta.content:
                    yield f"data: {json.dumps({'role': 'assistant', 'content': delta.content})}\n\n"

                # Detect tool call
                if hasattr(delta, "tool_calls") and delta.tool_calls:
                    tasks = []
                    tool_outputs = []
                    for tool_call in delta.tool_calls:
                        function_name = tool_call.function.name
                        function_args = json.loads(tool_call.function.arguments)

                        if function_name not in TOOL_REGISTRY:
                            err_msg = f"Unknown tool: {function_name}"
                            logger.error(err_msg)
                            yield f"data: {json.dumps({'role': 'assistant', 'content': err_msg})}\n\n"
                            continue

                        async def invoke_tool(function_name=function_name, function_args=function_args):
                            try:
                                func = TOOL_REGISTRY[function_name]
                                if inspect.iscoroutinefunction(func):
                                    result = await func(**function_args)
                                else:
                                    loop = asyncio.get_event_loop()
                                    result = await loop.run_in_executor(None, func, **function_args)
                                return {
                                    "tool_call_id": tool_call.id,
                                    "name": function_name,
                                    "content": result,
                                }
                            except Exception as e:
                                logger.exception(f"Tool error: {function_name} - {e}")
                                return {
                                    "tool_call_id": tool_call.id,
                                    "name": function_name,
                                    "content": f"Error calling tool {function_name}: {str(e)}",
                                }

                        tasks.append(invoke_tool())

                    tool_outputs = await asyncio.gather(*tasks)

                    for output in tool_outputs:
                        msg = {
                            "tool_call_id": output["tool_call_id"],
                            "role": "function",
                            "name": output["name"],
                            "content": (
                                output["content"]
                                if isinstance(output["content"], str)
                                else json.dumps(output["content"])
                            ),
                        }
                        yield f"data: {json.dumps(msg)}\n\n"

                if finish_reason is not None:
                    break

            yield "event: end\ndata: [DONE]\n\n"

        except Exception as e:
            logger.exception("Error in SSE stream")
            yield f"event: error\ndata: {str(e)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")