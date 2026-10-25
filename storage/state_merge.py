"""Fail-safe three-way text merge primitive for scanner state-save research.

This helper is intentionally not wired into production workflow yet. It provides
a deterministic primitive: preserve non-overlapping changes and reject conflicts
instead of silently overwriting another writer's updates.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


class StateMergeConflict(RuntimeError):
    """Raised when concurrent state changes overlap and cannot be merged safely."""


def merge_text(base: str, latest: str, generated: str) -> str:
    """Merge generated changes onto latest using base as the common ancestor.

    Arguments:
        base: File content at the writer's starting commit.
        latest: Current remote/main file content.
        generated: File content after the writer's local job changes.

    Raises:
        StateMergeConflict: If edits overlap.
        RuntimeError: If git merge-file is unavailable or fails unexpectedly.
    """
    with tempfile.TemporaryDirectory(prefix="state-merge-") as directory:
        root = Path(directory)
        current_path = root / "latest.txt"
        base_path = root / "base.txt"
        generated_path = root / "generated.txt"
        current_path.write_text(latest, encoding="utf-8")
        base_path.write_text(base, encoding="utf-8")
        generated_path.write_text(generated, encoding="utf-8")

        result = subprocess.run(
            [
                "git", "merge-file", "--stdout",
                str(current_path), str(base_path), str(generated_path),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        if result.returncode == 0:
            return result.stdout
        if result.returncode == 1:
            raise StateMergeConflict(
                "Concurrent edits overlap; refusing to discard either writer's changes."
            )
        raise RuntimeError(
            "git merge-file failed unexpectedly: "
            + (result.stderr.strip() or f"exit code {result.returncode}")
        )
