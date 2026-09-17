import ast
from pathlib import Path


SCANNER = Path(__file__).resolve().parents[1] / "scanner_v5.py"


def _scanner_source():
    return SCANNER.read_text(encoding="utf-8")


def test_scanner_imports_direction_policy_helper():
    tree = ast.parse(_scanner_source())
    imports = [node for node in tree.body if isinstance(node, ast.ImportFrom)]

    assert any(
        node.module == "engines.direction_policy"
        and any(alias.name == "get_candidate_directions" for alias in node.names)
        for node in imports
    )


def test_scanner_delegates_candidate_direction_selection():
    tree = ast.parse(_scanner_source())
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "get_candidate_directions"
    ]

    assert len(calls) == 1
    call = calls[0]
    assert len(call.args) == 2
    assert isinstance(call.args[0], ast.Subscript)
    assert isinstance(call.args[1], ast.Call)


def test_scanner_has_no_inline_direction_policy_branch():
    source = _scanner_source()

    assert 'candidate_directions = ["LONG", "SHORT"]' not in source
    assert 'candidate_directions = [trend["direction"]]' not in source
