import sqlite3
from contextlib import contextmanager


class Database:

    def __init__(self, db_file="scanner.db"):
        self.db_file = db_file
        self.initialize()

    @contextmanager
    def connection(self):

        conn = sqlite3.connect(
            self.db_file,
            timeout=30,
            check_same_thread=False
        )

        try:
            yield conn
            conn.commit()

        finally:
            conn.close()

    def initialize(self):

        with self.connection() as conn:

            cursor = conn.cursor()

            # Metadata

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS metadata (

                key TEXT PRIMARY KEY,
                value TEXT
            )
            """)

            # State

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS state (

                key TEXT PRIMARY KEY,
                value TEXT
            )
            """)

            # Signals

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS signals (

                id TEXT PRIMARY KEY,

                symbol TEXT,
                direction TEXT,

                score REAL,
                grade TEXT,

                entry REAL,
                stop_loss REAL,

                tp1 REAL,
                tp2 REAL,
                tp3 REAL,

                regime TEXT,
                breadth TEXT,

                oi_grade TEXT,
                funding_grade TEXT,

                setup_hash TEXT,

                created_at TEXT
            )
            """)

            # Trades

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (

                id TEXT PRIMARY KEY,

                signal_id TEXT,

                symbol TEXT,
                direction TEXT,

                entry REAL,
                exit_price REAL,

                status TEXT,

                profit_r REAL,

                tp1_hit INTEGER DEFAULT 0,
                tp2_hit INTEGER DEFAULT 0,
                tp3_hit INTEGER DEFAULT 0,

                breakeven_hit INTEGER DEFAULT 0,
                trailing_exit INTEGER DEFAULT 0,

                created_at TEXT,
                closed_at TEXT
            )
            """)

    def set_state(
        self,
        key,
        value
    ):

        with self.connection() as conn:

            conn.execute("""
            INSERT OR REPLACE INTO state
            (
                key,
                value
            )
            VALUES (?,?)
            """, (
                key,
                str(value)
            ))

    def get_state(
        self,
        key,
        default=None
    ):

        with self.connection() as conn:

            cursor = conn.execute("""
            SELECT value
            FROM state
            WHERE key = ?
            """, (key,))

            row = cursor.fetchone()

            if row:
                return row[0]

            return default

    def set_metadata(
        self,
        key,
        value
    ):

        with self.connection() as conn:

            conn.execute("""
            INSERT OR REPLACE INTO metadata
            (
                key,
                value
            )
            VALUES (?,?)
            """, (
                key,
                str(value)
            ))

    def get_metadata(
        self,
        key,
        default=None
    ):

        with self.connection() as conn:

            cursor = conn.execute("""
            SELECT value
            FROM metadata
            WHERE key = ?
            """, (key,))

            row = cursor.fetchone()

            if row:
                return row[0]

            return default
