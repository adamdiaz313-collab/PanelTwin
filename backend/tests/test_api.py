import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.models import PanelSettingsInput
from app.store import PanelStore


def make_client(database_path: Path) -> TestClient:
    return TestClient(create_app(database_path))


def load_payload(**overrides) -> dict:
    payload = {
        "name": "Garage motor",
        "wattage": 1200,
        "voltage": 120,
        "continuous": False,
        "power_factor": 0.9,
        "inrush_multiplier": 3,
        "inrush_duration_seconds": 1.2,
        "data_quality": "Manufacturer",
        "weekday_periods": [
            {"start_time": "08:00", "end_time": "08:30"},
            {"start_time": "17:00", "end_time": "17:30"},
        ],
        "weekend_periods": [
            {"start_time": "10:00", "end_time": "10:30"}
        ],
        "preset_key": None,
    }
    payload.update(overrides)
    return payload


def test_panel_endpoint_returns_two_15_minute_profiles(
    tmp_path: Path,
) -> None:
    client = make_client(tmp_path / "panel.db")

    response = client.get("/api/panel")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["circuit_count"] == 5
    assert len(payload["weekday_demand"]) == 96
    assert len(payload["weekend_demand"]) == 96
    assert payload["weekday_demand"][1]["label"] == "00:15"
    assert payload["summary"]["leg_a_current"] > 0
    assert payload["summary"]["leg_b_current"] > 0


def test_create_update_and_remove_circuit(tmp_path: Path) -> None:
    client = make_client(tmp_path / "panel.db")
    home_id = client.get("/api/homes").json()[0]["id"]

    create_response = client.post(
        f"/api/circuits?home_id={home_id}",
        json={
            "name": "Garage",
            "voltage": 120,
            "breaker_rating": 20,
            "leg": "B",
        },
    )
    assert create_response.status_code == 201
    garage = next(
        circuit
        for circuit in create_response.json()["circuits"]
        if circuit["name"] == "Garage"
    )

    update_response = client.put(
        f"/api/circuits/{garage['id']}?home_id={home_id}",
        json={
            "name": "Garage workshop",
            "voltage": 120,
            "breaker_rating": 20,
            "leg": "A",
        },
    )
    assert update_response.status_code == 200

    delete_response = client.delete(
        f"/api/circuits/{garage['id']}?home_id={home_id}"
    )
    assert delete_response.status_code == 200
    assert all(
        circuit["id"] != garage["id"]
        for circuit in delete_response.json()["circuits"]
    )


def test_create_and_update_load_persists_schedules_and_quality(
    tmp_path: Path,
) -> None:
    client = make_client(tmp_path / "panel.db")
    panel = client.get("/api/panel").json()
    home_id = panel["home"]["id"]
    circuit = next(
        item for item in panel["circuits"] if item["voltage"] == 120
    )

    response = client.post(
        f"/api/circuits/{circuit['id']}/loads?home_id={home_id}",
        json=load_payload(),
    )
    assert response.status_code == 201
    created = next(
        load
        for item in response.json()["circuits"]
        if item["id"] == circuit["id"]
        for load in item["loads"]
        if load["name"] == "Garage motor"
    )
    assert created["data_quality"] == "Manufacturer"
    assert created["inrush_duration_seconds"] == 1.2
    assert len(created["weekday_periods"]) == 2

    update_response = client.put(
        (
            f"/api/circuits/{circuit['id']}/loads/{created['id']}"
            f"?home_id={home_id}"
        ),
        json=load_payload(
            name="Measured garage motor",
            data_quality="Measured",
            weekday_periods=[
                {"start_time": "07:15", "end_time": "08:00"}
            ],
        ),
    )
    assert update_response.status_code == 200
    updated = next(
        load
        for item in update_response.json()["circuits"]
        if item["id"] == circuit["id"]
        for load in item["loads"]
        if load["id"] == created["id"]
    )
    assert updated["data_quality"] == "Measured"
    assert updated["weekday_periods"][0]["start_time"] == "07:15"


