from database import Database


class StateManager:

    def __init__(self):

        self.db = Database()

    def set_value(
        self,
        key,
        value
    ):

        self.db.set_state(
            key,
            value
        )

    def get_value(
        self,
        key,
        default=None
    ):

        return self.db.get_state(
            key,
            default
        )

    def delete_value(
        self,
        key
    ):

        with self.db.connection() as conn:

            conn.execute("""
            DELETE FROM state
            WHERE key = ?
            """, (key,))
