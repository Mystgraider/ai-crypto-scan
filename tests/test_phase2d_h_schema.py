from storage.outcome_fields import DEFAULT_EXECUTION_OUTCOME, EXECUTION_OUTCOME_FIELDS
from storage.signal_logger import FIELDNAMES


def test_execution_outcome_fields_are_part_of_persistent_schema():
    assert all(field in FIELDNAMES for field in EXECUTION_OUTCOME_FIELDS)


def test_execution_outcome_defaults_are_blank():
    assert set(DEFAULT_EXECUTION_OUTCOME) == set(EXECUTION_OUTCOME_FIELDS)
    assert all(value == "" for value in DEFAULT_EXECUTION_OUTCOME.values())


def test_execution_outcome_fields_do_not_replace_terminal_realized_r():
    assert "realized_r" in FIELDNAMES
    assert "remaining_position_exit_r" in FIELDNAMES
