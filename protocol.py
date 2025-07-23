"
protocol.py

Defines the message protocol used between the server and clients
for the Texas Hold'em Poker game.
All messages are sent as JSON strings via WebSockets.

Each message must contain:
- "type": A string identifying the message type
- "data": A dictionary with message-specific fields
"""

from typing import Dict, Any
import json


def encode_message(message_type: str, data: Dict[str, Any]) -> str:
    """
    Encode a message dictionary to JSON string for transmission.

    :param message_type: Type of the message (join, action, game_state, etc.)
    :param data: The message payload
    :return: Serialized JSON string
    """
    return json.dumps({
        "type": message_type,
        "data": data
    })


def decode_message(message: str) -> Dict[str, Any]:
    """
    Decode a received message from JSON string to dictionary.

    :param message: JSON string received
    :return: Dictionary with type and data
    :raises: json.JSONDecodeError if invalid JSON
    """
    return json.loads(message)