from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

Voltage = Literal[120, 240]
BreakerRating = Literal[15, 20, 30, 40, 50]
MainServiceRating = Literal[100, 150, 200]
PanelLeg = Literal["A", "B", "AB"]
DayType = Literal["weekday", "weekend"]
DataQuality = Literal["Measured", "Manufacturer", "Estimated"]
CircuitStatus = Literal["safe", "advisory", "overloaded"]
ServiceStatus = Literal["safe", "advisory", "overloaded"]

TIME_STEP_MINUTES = 15
MINUTES_PER_DAY = 24 * 60


def time_to_minutes(value: str) -> int:
    hour, minute = (int(part) for part in value.split(":"))
    return hour * 60 + minute


def period_segments(start_time: str, end_time: str) -> list[tuple[int, int]]:
    start = time_to_minutes(start_time)
    end = time_to_minutes(end_time)
    if start == end:
        return [(0, MINUTES_PER_DAY)]
    if end > start:
        return [(start, end)]
    return [(start, MINUTES_PER_DAY), (0, end)]


class NamedModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def reject_blank_name(cls, value: str) -> str:
        if not value:
            raise ValueError("Name cannot be blank.")
        return value


class HomeInput(NamedModel):
    address: str = Field(default="", max_length=160)


class Home(HomeInput):
    id: str
    panel_id: str


class PanelSettingsInput(BaseModel):
    electricity_rate: float = Field(ge=0, le=10)
    main_service_rating: MainServiceRating


class SchedulePeriod(BaseModel):
    start_time: str
    end_time: str

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time(cls, value: str) -> str:
        parts = value.split(":")
        if len(parts) != 2:
            raise ValueError("Time must use HH:MM format.")
        try:
            hour, minute = (int(part) for part in parts)
        except ValueError as exc:
            raise ValueError("Time must use HH:MM format.") from exc
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError("Time must use a valid 24-hour clock value.")
        if minute % TIME_STEP_MINUTES:
            raise ValueError("Times must align to 15-minute intervals.")
        return f"{hour:02d}:{minute:02d}"


def validate_period_list(
    periods: list[SchedulePeriod],
    label: str,
) -> None:
    occupied: set[int] = set()
    for period in periods:
        for segment_start, segment_end in period_segments(
            period.start_time,
            period.end_time,
        ):
            for minute in range(
                segment_start,
                segment_end,
                TIME_STEP_MINUTES,
            ):
                if minute in occupied:
                    raise ValueError(f"{label} operating periods cannot overlap.")
                occupied.add(minute)


class LoadInput(NamedModel):
    wattage: float = Field(gt=0, le=50_000)
    voltage: Voltage
    continuous: bool = False
    power_factor: float = Field(default=1.0, gt=0, le=1)
    inrush_multiplier: float = Field(default=1.0, ge=1, le=12)
    inrush_duration_seconds: float = Field(default=0, ge=0, le=300)
    data_quality: DataQuality = "Estimated"
    weekday_periods: list[SchedulePeriod] = Field(
        default_factory=list,
        max_length=16,
    )
    weekend_periods: list[SchedulePeriod] = Field(
        default_factory=list,
        max_length=16,
    )
    preset_key: str | None = Field(default=None, max_length=60)

    @model_validator(mode="after")
    def validate_schedule_and_inrush(self):
        if not self.weekday_periods and not self.weekend_periods:
            raise ValueError("Add at least one weekday or weekend period.")
        validate_period_list(self.weekday_periods, "Weekday")
        validate_period_list(self.weekend_periods, "Weekend")
        if self.inrush_multiplier > 1 and self.inrush_duration_seconds <= 0:
            raise ValueError(
                "Inrush duration must be greater than zero when the "
                "inrush multiplier exceeds 1."
            )
        return self


class ElectricalLoad(LoadInput):
    id: str
    circuit_id: str


