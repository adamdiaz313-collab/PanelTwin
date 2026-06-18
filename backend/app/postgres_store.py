from __future__ import annotations

from threading import RLock

from psycopg import Connection, connect
from psycopg.rows import dict_row

from .store import PanelStore


class PostgresConnection:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.connection: Connection | None = None

    def __enter__(self) -> "PostgresConnection":
        self.connection = connect(self.database_url, row_factory=dict_row)
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self.connection is None:
            return
        if exc_type is None:
            self.connection.commit()
        else:
            self.connection.rollback()
        self.connection.close()
        self.connection = None

    @staticmethod
    def _translate_sql(sql: str) -> str:
        replacements = {
            "ORDER BY homes.rowid": "ORDER BY homes.created_order",
            "ORDER BY circuits.rowid": "ORDER BY circuits.created_order",
            "ORDER BY loads.rowid": "ORDER BY loads.created_order",
            "ORDER BY rowid": "ORDER BY created_order",
        }
        for sqlite_text, postgres_text in replacements.items():
            sql = sql.replace(sqlite_text, postgres_text)
        return sql.replace("?", "%s")

    def execute(self, sql: str, parameters=()):
        if self.connection is None:
            raise RuntimeError("Postgres connection is not open.")
        return self.connection.execute(
            self._translate_sql(sql),
            parameters,
        )

    def executescript(self, script: str) -> None:
        for statement in script.split(";"):
            if statement.strip():
                self.execute(statement)


class PostgresPanelStore(PanelStore):
    storage_name = "postgres"

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._lock = RLock()
        self.initialize()

    def connect(self) -> PostgresConnection:
        return PostgresConnection(self.database_url)

    def initialize(self) -> None:
        with self._lock, self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS homes (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    address TEXT NOT NULL DEFAULT '',
                    created_order BIGSERIAL UNIQUE
                );

                CREATE TABLE IF NOT EXISTS panels (
                    id TEXT PRIMARY KEY,
                    home_id TEXT NOT NULL UNIQUE,
                    electricity_rate DOUBLE PRECISION NOT NULL DEFAULT 0.18,
                    main_service_rating INTEGER NOT NULL DEFAULT 200,
                    FOREIGN KEY (home_id) REFERENCES homes(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS circuits (
                    id TEXT PRIMARY KEY,
                    panel_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    voltage INTEGER NOT NULL,
                    breaker_rating INTEGER NOT NULL,
                    leg TEXT NOT NULL,
                    created_order BIGSERIAL UNIQUE,
                    FOREIGN KEY (panel_id) REFERENCES panels(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS loads (
                    id TEXT PRIMARY KEY,
                    circuit_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    wattage DOUBLE PRECISION NOT NULL,
                    voltage INTEGER NOT NULL,
                    hours_per_day DOUBLE PRECISION NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    continuous INTEGER NOT NULL DEFAULT 0,
                    power_factor DOUBLE PRECISION NOT NULL DEFAULT 1.0,
                    inrush_multiplier DOUBLE PRECISION NOT NULL DEFAULT 1.0,
                    preset_key TEXT,
                    inrush_duration_seconds DOUBLE PRECISION NOT NULL DEFAULT 0,
                    data_quality TEXT NOT NULL DEFAULT 'Estimated',
                    created_order BIGSERIAL UNIQUE,
                    FOREIGN KEY (circuit_id) REFERENCES circuits(id)
                        ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS load_periods (
                    id TEXT PRIMARY KEY,
                    load_id TEXT NOT NULL,
                    day_type TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (load_id) REFERENCES loads(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_load_periods_load_id
                ON load_periods(load_id, day_type, sort_order);
                """
            )
            count = connection.execute(
                "SELECT COUNT(*) AS count FROM homes"
            ).fetchone()["count"]
            if count == 0:
                self._seed_sample(connection)

    def _ensure_load_column(
        self,
        connection: PostgresConnection,
        name: str,
        definition: str,
    ) -> None:
        return None

    def _migrate_legacy_schedules(
        self,
        connection: PostgresConnection,
    ) -> None:
        return None
