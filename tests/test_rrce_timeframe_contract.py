import ast
from pathlib import Path


def _rrce_evaluate_calls():
    tree = ast.parse(Path("scanner_v5.py").read_text(encoding="utf-8"))
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "evaluate":
                keywords = {kw.arg: kw.value for kw in node.keywords if kw.arg}
                if {"df_htf", "df_mtf", "df_ltf_confirm", "df_ltf_exec"} <= set(keywords):
                    calls.append(keywords)
    return calls


def test_production_rrce_timeframe_contract():
    calls = _rrce_evaluate_calls()
    assert calls, "No RRCE evaluate call with the full dataframe contract was found"

    rrce_call = calls[0]
    assert isinstance(rrce_call["df_htf"], ast.Name)
    assert isinstance(rrce_call["df_mtf"], ast.Name)
    assert isinstance(rrce_call["df_ltf_confirm"], ast.Name)
    assert isinstance(rrce_call["df_ltf_exec"], ast.Name)

    assert rrce_call["df_htf"].id == "df_4h"
    assert rrce_call["df_mtf"].id == "df_1h"
    assert rrce_call["df_ltf_confirm"].id == "_df_rrce_15m"
    assert rrce_call["df_ltf_exec"].id == "_df_rrce_5m"


def test_rrce_stage1_prefilter_uses_4h_range_data():
    tree = ast.parse(Path("scanner_v5.py").read_text(encoding="utf-8"))
    matches = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "stage1_range" and node.args:
                if isinstance(node.args[0], ast.Name):
                    matches.append(node.args[0].id)

    assert "df_4h" in matches
