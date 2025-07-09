import os
from openai import OpenAI
from typing import List, Dict, Any, Optional


class AgentZero:
    """
    A wrapper around OpenAI's Responses API to submit a structured prompt
    and return generated Python code or other completions.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initializes the AgentZero client with optional API key.
        """
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))

        # Initialize the default message prompt.
        self.default_prompt_id = "pmpt_686dcde1996081978e4d0feb9b73e81a039a52b0af2581d2"
        self.default_model = "gpt-4o-mini"
        self.default_messages = [
            {
                "role": "system",
                "content": (
                    "You are a code generator. When I ask for a Python file, "
                    "output only the complete .py file contents—no markdown, "
                    "no explanations, no commentary."
                )
            }
        ]

    def build_request(
        self,
        user_prompt: str,
        messages: Optional[List[Dict[str, str]]] = None,
        prompt_id: Optional[str] = None,
        version: str = "1"
    ) -> Dict[str, Any]:
        """
        Constructs the request payload to the responses.create endpoint.
        """
        full_messages = self.default_messages.copy()
        if messages:
            full_messages.extend(messages)
        else:
            full_messages.append({
                "role": "user",
                "content": user_prompt
            })

        return {
            "prompt": {
                "id": prompt_id or self.default_prompt_id,
                "version": version,
                "messages": full_messages
            },
            "model": self.default_model
        }

    def generate(self, user_prompt: str) -> str:
        """
        Sends the prompt to the Responses API and returns the model output.
        """
        try:
            request_payload = self.build_request(user_prompt=user_prompt)
            response = self.client.responses.create(**request_payload)
            return response.choices[0].message.content
        except Exception as e:
            raise RuntimeError(f"OpenAI API failed: {str(e)}")

    def generate_file(
        self,
        filename: str,
        description: str
    ) -> None:
        """
        Generates Python code from a description and writes it to a file.
        """
        user_prompt = f"Create a Python file named `{filename}` that:\n{description}\n\nOutput only the full contents of `{filename}`."
        code = self.generate(user_prompt)

        with open(filename, "w", encoding="utf-8") as f:
            f.write(code.strip())


# Example usage:
if __name__ == "__main__":
    agent = AgentZero()

    # Create a FastAPI-based server file with agent capabilities
    agent.generate_file(
        "server.py",
        (
            "1. Uses FastAPI to expose endpoints under `/function/{name}` where each endpoint "
            "invokes a stub function matching `name` and returns its result as JSON.\n"
            "2. Provides an `/agent-stream` Server-Sent-Events endpoint that forwards incoming messages "
            "to the OpenAI Responses API (using `client.responses.create`) and streams back the assistant’s "
            "replies in real time.\n"
            "3. Supports the Responses API’s parallel tool-calling feature: whenever the model requests a tool call, "
            "your code should execute it immediately and feed the tool output back into the streaming response "
            "until a final text answer is produced."
        )
    )

    print("server.py has been generated.")
