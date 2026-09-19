import ast
from pathlib import Path

from engines.support_resistance import SupportResistanceEngine


SCANNER = Path(__file__).resolve().parents[1] / "scanner_v5.py"


def _scanner_source():
    return SCANNER.read_text(encoding="utf-8")


def test_short_ceiling_is_direction_specific():
    engine = SupportResistanceEngine()
    no_ceiling = {
        "support_dist_pct": 1.0,
        "resistance_dist_pct": None,
    }
    with_ceiling = {
        "support_dist_pct": None,
        "resistance_dist_pct": 4.0,
    }

    assert engine.short_has_ceiling(no_ceiling, 5.0) is False
    assert engine.short_has_ceiling(with_ceiling, 5.0) is True
    assert engine.short_has_ceiling(with_ceiling, 3.0) is False


def test_sr_bonus_is_directional_not_global():
    engine = SupportResistanceEngine()

    long_levels = {
        "support_dist_pct": 1.0,
        "resistance_dist_pct": None,
    }
    short_levels = {
        "support_dist_pct": None,
        "resistance_dist_pct": 1.0,
    }

    assert engine.score_bonus("LONG", long_levels) == 15.0
    assert engine.score_bonus("SHORT", long_levels) == 0.0
    assert engine.score_bonus("SHORT", short_levels) == 15.0
    assert engine.score_bonus("LONG", short_levels) == 0.0


def test_scanner_sr_ceiling_gate_is_short_only():
    tree = ast.parse(_scanner_source())
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "short_has_ceiling"
    ]

    assert len(calls) == 1

    # Walk up the AST to the containing `if direction == "SHORT" ...` guard.
    parents = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    node = calls[0]
    guarded_by_short = False
    while node in parents:
        node = parents[node]
        if isinstance(node, ast.If) and isinstance(node.test, ast.BoolOp):
            for value in node.test.values:
                if (
                    isinstance(value, ast.Compare)
                    and isinstance(value.left, ast.Name)
                    and value.left.id == "direction"
                    and len(value.comparators) == 1
                    and isinstance(value.comparators[0], ast.Constant)
                    and value.comparators[0].value == "SHORT"
                ):
                    guarded_by_short = True
                    break
        if guarded_by_short:
            break

    assert guarded_by_short
