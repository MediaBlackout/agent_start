"""Utility helpers."""
from __future__ import annotations

import os
import tempfile


def atomic_write(path: str, data: str) -> None:
    """Write data to path atomically."""
    dir_path = os.path.dirname(path) or "."
    with tempfile.NamedTemporaryFile("w", delete=False, dir=dir_path) as tf:
        tf.write(data)
        temp_name = tf.name
    os.replace(temp_name, path)
