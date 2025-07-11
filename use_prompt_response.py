# use_prompt_response.py

"""CLI utility to interact with an OpenAI Prompt Response model."""

import argparse
import os
from openai import OpenAI

from openai_batch import build_jsonl, write_jsonl, create_batch


DEFAULT_PROMPT_ID = "pmpt_68702538ad2481958a150a6538d02ad90b7c27995ac44c36"
DEFAULT_PROMPT_VERSION = "1"


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Interact with a saved OpenAI prompt via the Responses API"
    )
    parser.add_argument(
        "-k",
        "--api-key",
        default=os.getenv("OPENAI_API_KEY"),
        help="OpenAI API key (defaults to OPENAI_API_KEY env variable)",
    )
    parser.add_argument(
        "--prompt-id",
        default=DEFAULT_PROMPT_ID,
        help="ID of the prompt to use",
    )
    parser.add_argument(
        "--prompt-version",
        default=DEFAULT_PROMPT_VERSION,
        help="Version of the prompt to use",
    )
    parser.add_argument(
        "--batch-jsonl",
        help="Submit a JSONL file of requests via the Batches API and exit",
    )
    parser.add_argument(
        "--batch-messages",
        help="Plain text file with one message per line to batch via Batches API",
    )
    return parser.parse_args()


def send_prompt(client: OpenAI, prompt_id: str, version: str, message: str):
    """Send a message to the prompt response API and return the response."""
    try:
        return client.responses.create(
            prompt={"id": prompt_id, "version": version},
            input=message,
        )
    except Exception as e:  # pragma: no cover - network/credential errors
        print(f"Error occurred while fetching response: {e}")
        return None


def format_output(response) -> str:
    """Extract readable text from the API response object."""
    if not response:
        return ""
    texts = []
    for item in getattr(response, "output", []):
        if getattr(item, "type", "") == "message":
            for chunk in getattr(item, "content", []):
                text = getattr(chunk, "text", None)
                if text:
                    texts.append(text)
    return "\n".join(texts)


def interactive_loop(client: OpenAI, prompt_id: str, version: str) -> None:
    """Run a REPL for sending messages to the prompt."""
    print("Enter messages. Type 'exit' or 'quit' to stop.")
    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            break
        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            break
        response = send_prompt(client, prompt_id, version, user_input)
        print("Assistant:")
        print(format_output(response))


def main() -> None:
    args = parse_args()
    if not args.api_key:
        raise SystemExit(
            "OpenAI API key must be provided via --api-key or OPENAI_API_KEY env"
        )

    client = OpenAI(api_key=args.api_key)

    if args.batch_jsonl or args.batch_messages:
        jsonl_path = args.batch_jsonl
        if args.batch_messages:
            with open(args.batch_messages, "r", encoding="utf-8") as f:
                messages = [line.strip() for line in f if line.strip()]
            jsonl_lines = build_jsonl(messages, args.prompt_id, args.prompt_version)
            jsonl_path = write_jsonl(jsonl_lines, "batch_requests.jsonl")
        batch = create_batch(client, jsonl_path)
        print(f"Created batch job: {getattr(batch, 'id', batch)}")
        return

    interactive_loop(client, args.prompt_id, args.prompt_version)

if __name__ == "__main__":
    main()
