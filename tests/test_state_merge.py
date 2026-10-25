import pytest

from storage.state_merge import StateMergeConflict, merge_text


def test_interleaved_non_overlapping_writers_preserve_both_changes():
    base = "signal_id,status\nA,OPEN\nB,OPEN\n"
    latest = "signal_id,status\nA,TP1\nB,OPEN\n"
    generated = "signal_id,status\nA,OPEN\nB,SL\n"

    merged = merge_text(base=base, latest=latest, generated=generated)

    assert "A,TP1" in merged
    assert "B,SL" in merged


def test_overlapping_writer_changes_fail_safe_instead_of_overwriting():
    base = "signal_id,status\nA,OPEN\n"
    latest = "signal_id,status\nA,TP1\n"
    generated = "signal_id,status\nA,SL\n"

    with pytest.raises(StateMergeConflict, match="refusing to discard"):
        merge_text(base=base, latest=latest, generated=generated)


def test_preserves_unrelated_latest_file_changes():
    base = "alpha\nbeta\ngamma\n"
    latest = "alpha\nbeta-from-other-writer\ngamma\n"
    generated = "alpha\nbeta\ngamma-from-this-writer\n"

    merged = merge_text(base=base, latest=latest, generated=generated)

    assert "beta-from-other-writer" in merged
    assert "gamma-from-this-writer" in merged


def test_identical_concurrent_change_is_not_treated_as_data_loss():
    base = "state=old\n"
    latest = "state=new\n"
    generated = "state=new\n"

    assert merge_text(base=base, latest=latest, generated=generated) == "state=new\n"


def test_independent_insertions_at_different_positions_are_preserved():
    base = "alpha\nomega\n"
    latest = "alpha\nremote\nomega\n"
    generated = "alpha\nomega\nlocal-tail\n"

    merged = merge_text(base=base, latest=latest, generated=generated)

    assert merged == "alpha\nremote\nomega\nlocal-tail\n"


def test_different_insertions_at_same_position_raise_conflict():
    base = "alpha\nomega\n"
    latest = "alpha\nremote\nomega\n"
    generated = "alpha\nlocal\nomega\n"

    with pytest.raises(StateMergeConflict):
        merge_text(base=base, latest=latest, generated=generated)


def test_empty_base_with_different_initial_contents_conflicts():
    with pytest.raises(StateMergeConflict):
        merge_text(base="", latest="remote\n", generated="local\n")
