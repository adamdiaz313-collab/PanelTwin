import os
import sqlite3
from pathlib import Path
from threading import RLock
from uuid import uuid4

from .models import (
    Circuit,
    CircuitInput,
    ElectricalLoad,
    Home,
    HomeInput,
    LoadInput,
    MINUTES_PER_DAY,
    PanelSettingsInput,
    PanelState,
    SchedulePeriod,
    time_to_minutes,
)


def new_id() -> str:
    return uuid4().hex


def period_minutes(period: SchedulePeriod) -> int:
    start = time_to_minutes(period.start_time)
    end = time_to_minutes(period.end_time)
    if start == end:
        return MINUTES_PER_DAY
    if end > start:
        return end - start
    return MINUTES_PER_DAY - start + end


def schedule_hours(periods: list[SchedulePeriod]) -> float:
    return sum(period_minutes(period) for period in periods) / 60


class StoreError(Exception):
    pass


class NotFoundError(StoreError):
    pass


class VoltageMismatchError(StoreError):
    pass


class PanelStore:
    storage_name = "sqlite"

    def __init__(self, database_path: str | Path | None = None) -> None:
        default_path = Path(__file__).resolve().parents[1] / "paneltwin.db"
        self.database_path = Path(
            database_path
            or os.getenv("PANELTWIN_DB_PATH")
            or default_path
        )
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with self._lock, self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS homes (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    address TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS panels (
                    id TEXT PRIMARY KEY,
                    home_id TEXT NOT NULL UNIQUE,
                    electricity_rate REAL NOT NULL DEFAULT 0.18,
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
                    FOREIGN KEY (panel_id) REFERENCES panels(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS loads (
                    id TEXT PRIMARY KEY,
                    circuit_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    wattage REAL NOT NULL,
                    voltage INTEGER NOT NULL,
                    hours_per_day REAL NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    continuous INTEGER NOT NULL DEFAULT 0,
                    power_factor REAL NOT NULL DEFAULT 1.0,
                    inrush_multiplier REAL NOT NULL DEFAULT 1.0,
                    preset_key TEXT,
                    inrush_duration_seconds REAL NOT NULL DEFAULT 0,
                    data_quality TEXT NOT NULL DEFAULT 'Estimated',
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
            self._ensure_load_column(
                connection,
                "inrush_duration_seconds",
                "REAL NOT NULL DEFAULT 0",
            )
            self._ensure_load_column(
                connection,
                "data_quality",
                "TEXT NOT NULL DEFAULT 'Estimated'",
            )
            self._migrate_legacy_schedules(connection)
            count = connection.execute(
                "SELECT COUNT(*) AS count FROM homes"
            ).fetchone()["count"]
            if count == 0:
                self._seed_sample(connection)

    def _ensure_load_column(
        self,
        connection: sqlite3.Connection,
        name: str,
        definition: str,
    ) -> None:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(loads)")
        }
        if name not in columns:
            connection.execute(
                f"ALTER TABLE loads ADD COLUMN {name} {definition}"
            )

    def _migrate_legacy_schedules(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        rows = connection.execute(
            """
            SELECT loads.* FROM loads
            LEFT JOIN load_periods ON load_periods.load_id = loads.id
            WHERE load_periods.id IS NULL
            """
        ).fetchall()
        for row in rows:
            start_minutes = time_to_minutes(row["start_time"])
            duration_steps = round(float(row["hours_per_day"]) * 4)
            if duration_steps <= 0:
                continue
            duration_steps = min(duration_steps, 96)
            end_minutes = (
                start_minutes + duration_steps * 15
            ) % MINUTES_PER_DAY
            end_time = (
                row["start_time"]
                if duration_steps == 96
                else f"{end_minutes // 60:02d}:{end_minutes % 60:02d}"
            )
            for day_type in ("weekday", "weekend"):
                connection.execute(
                    """
                    INSERT INTO load_periods (
                        id, load_id, day_type, start_time, end_time, sort_order
                    ) VALUES (?, ?, ?, ?, ?, 0)
                    """,
                    (
                        new_id(),
                        row["id"],
                        day_type,
                        row["start_time"],
                        end_time,
                    ),
                )
            if (
                row["inrush_multiplier"] > 1
                and row["inrush_duration_seconds"] <= 0
            ):
                connection.execute(
                    """
                    UPDATE loads
                    SET inrush_duration_seconds = 1
                    WHERE id = ?
                    """,
                    (row["id"],),
                )

    def _insert_periods(
        self,
        connection: sqlite3.Connection,
        load_id: str,
        weekday_periods: list[SchedulePeriod],
        weekend_periods: list[SchedulePeriod],
    ) -> None:
        for day_type, periods in (
            ("weekday", weekday_periods),
            ("weekend", weekend_periods),
        ):
            for order, period in enumerate(periods):
                connection.execute(
                    """
                    INSERT INTO load_periods (
                        id, load_id, day_type, start_time, end_time, sort_order
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        new_id(),
                        load_id,
                        day_type,
                        period.start_time,
                        period.end_time,
                        order,
                    ),
                )

    def _insert_load(
        self,
        connection: sqlite3.Connection,
        circuit_id: str,
        load_input: LoadInput,
    ) -> str:
        load_id = new_id()
        legacy_period = (
            load_input.weekday_periods
            or load_input.weekend_periods
        )[0]
        connection.execute(
            """
            INSERT INTO loads (
                id, circuit_id, name, wattage, voltage, hours_per_day,
                start_time, end_time, continuous, power_factor,
                inrush_multiplier, preset_key, inrush_duration_seconds,
                data_quality
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                load_id,
                circuit_id,
                load_input.name,
                load_input.wattage,
                load_input.voltage,
                schedule_hours(load_input.weekday_periods),
                legacy_period.start_time,
                legacy_period.end_time,
                int(load_input.continuous),
                load_input.power_factor,
                load_input.inrush_multiplier,
                load_input.preset_key,
                load_input.inrush_duration_seconds,
                load_input.data_quality,
            ),
        )
        self._insert_periods(
            connection,
            load_id,
            load_input.weekday_periods,
            load_input.weekend_periods,
        )
        return load_id

    def _seed_sample(self, connection: sqlite3.Connection) -> str:
        home_id = new_id()
        panel_id = new_id()
        connection.execute(
            "INSERT INTO homes (id, name, address) VALUES (?, ?, ?)",
            (home_id, "My Home", "Sample split-phase residence"),
        )
        connection.execute(
            """
            INSERT INTO panels (
                id, home_id, electricity_rate, main_service_rating
            ) VALUES (?, ?, ?, ?)
            """,
            (panel_id, home_id, 0.18, 200),
        )

        sample_circuits = [
            {
                "name": "Kitchen small appliances",
                "voltage": 120,
                "breaker_rating": 20,
                "leg": "A",
                "loads": [
                    LoadInput(
                        name="Coffee maker",
                        wattage=1100,
                        voltage=120,
                        continuous=False,
                        power_factor=1,
                        data_quality="Estimated",
                        weekday_periods=[
                            SchedulePeriod(
                                start_time="06:30",
                                end_time="07:00",
                            )
                        ],
                        weekend_periods=[
                            SchedulePeriod(
                                start_time="08:00",
                                end_time="08:30",
                            )
                        ],
                        preset_key="coffee-maker",
                    ),
                    LoadInput(
                        name="Refrigerator",
                        wattage=180,
                        voltage=120,
                        continuous=False,
                        power_factor=0.85,
                        inrush_multiplier=4,
                        inrush_duration_seconds=1,
                        data_quality="Manufacturer",
                        weekday_periods=[
                            SchedulePeriod(
                                start_time=f"{hour:02d}:00",
                                end_time=f"{hour + 1:02d}:00",
                            )
                            for hour in range(0, 24, 3)
                        ],
                        weekend_periods=[
                            SchedulePeriod(
                                start_time=f"{hour:02d}:00",
                                end_time=f"{hour + 1:02d}:00",
                            )
                            for hour in range(0, 24, 3)
                        ],
                        preset_key="refrigerator",
                    ),
                ],
            },
            {
                "name": "Home office",
                "voltage": 120,
                "breaker_rating": 15,
                "leg": "B",
                "loads": [
                    LoadInput(
                        name="Computer workstation",
                        wattage=780,
                        voltage=120,
                        continuous=True,
                        power_factor=0.95,
                        inrush_multiplier=1.2,
                        inrush_duration_seconds=0.5,
                        data_quality="Measured",
                        weekday_periods=[
                            SchedulePeriod(
                                start_time="08:00",
                                end_time="12:00",
                            ),
                            SchedulePeriod(
                                start_time="13:00",
                                end_time="17:00",
                            ),
                        ],
                        weekend_periods=[
                            SchedulePeriod(
                                start_time="10:00",
                                end_time="12:00",
                            )
                        ],
                        preset_key="computer-workstation",
                    ),
                    LoadInput(
                        name="Monitors and network",
                        wattage=260,
                        voltage=120,
                        continuous=True,
                        power_factor=0.95,
                        inrush_multiplier=1.1,
                        inrush_duration_seconds=0.2,
                        data_quality="Measured",
                        weekday_periods=[
                            SchedulePeriod(
                                start_time="08:00",
                                end_time="12:00",
                            ),
                            SchedulePeriod(
                                start_time="13:00",
                                end_time="18:00",
                            ),
                        ],
                        weekend_periods=[
                            SchedulePeriod(
                                start_time="10:00",
                                end_time="13:00",
                            )
                        ],
                        preset_key="home-office",
                    ),
                ],
            },
            {
                "name": "Electric dryer",
                "voltage": 240,
                "breaker_rating": 30,
                "leg": "AB",
                "loads": [
                    LoadInput(
                        name="Dryer heating and motor",
                        wattage=5000,
                        voltage=240,
                        continuous=False,
                        power_factor=0.95,
                        inrush_multiplier=2.5,
                        inrush_duration_seconds=1.5,
                        data_quality="Manufacturer",
                        weekday_periods=[
                            SchedulePeriod(
                                start_time="18:00",
                                end_time="18:45",
                            )
                        ],
                        weekend_periods=[
                            SchedulePeriod(
                                start_time="14:00",
                                end_time="15:00",
                            )
                        ],
                        preset_key="electric-dryer",
                    )
                ],
            },
            {
                "name": "Water heater",
                "voltage": 240,
                "breaker_rating": 30,
                "leg": "AB",
                "loads": [
                    LoadInput(
                        name="Tank heating elements",
                        wattage=4500,
                        voltage=240,
                        continuous=True,
                        power_factor=1,
                        data_quality="Manufacturer",
                        weekday_periods=[
                            SchedulePeriod(
                                start_time="05:00",
                                end_time="06:30",
                            ),
                            SchedulePeriod(
                                start_time="18:00",
                                end_time="19:30",
                            ),
                        ],
                        weekend_periods=[
                            SchedulePeriod(
                                start_time="06:00",
                                end_time="07:30",
                            ),
                            SchedulePeriod(
                                start_time="18:00",
                                end_time="19:30",
                            ),
                        ],
                        preset_key="water-heater",
                    )
                ],
            },
            {
                "name": "Central air",
                "voltage": 240,
                "breaker_rating": 40,
                "leg": "AB",
                "loads": [
                    LoadInput(
                        name="HVAC compressor and blower",
                        wattage=4200,
                        voltage=240,
                        continuous=True,
                        power_factor=0.88,
                        inrush_multiplier=3.5,
                        inrush_duration_seconds=0.8,
                        data_quality="Manufacturer",
                        weekday_periods=[
                            SchedulePeriod(
                                start_time="12:00",
                                end_time="18:00",
                            )
                        ],
                        weekend_periods=[
                            SchedulePeriod(
                                start_time="11:00",
                                end_time="19:00",
                            )
                        ],
                        preset_key="central-air",
                    )
                ],
            },
        ]

        for circuit_data in sample_circuits:
            circuit_id = new_id()
            connection.execute(
                """
                INSERT INTO circuits (
                    id, panel_id, name, voltage, breaker_rating, leg
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    circuit_id,
                    panel_id,
                    circuit_data["name"],
                    circuit_data["voltage"],
                    circuit_data["breaker_rating"],
                    circuit_data["leg"],
                ),
            )
            for load_input in circuit_data["loads"]:
                self._insert_load(connection, circuit_id, load_input)
        return home_id

    def list_homes(self) -> list[Home]:
        with self._lock, self.connect() as connection:
            rows = connection.execute(
                """
                SELECT homes.id, homes.name, homes.address, panels.id AS panel_id
                FROM homes
                JOIN panels ON panels.home_id = homes.id
                ORDER BY homes.rowid
                """
            ).fetchall()
        return [Home(**dict(row)) for row in rows]

    def create_home(self, home_input: HomeInput) -> Home:
        with self._lock, self.connect() as connection:
            home_id = new_id()
            panel_id = new_id()
            connection.execute(
                "INSERT INTO homes (id, name, address) VALUES (?, ?, ?)",
                (home_id, home_input.name, home_input.address),
            )
            connection.execute(
                """
                INSERT INTO panels (
                    id, home_id, electricity_rate, main_service_rating
                ) VALUES (?, ?, ?, ?)
                """,
                (panel_id, home_id, 0.18, 200),
            )
        return Home(id=home_id, panel_id=panel_id, **home_input.model_dump())

    def update_home(self, home_id: str, home_input: HomeInput) -> Home:
        with self._lock, self.connect() as connection:
            result = connection.execute(
                "UPDATE homes SET name = ?, address = ? WHERE id = ?",
                (home_input.name, home_input.address, home_id),
            )
            if result.rowcount == 0:
                raise NotFoundError("Home not found.")
        return self.get_home(home_id)

    def get_home(self, home_id: str) -> Home:
        with self._lock, self.connect() as connection:
            row = connection.execute(
                """
                SELECT homes.id, homes.name, homes.address, panels.id AS panel_id
                FROM homes
                JOIN panels ON panels.home_id = homes.id
                WHERE homes.id = ?
                """,
                (home_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError("Home not found.")
        return Home(**dict(row))

    def _resolve_home_id(
        self,
        connection: sqlite3.Connection,
        home_id: str | None,
    ) -> str:
        if home_id:
            exists = connection.execute(
                "SELECT id FROM homes WHERE id = ?",
                (home_id,),
            ).fetchone()
            if exists is None:
                raise NotFoundError("Home not found.")
            return home_id
        row = connection.execute(
            "SELECT id FROM homes ORDER BY rowid LIMIT 1"
        ).fetchone()
        if row is None:
            raise NotFoundError("No homes exist.")
        return row["id"]

    def snapshot(self, home_id: str | None = None) -> PanelState:
        with self._lock, self.connect() as connection:
            resolved_home_id = self._resolve_home_id(connection, home_id)
            panel_row = connection.execute(
                """
                SELECT
                    homes.id AS home_id,
                    homes.name AS home_name,
                    homes.address,
                    panels.id AS panel_id,
                    panels.electricity_rate,
                    panels.main_service_rating
                FROM homes
                JOIN panels ON panels.home_id = homes.id
                WHERE homes.id = ?
                """,
                (resolved_home_id,),
            ).fetchone()
            circuit_rows = connection.execute(
                """
                SELECT * FROM circuits
                WHERE panel_id = ?
                ORDER BY rowid
                """,
                (panel_row["panel_id"],),
            ).fetchall()
            load_rows = connection.execute(
                """
                SELECT loads.* FROM loads
                JOIN circuits ON circuits.id = loads.circuit_id
                WHERE circuits.panel_id = ?
                ORDER BY loads.rowid
                """,
                (panel_row["panel_id"],),
            ).fetchall()
            period_rows = connection.execute(
                """
                SELECT load_periods.* FROM load_periods
                JOIN loads ON loads.id = load_periods.load_id
                JOIN circuits ON circuits.id = loads.circuit_id
                WHERE circuits.panel_id = ?
                ORDER BY load_periods.day_type, load_periods.sort_order
                """,
                (panel_row["panel_id"],),
            ).fetchall()

        periods_by_load: dict[str, dict[str, list[SchedulePeriod]]] = {}
        for row in period_rows:
            periods_by_load.setdefault(
                row["load_id"],
                {"weekday": [], "weekend": []},
            )[row["day_type"]].append(
                SchedulePeriod(
                    start_time=row["start_time"],
                    end_time=row["end_time"],
                )
            )

        loads_by_circuit: dict[str, list[ElectricalLoad]] = {}
        for row in load_rows:
            load_data = dict(row)
            load_data["continuous"] = bool(load_data["continuous"])
            load_data.pop("hours_per_day", None)
            load_data.pop("start_time", None)
            load_data.pop("end_time", None)
            schedules = periods_by_load.get(
                row["id"],
                {"weekday": [], "weekend": []},
            )
            load_data["weekday_periods"] = schedules["weekday"]
            load_data["weekend_periods"] = schedules["weekend"]
            loads_by_circuit.setdefault(row["circuit_id"], []).append(
                ElectricalLoad(**load_data)
            )

        circuits = [
            Circuit(
                **dict(row),
                loads=loads_by_circuit.get(row["id"], []),
            )
            for row in circuit_rows
        ]
        return PanelState(
            home=Home(
                id=panel_row["home_id"],
                panel_id=panel_row["panel_id"],
                name=panel_row["home_name"],
                address=panel_row["address"],
            ),
            electricity_rate=panel_row["electricity_rate"],
            main_service_rating=panel_row["main_service_rating"],
            circuits=circuits,
        )

    def update_panel_settings(
        self,
        home_id: str,
        settings: PanelSettingsInput,
    ) -> PanelState:
        with self._lock, self.connect() as connection:
            result = connection.execute(
                """
                UPDATE panels
                SET electricity_rate = ?, main_service_rating = ?
                WHERE home_id = ?
                """,
                (
                    settings.electricity_rate,
                    settings.main_service_rating,
                    home_id,
                ),
            )
            if result.rowcount == 0:
                raise NotFoundError("Home panel not found.")
        return self.snapshot(home_id)

    def add_circuit(
        self,
        home_id: str,
        circuit_input: CircuitInput,
    ) -> PanelState:
        with self._lock, self.connect() as connection:
            panel = connection.execute(
                "SELECT id FROM panels WHERE home_id = ?",
                (home_id,),
            ).fetchone()
            if panel is None:
                raise NotFoundError("Home panel not found.")
            connection.execute(
                """
                INSERT INTO circuits (
                    id, panel_id, name, voltage, breaker_rating, leg
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id(),
                    panel["id"],
                    circuit_input.name,
                    circuit_input.voltage,
                    circuit_input.breaker_rating,
                    circuit_input.leg,
                ),
            )
        return self.snapshot(home_id)

    def update_circuit(
        self,
        home_id: str,
        circuit_id: str,
        circuit_input: CircuitInput,
    ) -> PanelState:
        with self._lock, self.connect() as connection:
            load_voltages = connection.execute(
                "SELECT DISTINCT voltage FROM loads WHERE circuit_id = ?",
                (circuit_id,),
            ).fetchall()
            if any(
                row["voltage"] != circuit_input.voltage
                for row in load_voltages
            ):
                raise VoltageMismatchError(
                    "Remove or edit loads before changing circuit voltage."
                )
            result = connection.execute(
                """
                UPDATE circuits
                SET name = ?, voltage = ?, breaker_rating = ?, leg = ?
                WHERE id = ? AND panel_id = (
                    SELECT id FROM panels WHERE home_id = ?
                )
                """,
                (
                    circuit_input.name,
                    circuit_input.voltage,
                    circuit_input.breaker_rating,
                    circuit_input.leg,
                    circuit_id,
                    home_id,
                ),
            )
            if result.rowcount == 0:
                raise NotFoundError("Circuit not found.")
        return self.snapshot(home_id)

    def remove_circuit(self, home_id: str, circuit_id: str) -> PanelState:
        with self._lock, self.connect() as connection:
            result = connection.execute(
                """
                DELETE FROM circuits
                WHERE id = ? AND panel_id = (
                    SELECT id FROM panels WHERE home_id = ?
                )
                """,
                (circuit_id, home_id),
            )
            if result.rowcount == 0:
                raise NotFoundError("Circuit not found.")
        return self.snapshot(home_id)

    def _get_circuit(
        self,
        connection: sqlite3.Connection,
        home_id: str,
        circuit_id: str,
    ) -> sqlite3.Row:
        row = connection.execute(
            """
            SELECT circuits.* FROM circuits
            JOIN panels ON panels.id = circuits.panel_id
            WHERE circuits.id = ? AND panels.home_id = ?
            """,
            (circuit_id, home_id),
        ).fetchone()
        if row is None:
            raise NotFoundError("Circuit not found.")
        return row

    def add_load(
        self,
        home_id: str,
        circuit_id: str,
        load_input: LoadInput,
    ) -> PanelState:
        with self._lock, self.connect() as connection:
            circuit = self._get_circuit(connection, home_id, circuit_id)
            if circuit["voltage"] != load_input.voltage:
                raise VoltageMismatchError(
                    "Load voltage must match the circuit voltage."
                )
            self._insert_load(connection, circuit_id, load_input)
        return self.snapshot(home_id)

    def update_load(
        self,
        home_id: str,
        circuit_id: str,
        load_id: str,
        load_input: LoadInput,
    ) -> PanelState:
        with self._lock, self.connect() as connection:
            circuit = self._get_circuit(connection, home_id, circuit_id)
            if circuit["voltage"] != load_input.voltage:
                raise VoltageMismatchError(
                    "Load voltage must match the circuit voltage."
                )
            legacy_period = (
                load_input.weekday_periods
                or load_input.weekend_periods
            )[0]
            result = connection.execute(
                """
                UPDATE loads
                SET name = ?, wattage = ?, voltage = ?, hours_per_day = ?,
                    start_time = ?, end_time = ?, continuous = ?,
                    power_factor = ?, inrush_multiplier = ?, preset_key = ?,
                    inrush_duration_seconds = ?, data_quality = ?
                WHERE id = ? AND circuit_id = ?
                """,
                (
                    load_input.name,
                    load_input.wattage,
                    load_input.voltage,
                    schedule_hours(load_input.weekday_periods),
                    legacy_period.start_time,
                    legacy_period.end_time,
                    int(load_input.continuous),
                    load_input.power_factor,
                    load_input.inrush_multiplier,
                    load_input.preset_key,
                    load_input.inrush_duration_seconds,
                    load_input.data_quality,
                    load_id,
                    circuit_id,
                ),
            )
            if result.rowcount == 0:
                raise NotFoundError("Load not found.")
            connection.execute(
                "DELETE FROM load_periods WHERE load_id = ?",
                (load_id,),
            )
            self._insert_periods(
                connection,
                load_id,
                load_input.weekday_periods,
                load_input.weekend_periods,
            )
        return self.snapshot(home_id)

    def remove_load(
        self,
        home_id: str,
        circuit_id: str,
        load_id: str,
    ) -> PanelState:
        with self._lock, self.connect() as connection:
            self._get_circuit(connection, home_id, circuit_id)
            result = connection.execute(
                "DELETE FROM loads WHERE id = ? AND circuit_id = ?",
                (load_id, circuit_id),
            )
            if result.rowcount == 0:
                raise NotFoundError("Load not found.")
        return self.snapshot(home_id)

    def reset(self) -> PanelState:
        with self._lock, self.connect() as connection:
            connection.execute("DELETE FROM homes")
            home_id = self._seed_sample(connection)
        return self.snapshot(home_id)
