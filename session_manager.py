import json
import redis

class SessionManager:
    """Simple Redis-backed session store."""

    def __init__(self, redis_client=None):
        self.redis = redis_client or redis.Redis(host='localhost', port=6379, decode_responses=True)

    def get(self, session_id: str):
        data = self.redis.get(f"session:{session_id}")
        return json.loads(data) if data else []

    def append(self, session_id: str, message: dict) -> None:
        history = self.get(session_id)
        history.append(message)
        self.redis.set(f"session:{session_id}", json.dumps(history))