def test_load_voltage_must_match_circuit(tmp_path: Path) -> None:
    client = make_client(tmp_path / "panel.db")
    panel = client.get("/api/panel").json()
    home_id = panel["home"]["id"]
    circuit_120 = next(
        circuit for circuit in panel["circuits"] if circuit["voltage"] == 120
    )

    response = client.post(
        f"/api/circuits/{circuit_120['id']}/loads?home_id={home_id}",
        json=load_payload(voltage=240),
    )

    assert response.status_code == 400
    assert "match" in response.json()["detail"]


def test_invalid_period_and_inrush_inputs_return_validation_errors(
    tmp_path: Path,
) -> None:
    client = make_client(tmp_path / "panel.db")
    panel = client.get("/api/panel").json()
    home_id = panel["home"]["id"]
    circuit = next(
        item for item in panel["circuits"] if item["voltage"] == 120
    )

    response = client.post(
        f"/api/circuits/{circuit['id']}/loads?home_id={home_id}",
        json=load_payload(
            inrush_duration_seconds=0,
            weekday_periods=[
                {"start_time": "08:10", "end_time": "09:00"}
            ],
        ),
    )

    assert response.status_code == 422


def test_sqlite_data_survives_new_store_instance(tmp_path: Path) -> None:
    database_path = tmp_path / "persistent.db"
    first_store = PanelStore(database_path)
    home = first_store.list_homes()[0]
    first_store.update_panel_settings(
        home.id,
        PanelSettingsInput(
            electricity_rate=0.31,
            main_service_rating=150,
        ),
    )

    second_store = PanelStore(database_path)
    restored = second_store.snapshot(home.id)

    assert restored.electricity_rate == 0.31
    assert restored.main_service_rating == 150
    assert restored.circuits[0].loads[0].weekday_periods


def test_legacy_database_is_migrated_without_resetting_home(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        CREATE TABLE homes (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            address TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE panels (
            id TEXT PRIMARY KEY,
            home_id TEXT NOT NULL UNIQUE,
            electricity_rate REAL NOT NULL DEFAULT 0.18,
            main_service_rating INTEGER NOT NULL DEFAULT 200
        );
        CREATE TABLE circuits (
            id TEXT PRIMARY KEY,
            panel_id TEXT NOT NULL,
            name TEXT NOT NULL,
            voltage INTEGER NOT NULL,
            breaker_rating INTEGER NOT NULL,
            leg TEXT NOT NULL
        );
        CREATE TABLE loads (
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
            preset_key TEXT
        );
        INSERT INTO homes VALUES ('home-1', 'Legacy home', '');
        INSERT INTO panels VALUES ('panel-1', 'home-1', 0.2, 100);
        INSERT INTO circuits VALUES (
            'circuit-1', 'panel-1', 'Legacy circuit', 120, 20, 'A'
        );
        INSERT INTO loads VALUES (
            'load-1', 'circuit-1', 'Legacy load', 1200, 120, 2,
            '08:00', '12:00', 0, 1, 3, NULL
        );
        """
    )
    connection.commit()
    connection.close()

    store = PanelStore(database_path)
    panel = store.snapshot("home-1")
    load = panel.circuits[0].loads[0]

    assert panel.home.name == "Legacy home"
    assert load.weekday_periods[0].start_time == "08:00"
    assert load.weekday_periods[0].end_time == "10:00"
    assert load.weekend_periods[0].end_time == "10:00"
    assert load.inrush_duration_seconds == 1


def test_presets_include_periods_inrush_duration_and_quality(
    tmp_path: Path,
) -> None:
    client = make_client(tmp_path / "panel.db")

    response = client.get("/api/presets")

    assert response.status_code == 200
    refrigerator = next(
        preset
        for preset in response.json()
        if preset["key"] == "refrigerator"
    )
    assert refrigerator["power_factor"] < 1
    assert refrigerator["inrush_multiplier"] > 1
    assert refrigerator["inrush_duration_seconds"] > 0
    assert len(refrigerator["weekday_periods"]) > 1
    assert refrigerator["data_quality"] == "Estimated"
