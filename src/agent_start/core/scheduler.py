"""Simple in-memory task scheduler."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable, List


class Priority(Enum):
    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()


@dataclass
class Task:
    description: str
    action: Callable[[], None]
    priority: Priority = Priority.MEDIUM
    done: bool = False


class Scheduler:
    def __init__(self) -> None:
        self.tasks: List[Task] = []

    def add(self, task: Task) -> None:
        self.tasks.append(task)
        self.tasks.sort(key=lambda t: t.priority.value)

    def run(self) -> None:
        for task in list(self.tasks):
            if task.done:
                continue
            try:
                task.action()
                task.done = True
            finally:
                pass
