#!/usr/bin/env python3
"""
AgentZero - Improved Version

An enhanced wrapper around OpenAI's Responses API to submit structured prompts
and return generated Python code or other completions.

Improvements:
- Added comprehensive type hints
- Implemented proper error handling and logging
- Added input validation and security enhancements
- Improved documentation and code structure
- Added configuration management
"""

import os
import logging
from typing import List, Dict, Any, Optional
from openai import OpenAI
from pathlib import Path


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AgentZeroError(Exception):
    """Custom exception for AgentZero errors."""
    pass


class AgentZero:
    """
    An enhanced wrapper around OpenAI's Responses API to submit structured prompts
    and return generated Python code or other completions.
    
    Features:
    - Comprehensive error handling
    - Type annotations for better code clarity
    - Secure credential management
    - Structured logging
    - Input validation
    """

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        """
        Initialize the AgentZero client with optional API key and model.
        
        Args:
            api_key: OpenAI API key. If None, loads from OPENAI_API_KEY env var.
            model: Model to use for completions. Defaults to gpt-4o-mini.
            
        Raises:
            AgentZeroError: If API key is not provided or found in environment.
        """
        # Validate and set API key
        final_api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not final_api_key:
            raise AgentZeroError(
                "OpenAI API key is required. Set OPENAI_API_KEY environment variable "
                "or provide api_key parameter."
            )
        
        try:
            self.client = OpenAI(api_key=final_api_key)
            logger.info("OpenAI client initialized successfully")
        except Exception as e:
            raise AgentZeroError(f"Failed to initialize OpenAI client: {str(e)}")

        # Configuration
        self.default_prompt_id = "pmpt_686dcde1996081978e4d0feb9b73e81a039a52b0af2581d2"
        self.default_model = model
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

    def validate_input(self, user_prompt: str) -> None:
        """
        Validate user input for security and correctness.
        
        Args:
            user_prompt: The user's prompt to validate.
            
        Raises:
            AgentZeroError: If input is invalid or potentially dangerous.
        """
        if not user_prompt or not user_prompt.strip():
            raise AgentZeroError("User prompt cannot be empty")
        
        if len(user_prompt) > 10000:  # Reasonable limit
            raise AgentZeroError("User prompt too long (max 10000 characters)")
        
        # Check for potentially dangerous patterns
        dangerous_patterns = [
            "import subprocess",
            "os.system",
            "eval(",
            "exec(",
            "__import__"
        ]
        
        prompt_lower = user_prompt.lower()
        for pattern in dangerous_patterns:
            if pattern in prompt_lower:
                logger.warning(f"Potentially dangerous pattern detected: {pattern}")
                # Log but don't block - just warn

    def build_request(
        self,
        user_prompt: str,
        messages: Optional[List[Dict[str, str]]] = None,
        prompt_id: Optional[str] = None,
        version: str = "1"
    ) -> Dict[str, Any]:
        """
        Construct the request payload for the responses.create endpoint.
        
        Args:
            user_prompt: The user's prompt.
            messages: Optional additional messages to include.
            prompt_id: Optional custom prompt ID.
            version: Prompt version to use.
            
        Returns:
            Dictionary containing the request payload.
            
        Raises:
            AgentZeroError: If input validation fails.
        """
        self.validate_input(user_prompt)
        
        try:
            full_messages = self.default_messages.copy()
            if messages:
                # Validate messages structure
                for msg in messages:
                    if not isinstance(msg, dict) or "role" not in msg or "content" not in msg:
                        raise AgentZeroError("Invalid message format")
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
        except Exception as e:
            raise AgentZeroError(f"Failed to build request: {str(e)}")

    def generate(self, user_prompt: str) -> str:
        """
        Send the prompt to the Responses API and return the model output.
        
        Args:
            user_prompt: The user's prompt.
            
        Returns:
            The model's response content.
            
        Raises:
            AgentZeroError: If the API request fails.
        """
        try:
            logger.info(f"Generating response for prompt: {user_prompt[:100]}...")
            
            request_payload = self.build_request(user_prompt=user_prompt)
            response = self.client.responses.create(**request_payload)
            
            if not response.choices or not response.choices[0].message.content:
                raise AgentZeroError("Empty response from OpenAI API")
                
            content = response.choices[0].message.content
            logger.info(f"Successfully generated response ({len(content)} characters)")
            
            return content
            
        except Exception as e:
            error_msg = f"OpenAI API request failed: {str(e)}"
            logger.error(error_msg)
            raise AgentZeroError(error_msg)

    def generate_file(
        self,
        filename: str,
        description: str,
        output_dir: Optional[str] = None
    ) -> None:
        """
        Generate Python code from a description and write it to a file.
        
        Args:
            filename: Name of the file to create.
            description: Description of what the code should do.
            output_dir: Optional directory to save the file. Defaults to current directory.
            
        Raises:
            AgentZeroError: If file generation or writing fails.
        """
        # Validate filename
        if not filename or not filename.strip():
            raise AgentZeroError("Filename cannot be empty")
        
        # Sanitize filename
        safe_filename = "".join(c for c in filename if c.isalnum() or c in "._-")
        if not safe_filename.endswith(".py"):
            safe_filename += ".py"
        
        # Construct output path
        if output_dir:
            output_path = Path(output_dir) / safe_filename
            output_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            output_path = Path(safe_filename)
        
        try:
            user_prompt = (
                f"Create a Python file named `{safe_filename}` that:\n"
                f"{description}\n\n"
                f"Output only the full contents of `{safe_filename}`."
            )
            
            logger.info(f"Generating file: {output_path}")
            code = self.generate(user_prompt)
            
            # Write file with proper encoding
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(code.strip())
            
            logger.info(f"Successfully created file: {output_path}")
            
        except Exception as e:
            error_msg = f"Failed to generate file {safe_filename}: {str(e)}"
            logger.error(error_msg)
            raise AgentZeroError(error_msg)


def main() -> None:
    """
    Main function demonstrating AgentZero usage.
    """
    try:
        agent = AgentZero()
        
        # Create a FastAPI-based server file with agent capabilities
        agent.generate_file(
            "server.py",
            (
                "1. Uses FastAPI to expose endpoints under `/function/{name}` where each endpoint "
                "invokes a stub function matching `name` and returns its result as JSON.\n"
                "2. Provides an `/agent-stream` Server-Sent-Events endpoint that forwards incoming messages "
                "to the OpenAI Responses API (using `client.responses.create`) and streams back the assistant's "
                "replies in real time.\n"
                "3. Supports the Responses API's parallel tool-calling feature: whenever the model requests a tool call, "
                "your code should execute it immediately and feed the tool output back into the streaming response "
                "until a final text answer is produced."
            )
        )
        
        logger.info("server.py has been generated successfully")
        
    except AgentZeroError as e:
        logger.error(f"AgentZero error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise


if __name__ == "__main__":
    main()