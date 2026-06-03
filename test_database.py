from database import Database

db = Database()

db.set_metadata(
    "strategy_version",
    "4.0.0"
)

print(
    db.get_metadata(
        "strategy_version"
    )
)
