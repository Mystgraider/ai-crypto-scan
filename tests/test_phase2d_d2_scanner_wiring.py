from pathlib import Path


SCANNER_PATH = Path(__file__).resolve().parents[1] / "scanner_v5.py"


def test_scanner_passes_ai_attribution_to_signal_logger():
    source = SCANNER_PATH.read_text(encoding="utf-8")
    assert "ai_attribution=sig.get(\"ai_attribution\")" in source


def test_scanner_keeps_existing_ai_rank_fields_when_logging():
    source = SCANNER_PATH.read_text(encoding="utf-8")
    assert "ai_rank_score=sig.get(\"ai_rank_score\", sig.get(\"ai_composite\"))" in source
    assert "ai_rank_raw=sig.get(\"ai_rank_raw\")" in source
    assert "confidence=confidence" in source
