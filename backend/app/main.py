import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware

from .calculations import calculate_panel
from .models import (
    AppliancePreset,
    CircuitInput,
    Home,
    HomeInput,
    LoadInput,
    PanelAnalysis,
    PanelSettingsInput,
    SchedulePeriod,
)
from .store import (
    NotFoundError,
    PanelStore,
    VoltageMismatchError,
)

APPLIANCE_PRESETS = [
    AppliancePreset(
        key="refrigerator",
        name="Refrigerator",
        category="Kitchen",
        wattage=180,
        voltage=120,
        continuous=False,
        power_factor=0.85,
        inrush_multiplier=4.0,
        inrush_duration_seconds=1,
        data_quality="Estimated",
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
    ),
    AppliancePreset(
        key="central-air",
        name="Central air conditioner",
        category="HVAC",
        wattage=4200,
        voltage=240,
        continuous=True,
        power_factor=0.88,
        inrush_multiplier=3.5,
        inrush_duration_seconds=0.8,
        data_quality="Estimated",
        weekday_periods=[
            SchedulePeriod(start_time="12:00", end_time="18:00")
        ],
        weekend_periods=[
            SchedulePeriod(start_time="11:00", end_time="19:00")
        ],
    ),
    AppliancePreset(
        key="heat-pump",
        name="Heat pump",
        category="HVAC",
        wattage=3500,
        voltage=240,
        continuous=True,
        power_factor=0.9,
        inrush_multiplier=3.0,
        inrush_duration_seconds=1,
        data_quality="Estimated",
        weekday_periods=[
            SchedulePeriod(start_time="06:00", end_time="09:00"),
            SchedulePeriod(start_time="17:00", end_time="21:00"),
        ],
        weekend_periods=[
            SchedulePeriod(start_time="07:00", end_time="11:00"),
            SchedulePeriod(start_time="16:00", end_time="21:00"),
        ],
    ),
    AppliancePreset(
        key="electric-dryer",
        name="Electric dryer",
        category="Laundry",
        wattage=5000,
        voltage=240,
        continuous=False,
        power_factor=0.95,
        inrush_multiplier=2.5,
        inrush_duration_seconds=1.5,
        data_quality="Estimated",
        weekday_periods=[
            SchedulePeriod(start_time="18:00", end_time="18:45")
        ],
        weekend_periods=[
            SchedulePeriod(start_time="14:00", end_time="15:00")
        ],
    ),
    AppliancePreset(
        key="water-heater",
        name="Electric water heater",
        category="Water heating",
        wattage=4500,
        voltage=240,
        continuous=True,
        power_factor=1.0,
        inrush_multiplier=1.0,
        inrush_duration_seconds=0,
        data_quality="Estimated",
        weekday_periods=[
            SchedulePeriod(start_time="05:00", end_time="06:30"),
            SchedulePeriod(start_time="18:00", end_time="19:30"),
        ],
        weekend_periods=[
            SchedulePeriod(start_time="06:00", end_time="07:30"),
            SchedulePeriod(start_time="18:00", end_time="19:30"),
        ],
    ),
    AppliancePreset(
        key="ev-charger",
        name="EV charger",
        category="Transportation",
        wattage=7200,
        voltage=240,
        continuous=True,
        power_factor=0.98,
        inrush_multiplier=1.0,
        inrush_duration_seconds=0,
        data_quality="Estimated",
        weekday_periods=[
            SchedulePeriod(start_time="22:00", end_time="02:00")
        ],
        weekend_periods=[
            SchedulePeriod(start_time="23:00", end_time="04:00")
        ],
    ),
    AppliancePreset(
        key="sump-pump",
        name="Sump pump",
        category="Motor",
        wattage=900,
        voltage=120,
        continuous=False,
        power_factor=0.8,
        inrush_multiplier=5.0,
        inrush_duration_seconds=2,
        data_quality="Estimated",
        weekday_periods=[
            SchedulePeriod(start_time="06:00", end_time="06:15"),
            SchedulePeriod(start_time="18:00", end_time="18:15"),
        ],
        weekend_periods=[
            SchedulePeriod(start_time="07:00", end_time="07:15"),
            SchedulePeriod(start_time="19:00", end_time="19:15"),
        ],
    ),
    AppliancePreset(
        key="lighting",
        name="LED lighting group",
        category="Lighting",
        wattage=500,
        voltage=120,
        continuous=False,
        power_factor=0.95,
        inrush_multiplier=1.0,
        inrush_duration_seconds=0,
        data_quality="Estimated",
        weekday_periods=[
            SchedulePeriod(start_time="17:00", end_time="23:00")
        ],
        weekend_periods=[
            SchedulePeriod(start_time="16:00", end_time="23:30")
        ],
    ),
]


def get_store(request: Request) -> PanelStore:
    return request.app.state.store


def translate_store_error(error: Exception) -> HTTPException:
    if isinstance(error, NotFoundError):
        return HTTPException(status_code=404, detail=str(error))
    if isinstance(error, VoltageMismatchError):
        return HTTPException(status_code=400, detail=str(error))
    return HTTPException(status_code=500, detail="Unexpected storage error.")


