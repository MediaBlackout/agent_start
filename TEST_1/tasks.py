from dataclasses import dataclass
from enum import Enum, auto
from typing import Any


class OrchestratorState(Enum):
    IDLE = auto()
    PLANNING = auto()
    EXECUTING = auto()
    REVIEWING = auto()
    COMPLETE = auto()


@dataclass
class Task:
    agent: str
    action: str
    requires_approval: bool = False
    result: Any | None = None
