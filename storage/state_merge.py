"""Fail-safe line-based three-way text merge primitive for research only."""
from __future__ import annotations

import difflib


class StateMergeConflict(RuntimeError):
    """Raised when concurrent state changes overlap and cannot be merged safely."""


def _edits(base_lines: list[str], changed_lines: list[str]):
    matcher = difflib.SequenceMatcher(a=base_lines, b=changed_lines, autojunk=False)
    return [
        (i1, i2, changed_lines[j1:j2])
        for tag, i1, i2, j1, j2 in matcher.get_opcodes()
        if tag != "equal"
    ]


def merge_text(base: str, latest: str, generated: str) -> str:
    """Merge two versions against a common base, preserving non-overlapping edits.

    Raises StateMergeConflict when the writers changed overlapping base ranges.
    """
    if latest == generated:
        return latest
    if latest == base:
        return generated
    if generated == base:
        return latest

    base_lines = base.splitlines(keepends=True)
    latest_lines = latest.splitlines(keepends=True)
    generated_lines = generated.splitlines(keepends=True)

    latest_edits = _edits(base_lines, latest_lines)
    generated_edits = _edits(base_lines, generated_lines)
    combined = list(latest_edits)

    for edit in generated_edits:
        start, end, replacement = edit
        duplicate = False
        for other_start, other_end, other_replacement in latest_edits:
            if (start, end, replacement) == (other_start, other_end, other_replacement):
                duplicate = True
                break

            # Two insertions at the same position conflict unless identical.
            if start == end and other_start == other_end:
                overlaps = start == other_start
            # An insertion conflicts when it falls inside or at the boundary of
            # a range another writer replaces/deletes.
            elif start == end:
                overlaps = other_start <= start <= other_end
            elif other_start == other_end:
                overlaps = start <= other_start <= end
            else:
                overlaps = max(start, other_start) < min(end, other_end)

            if overlaps:
                raise StateMergeConflict(
                    "Concurrent edits overlap; refusing to discard either writer's changes."
                )
        if not duplicate:
            combined.append(edit)

    merged_lines = list(base_lines)
    for start, end, replacement in sorted(combined, key=lambda item: (item[0], item[1]), reverse=True):
        merged_lines[start:end] = replacement
    return "".join(merged_lines)
