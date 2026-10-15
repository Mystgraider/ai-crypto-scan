"""Atomic JSON persistence helpers for scanner state files."""

import json
import os
import tempfile


def atomic_json_dump(path: str, data, *, indent=None, sort_keys=False) -> None:
    """Write JSON to a same-directory temporary file, then atomically replace path."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, temporary_path = tempfile.mkstemp(prefix=".state-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=indent, sort_keys=sort_keys)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass
        raise
