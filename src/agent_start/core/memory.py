"""Persistent memory backed by SQLite."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable


class Memory:
    def __init__(self, path: str = "memory.db") -> None:
        self.path = Path(path)
        self.conn = sqlite3.connect(self.path)
        self._init()

    def _init(self) -> None:
        cur = self.conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS log (id INTEGER PRIMARY KEY AUTOINCREMENT, event TEXT)"
        )
        self.conn.commit()

    def log(self, event: str) -> None:
        cur = self.conn.cursor()
        cur.execute("INSERT INTO log(event) VALUES(?)", (event,))
        self.conn.commit()

    def all(self) -> Iterable[str]:
        cur = self.conn.cursor()
        for row in cur.execute("SELECT event FROM log"):
            yield row[0]
