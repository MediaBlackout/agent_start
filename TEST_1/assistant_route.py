#!/usr/bin/env python3

"""
Interactive CLI helper for Agent_MBO3
-------------------------------------

Talk to the assistant (`Agent_MBO3`) using OpenAI's modern stateless Responses API.
Automatically handles tool use by calling local Flask endpoint functions.

Agent ID: asst_RSfaHeBbC3tcRPUwFvsQviVv
Toolbox URL: http://localhost:5000/function/<name>
"""

import openai
import requests
import uuid
import argparse
import json
import os

# Set your OpenAI API key or get it from environment
openai.api_key = os.getenv("OPENAI_API_KEY")

AGENT_ID = "asst_RSfaHeBbC3tcRPUwFvsQviVv"
FLASK_TOOLBOX_BASE_URL = "http://localhost:5000/function"

def execute_tool_call(tool_call):
    """
    Execute a tool call by sending the arguments to the Flask function server.
    """
    tool_name = tool_call["tool_call"]["function"]["name"]
    arguments = json.loads(tool_call["tool_call"]["function"]["arguments"])
    function_url = f"{FLASK_TOOLBOX_BASE_URL}/{tool_name}"

    try:
        response = requests.post(function_url, json=arguments)
        response.raise_for_status()
        return {
            "tool_call_id": tool_call["tool_call"]["id"],
            "output": response.json()
        }
    except requests.exceptions.RequestException as e:
        print(f"Error calling tool {tool_name}: {e}")
        return {
            "tool_call_id": tool_call["tool_call"]["id"],
            "output": {"error": str(e)}
        }

def send_prompt(prompt, previous_response_id=None, tool_outputs=None):
    """
    Send a prompt to the assistant via OpenAI Responses API.
    For follow-up calls, use previous_response_id and tool_outputs.
    """
    response = openai.beta.responses.create(
        agent_id=AGENT_ID,
        prompt=prompt,
        previous_response_id=previous_response_id,
        tool_outputs=tool_outputs or None
    )
    return response

def print_response(response):
    print("\nAssistant Response:")
    for output in response.output:
        if "text" in output:
            print(output["text"])
        else:
            print("[Non-text output received]")

def main():
    parser = argparse.ArgumentParser(description="Start interactive CLI session with Agent MBO3.")
    args = parser.parse_args()

    print(f"🤖 Starting Assistant CLI for Agent_MBO3 — Agent ID: {AGENT_ID}")
    print("Type your messages below. Type 'exit' to quit.\n")

    previous_response_id = None
    while True:
        user_input = input("You: ")
        if user_input.lower() in ["exit", "quit"]:
            print("Goodbye 👋")
            break

        # First request
        response = send_prompt(prompt=user_input, previous_response_id=previous_response_id)

        needs_tool_call = any(output.get("tool_call") for output in response.output)

        if not needs_tool_call:
            print_response(response)
            previous_response_id = response.id
            continue

        # Handle tool calls
        tool_outputs = []
        for tool_call in response.output:
            if "tool_call" in tool_call:
                tool_output = execute_tool_call(tool_call)
                tool_outputs.append(tool_output)

        # Send tool outputs back for final assistant reply
        followup_response = send_prompt(
            prompt=user_input,
            previous_response_id=response.id,
            tool_outputs=tool_outputs
        )

        print_response(followup_response)
        previous_response_id = followup_response.id


if __name__ == "__main__":
    main()
