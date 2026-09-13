"""Phase 2D-H execution outcome field contract.

These fields are persistence-ready only. They do not imply that a TP milestone
was actually executed; execution evidence must be supplied explicitly later.
"""

EXECUTION_OUTCOME_FIELDS = (
    "tp1_qty_pct",
    "tp2_qty_pct",
    "tp3_qty_pct",
    "tp1_exit_price",
    "tp2_exit_price",
    "tp3_exit_price",
    "tp1_realized_r",
    "tp2_realized_r",
    "tp3_realized_r",
    "remaining_position_pct",
    "remaining_position_exit_r",
)

DEFAULT_EXECUTION_OUTCOME = {field: "" for field in EXECUTION_OUTCOME_FIELDS}
