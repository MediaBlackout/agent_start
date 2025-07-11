"""Simple TODO CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

from .utils import atomic_write

TASKS_FILE = Path("todo.json")


class TodoList:
    def __init__(self, path: Path = TASKS_FILE) -> None:
        self.path = path
        self.tasks: List[dict] = []
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            self.tasks = json.loads(self.path.read_text())
        else:
            self.tasks = []

    def _save(self) -> None:
        atomic_write(self.path, json.dumps(self.tasks, indent=2))

    def add(self, text: str) -> None:
        self.tasks.append({"text": text, "done": False})
        self._save()

    def list(self) -> List[dict]:
        return self.tasks

    def complete(self, idx: int) -> None:
        if 0 <= idx < len(self.tasks):
            self.tasks[idx]["done"] = True
            self._save()


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    add_p = sub.add_parser("add")
    add_p.add_argument("text")
    sub.add_parser("list")
    comp_p = sub.add_parser("complete")
    comp_p.add_argument("idx", type=int)
    args = parser.parse_args()
    todo = TodoList()
    if args.cmd == "add":
        todo.add(args.text)
    elif args.cmd == "list":
        for i, t in enumerate(todo.list(), 1):
            mark = "✓" if t["done"] else " "
            print(f"[{mark}] {i}: {t['text']}")
    elif args.cmd == "complete":
        todo.complete(args.idx - 1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
