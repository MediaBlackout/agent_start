import json
import redis
from typing import Optional

class TaskQueue:
    """Simple FIFO queue backed by Redis."""

    def __init__(self, redis_client=None, key: str = "task_queue"):
        self.redis = redis_client or redis.Redis(host='localhost', port=6379, decode_responses=True)
        self.key = key

    def push(self, task: dict) -> None:
        self.redis.lpush(self.key, json.dumps(task))

    def pop(self, timeout: int = 0) -> Optional[dict]:
        if timeout:
            item = self.redis.brpop(self.key, timeout=timeout)
            if item:
                return json.loads(item[1])
            return None
        item = self.redis.rpop(self.key)
        return json.loads(item) if item else None
