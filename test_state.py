from state_manager import StateManager

state = StateManager()

state.set_value(
    "BTC_LAST_SIGNAL",
    "2026-06-03 20:00:00"
)

print(
    state.get_value(
        "BTC_LAST_SIGNAL"
    )
)