def create_app(database_path: str | Path | None = None) -> FastAPI:
    app = FastAPI(
        title="PanelTwin API",
        description=(
            "Persistent split-phase and time-based residential electrical "
            "panel digital twin."
        ),
        version="3.0.0",
    )
    database_url = os.getenv("DATABASE_URL")
    if database_url and database_path is None:
        from .postgres_store import PostgresPanelStore

        app.state.store = PostgresPanelStore(database_url)
    else:
        app.state.store = PanelStore(database_path)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health_check() -> dict[str, str]:
        return {
            "status": "ok",
            "storage": app.state.store.storage_name,
        }

    @app.get("/api/homes", response_model=list[Home])
    def list_homes(request: Request) -> list[Home]:
        return get_store(request).list_homes()

    @app.post(
        "/api/homes",
        response_model=Home,
        status_code=status.HTTP_201_CREATED,
    )
    def create_home(request: Request, home_input: HomeInput) -> Home:
        return get_store(request).create_home(home_input)

    @app.put("/api/homes/{home_id}", response_model=Home)
    def update_home(
        request: Request,
        home_id: str,
        home_input: HomeInput,
    ) -> Home:
        try:
            return get_store(request).update_home(home_id, home_input)
        except Exception as error:
            raise translate_store_error(error) from error

    @app.get("/api/panel", response_model=PanelAnalysis)
    def get_panel(
        request: Request,
        home_id: str | None = Query(default=None),
    ) -> PanelAnalysis:
        try:
            return calculate_panel(get_store(request).snapshot(home_id))
        except Exception as error:
            raise translate_store_error(error) from error

    @app.put("/api/panel/settings", response_model=PanelAnalysis)
    def update_panel_settings(
        request: Request,
        settings: PanelSettingsInput,
        home_id: str = Query(...),
    ) -> PanelAnalysis:
        try:
            panel = get_store(request).update_panel_settings(home_id, settings)
            return calculate_panel(panel)
        except Exception as error:
            raise translate_store_error(error) from error

    @app.get("/api/presets", response_model=list[AppliancePreset])
    def get_presets() -> list[AppliancePreset]:
        return APPLIANCE_PRESETS

    @app.post(
        "/api/circuits",
        response_model=PanelAnalysis,
        status_code=status.HTTP_201_CREATED,
    )
    def create_circuit(
        request: Request,
        circuit_input: CircuitInput,
        home_id: str = Query(...),
    ) -> PanelAnalysis:
        try:
            panel = get_store(request).add_circuit(home_id, circuit_input)
            return calculate_panel(panel)
        except Exception as error:
            raise translate_store_error(error) from error

    @app.put(
        "/api/circuits/{circuit_id}",
        response_model=PanelAnalysis,
    )
    def update_circuit(
        request: Request,
        circuit_id: str,
        circuit_input: CircuitInput,
        home_id: str = Query(...),
    ) -> PanelAnalysis:
        try:
            panel = get_store(request).update_circuit(
                home_id,
                circuit_id,
                circuit_input,
            )
            return calculate_panel(panel)
        except Exception as error:
            raise translate_store_error(error) from error

    @app.delete(
        "/api/circuits/{circuit_id}",
        response_model=PanelAnalysis,
    )
    def delete_circuit(
        request: Request,
        circuit_id: str,
        home_id: str = Query(...),
    ) -> PanelAnalysis:
        try:
            panel = get_store(request).remove_circuit(home_id, circuit_id)
            return calculate_panel(panel)
        except Exception as error:
            raise translate_store_error(error) from error

    @app.post(
        "/api/circuits/{circuit_id}/loads",
        response_model=PanelAnalysis,
        status_code=status.HTTP_201_CREATED,
    )
    def create_load(
        request: Request,
        circuit_id: str,
        load_input: LoadInput,
        home_id: str = Query(...),
    ) -> PanelAnalysis:
        try:
            panel = get_store(request).add_load(
                home_id,
                circuit_id,
                load_input,
            )
            return calculate_panel(panel)
        except Exception as error:
            raise translate_store_error(error) from error

    @app.put(
        "/api/circuits/{circuit_id}/loads/{load_id}",
        response_model=PanelAnalysis,
    )
    def update_load(
        request: Request,
        circuit_id: str,
        load_id: str,
        load_input: LoadInput,
        home_id: str = Query(...),
    ) -> PanelAnalysis:
        try:
            panel = get_store(request).update_load(
                home_id,
                circuit_id,
                load_id,
                load_input,
            )
            return calculate_panel(panel)
        except Exception as error:
            raise translate_store_error(error) from error

    @app.delete(
        "/api/circuits/{circuit_id}/loads/{load_id}",
        response_model=PanelAnalysis,
    )
    def delete_load(
        request: Request,
        circuit_id: str,
        load_id: str,
        home_id: str = Query(...),
    ) -> PanelAnalysis:
        try:
            panel = get_store(request).remove_load(
                home_id,
                circuit_id,
                load_id,
            )
            return calculate_panel(panel)
        except Exception as error:
            raise translate_store_error(error) from error

    @app.post("/api/panel/reset", response_model=PanelAnalysis)
    def reset_panel(request: Request, response: Response) -> PanelAnalysis:
        response.headers["X-PanelTwin-Reset"] = "sample-data"
        return calculate_panel(get_store(request).reset())

    return app


app = create_app()