class CircuitInput(NamedModel):
    voltage: Voltage
    breaker_rating: BreakerRating
    leg: PanelLeg

    @model_validator(mode="after")
    def validate_leg_for_voltage(self):
        if self.voltage == 240 and self.leg != "AB":
            raise ValueError("240V circuits must use both legs (AB).")
        if self.voltage == 120 and self.leg not in ("A", "B"):
            raise ValueError("120V circuits must be assigned to Leg A or Leg B.")
        return self


class Circuit(CircuitInput):
    id: str
    panel_id: str
    loads: list[ElectricalLoad] = Field(default_factory=list)


class PanelState(BaseModel):
    home: Home
    electricity_rate: float = Field(default=0.18, ge=0, le=10)
    main_service_rating: MainServiceRating = 200
    circuits: list[Circuit] = Field(default_factory=list)


class LoadAnalysis(ElectricalLoad):
    real_power_watts: float
    apparent_power_va: float
    running_current_amps: float
    startup_current_amps: float
    inrush_extra_amps: float
    breaker_calculation_amps: float
    weekday_hours: float
    weekend_hours: float
    average_daily_kwh: float
    monthly_kwh: float
    monthly_cost: float


class CircuitAnalysis(CircuitInput):
    id: str
    panel_id: str
    connected_watts: float
    connected_va: float
    connected_amps: float
    peak_running_amps: float
    peak_noncontinuous_amps: float
    peak_continuous_amps: float
    peak_calculated_load_amps: float
    running_utilization_percent: float
    calculated_load_utilization_percent: float
    overloaded: bool
    load_advisory: bool
    transient_peak_amps: float
    transient_advisory: bool
    status: CircuitStatus
    peak_period_label: str
    peak_day_type: DayType
    average_daily_kwh: float
    monthly_kwh: float
    monthly_cost: float
    loads: list[LoadAnalysis]


class DemandPoint(BaseModel):
    interval_index: int
    minute_of_day: int
    day_type: DayType
    label: str
    real_power_watts: float
    apparent_power_va: float
    leg_a_amps: float
    leg_b_amps: float
    neutral_amps: float
    active_load_count: int
    high_power_loads: list[str]


class TransientEvent(BaseModel):
    day_type: DayType
    minute_of_day: int
    label: str
    circuit_id: str
    circuit_name: str
    load_names: list[str]
    running_amps_before_inrush: float
    transient_current_amps: float
    breaker_rating: BreakerRating
    duration_seconds: float
    advisory: bool


class SimultaneousLoadWarning(BaseModel):
    day_type: DayType
    minute_of_day: int
    label: str
    load_names: list[str]
    combined_watts: float


class PanelSummary(BaseModel):
    connected_watts: float
    connected_va: float
    leg_a_current: float
    leg_b_current: float
    neutral_current: float
    leg_imbalance_percent: float
    main_service_rating: MainServiceRating
    main_service_utilization_percent: float
    main_service_status: ServiceStatus
    leg_a_status: ServiceStatus
    leg_b_status: ServiceStatus
    peak_demand_watts: float
    peak_demand_label: str
    peak_demand_day_type: DayType
    average_daily_kwh: float
    monthly_kwh: float
    monthly_cost: float
    circuit_count: int
    load_count: int
    safe_count: int
    advisory_count: int
    overloaded_count: int
    transient_advisory_count: int
    high_concurrency_count: int
    leg_unbalanced: bool
    measured_load_count: int
    manufacturer_load_count: int
    estimated_load_count: int


class PanelAnalysis(BaseModel):
    home: Home
    electricity_rate: float
    main_service_rating: MainServiceRating
    summary: PanelSummary
    circuits: list[CircuitAnalysis]
    weekday_demand: list[DemandPoint]
    weekend_demand: list[DemandPoint]
    transient_events: list[TransientEvent]
    simultaneous_load_warnings: list[SimultaneousLoadWarning]


class AppliancePreset(BaseModel):
    key: str
    name: str
    category: str
    wattage: float
    voltage: Voltage
    continuous: bool
    power_factor: float
    inrush_multiplier: float
    inrush_duration_seconds: float
    data_quality: DataQuality = "Estimated"
    weekday_periods: list[SchedulePeriod]
    weekend_periods: list[SchedulePeriod]
