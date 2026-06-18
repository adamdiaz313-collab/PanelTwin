import pytest

from app.calculations import (
    calculate_circuit,
    calculate_load,
    calculate_panel,
    load_is_active,
)
from app.models import (
    Circuit,
    ElectricalLoad,
    Home,
    LoadInput,
    PanelState,
    SchedulePeriod,
)


def period(start: str = "08:00", end: str = "09:00") -> SchedulePeriod:
    return SchedulePeriod(start_time=start, end_time=end)


def build_load(
    *,
    load_id: str = "load-1",
    circuit_id: str = "circuit-1",
    name: str = "Test load",
    wattage: float,
    voltage: int = 120,
    continuous: bool = False,
    power_factor: float = 1.0,
    inrush_multiplier: float = 1.0,
    inrush_duration_seconds: float = 0,
    data_quality: str = "Estimated",
    weekday_periods: list[SchedulePeriod] | None = None,
    weekend_periods: list[SchedulePeriod] | None = None,
) -> ElectricalLoad:
    return ElectricalLoad(
        id=load_id,
        circuit_id=circuit_id,
        name=name,
        wattage=wattage,
        voltage=voltage,
        continuous=continuous,
        power_factor=power_factor,
        inrush_multiplier=inrush_multiplier,
        inrush_duration_seconds=inrush_duration_seconds,
        data_quality=data_quality,
        weekday_periods=weekday_periods or [period()],
        weekend_periods=weekend_periods or [],
    )


def build_circuit(
    loads: list[ElectricalLoad],
    *,
    circuit_id: str = "circuit-1",
    voltage: int = 120,
    breaker_rating: int = 20,
    leg: str = "A",
) -> Circuit:
    return Circuit(
        id=circuit_id,
        panel_id="panel-1",
        name="Test circuit",
        voltage=voltage,
        breaker_rating=breaker_rating,
        leg=leg,
        loads=loads,
    )


def build_panel(circuits: list[Circuit], rating: int = 200) -> PanelState:
    return PanelState(
        home=Home(
            id="home-1",
            panel_id="panel-1",
            name="Test home",
            address="",
        ),
        electricity_rate=0.20,
        main_service_rating=rating,
        circuits=circuits,
    )


def test_real_apparent_power_and_running_current_formula() -> None:
    load = build_load(wattage=2400, voltage=240, power_factor=0.8)

    result = calculate_load(load, electricity_rate=0.20)

    assert result.real_power_watts == 2400
    assert result.apparent_power_va == 3000
    assert result.running_current_amps == 12.5


def test_startup_current_is_running_current_times_multiplier() -> None:
    load = build_load(
        wattage=1200,
        inrush_multiplier=4,
        inrush_duration_seconds=1.5,
    )

    result = calculate_load(load, electricity_rate=0.20)

    assert result.running_current_amps == 10
    assert result.startup_current_amps == 40
    assert result.inrush_extra_amps == 30
    assert result.inrush_duration_seconds == 1.5


def test_continuous_load_uses_125_percent_in_breaker_calculation() -> None:
    load = build_load(wattage=1200, continuous=True)

    result = calculate_load(load, electricity_rate=0.20)

    assert result.running_current_amps == 10
    assert result.breaker_calculation_amps == 12.5


def test_noncontinuous_load_uses_100_percent_in_breaker_calculation() -> None:
    load = build_load(wattage=1200, continuous=False)

    result = calculate_load(load, electricity_rate=0.20)

    assert result.breaker_calculation_amps == 10


def test_15_minute_schedule_boundaries() -> None:
    load = build_load(
        wattage=1000,
        weekday_periods=[period("08:15", "08:45")],
    )

    assert load_is_active(load, "weekday", 8 * 60) is False
    assert load_is_active(load, "weekday", 8 * 60 + 15) is True
    assert load_is_active(load, "weekday", 8 * 60 + 30) is True
    assert load_is_active(load, "weekday", 8 * 60 + 45) is False


def test_multiple_operating_periods_are_supported() -> None:
    load = build_load(
        wattage=1000,
        weekday_periods=[
            period("06:00", "07:00"),
            period("18:00", "19:30"),
        ],
    )

    result = calculate_load(load, electricity_rate=0.20)

    assert result.weekday_hours == 2.5
    assert load_is_active(load, "weekday", 6 * 60 + 30)
    assert load_is_active(load, "weekday", 18 * 60 + 15)
    assert not load_is_active(load, "weekday", 12 * 60)


def test_weekday_and_weekend_schedules_are_distinct() -> None:
    load = build_load(
        wattage=1000,
        weekday_periods=[period("08:00", "09:00")],
        weekend_periods=[period("10:00", "12:00")],
    )

    assert load_is_active(load, "weekday", 8 * 60)
    assert not load_is_active(load, "weekend", 8 * 60)
    assert load_is_active(load, "weekend", 10 * 60)


def test_overnight_period_wraps_across_midnight() -> None:
    load = build_load(
        wattage=1000,
        weekday_periods=[period("22:00", "02:00")],
    )

    assert load_is_active(load, "weekday", 23 * 60)
    assert load_is_active(load, "weekday", 60)
    assert not load_is_active(load, "weekday", 12 * 60)


def test_full_day_period_uses_equal_start_and_end() -> None:
    load = build_load(
        wattage=100,
        weekday_periods=[period("00:00", "00:00")],
    )

    result = calculate_load(load, electricity_rate=0.20)

    assert result.weekday_hours == 24
    assert load_is_active(load, "weekday", 0)
    assert load_is_active(load, "weekday", 23 * 60 + 45)


def test_schedule_times_must_align_to_15_minutes() -> None:
    with pytest.raises(ValueError, match="15-minute"):
        SchedulePeriod(start_time="08:10", end_time="09:00")


def test_overlapping_periods_are_rejected() -> None:
    with pytest.raises(ValueError, match="cannot overlap"):
        LoadInput(
            name="Overlap",
            wattage=1000,
            voltage=120,
            weekday_periods=[
                period("08:00", "10:00"),
                period("09:30", "11:00"),
            ],
        )


def test_load_requires_at_least_one_schedule_period() -> None:
    with pytest.raises(ValueError, match="at least one"):
        LoadInput(
            name="Never on",
            wattage=1000,
            voltage=120,
        )


def test_inrush_multiplier_requires_positive_duration() -> None:
    with pytest.raises(ValueError, match="duration"):
        LoadInput(
            name="Motor",
            wattage=1000,
            voltage=120,
            inrush_multiplier=3,
            inrush_duration_seconds=0,
            weekday_periods=[period()],
        )


def test_monthly_energy_uses_22_weekdays_and_8_weekend_days() -> None:
    load = build_load(
        wattage=1000,
        weekday_periods=[period("08:00", "10:00")],
        weekend_periods=[period("08:00", "11:00")],
    )

    result = calculate_load(load, electricity_rate=0.20)

    assert result.monthly_kwh == 68
    assert result.average_daily_kwh == pytest.approx(68 / 30, abs=0.001)
    assert result.monthly_cost == 13.6


def test_calculated_load_combines_noncontinuous_plus_125_percent_continuous() -> None:
    continuous = build_load(
        load_id="continuous",
        wattage=960,
        continuous=True,
    )
    noncontinuous = build_load(
        load_id="noncontinuous",
        wattage=600,
        continuous=False,
    )
    circuit = build_circuit([continuous, noncontinuous], breaker_rating=20)

    result = calculate_circuit(circuit, electricity_rate=0.20)

    assert result.peak_running_amps == 13
    assert result.peak_continuous_amps == 8
    assert result.peak_noncontinuous_amps == 5
    assert result.peak_calculated_load_amps == 15


def test_calculated_load_over_rating_is_advisory_not_overload() -> None:
    load = build_load(
        wattage=1560,
        continuous=True,
    )
    circuit = build_circuit([load], breaker_rating=15)

    result = calculate_circuit(circuit, electricity_rate=0.20)

    assert result.peak_running_amps == 13
    assert result.peak_calculated_load_amps == 16.25
    assert result.load_advisory is True
    assert result.overloaded is False
    assert result.status == "advisory"


def test_calculated_load_equal_to_rating_is_safe() -> None:
    load = build_load(
        wattage=1440,
        continuous=True,
    )
    circuit = build_circuit([load], breaker_rating=15)

    result = calculate_circuit(circuit, electricity_rate=0.20)

    assert result.peak_running_amps == 12
    assert result.peak_calculated_load_amps == 15
    assert result.status == "safe"


def test_running_current_over_rating_is_overload() -> None:
    load = build_load(wattage=2000)
    circuit = build_circuit([load], breaker_rating=15)

    result = calculate_circuit(circuit, electricity_rate=0.20)

    assert result.peak_running_amps == pytest.approx(16.667, abs=0.001)
    assert result.overloaded is True
    assert result.status == "overloaded"


def test_startup_advisory_does_not_change_normal_circuit_status() -> None:
    load = build_load(
        wattage=1200,
        inrush_multiplier=4,
        inrush_duration_seconds=1,
    )
    circuit = build_circuit([load], breaker_rating=20)

    result = calculate_circuit(circuit, electricity_rate=0.20)

    assert result.peak_running_amps == 10
    assert result.transient_peak_amps == 40
    assert result.transient_advisory is True
    assert result.status == "safe"


def test_inrush_is_not_added_to_15_minute_demand_or_service_utilization() -> None:
    load = build_load(
        wattage=1200,
        inrush_multiplier=10,
        inrush_duration_seconds=0.5,
    )
    circuit = build_circuit([load], breaker_rating=50)

    result = calculate_panel(build_panel([circuit], rating=100))

    assert result.weekday_demand[32].leg_a_amps == 10
    assert result.summary.leg_a_current == 10
    assert result.summary.main_service_utilization_percent == 10
    assert result.transient_events[0].transient_current_amps == 100


def test_multiplier_one_creates_no_transient_event() -> None:
    circuit = build_circuit([build_load(wattage=1200)])

    result = calculate_panel(build_panel([circuit]))

    assert result.transient_events == []
    assert result.summary.transient_advisory_count == 0


def test_simultaneous_combined_inrush_uses_shortest_peak_duration() -> None:
    first = build_load(
        load_id="first",
        wattage=600,
        inrush_multiplier=3,
        inrush_duration_seconds=0.5,
    )
    second = build_load(
        load_id="second",
        wattage=600,
        inrush_multiplier=3,
        inrush_duration_seconds=2,
    )
    circuit = build_circuit([first, second], breaker_rating=20)

    result = calculate_panel(build_panel([circuit]))
    event = result.transient_events[0]

    assert event.running_amps_before_inrush == 10
    assert event.transient_current_amps == 30
    assert event.duration_seconds == 0.5


def test_service_advisory_threshold_uses_running_current() -> None:
    load = build_load(wattage=9600)
    circuit = build_circuit(
        [load],
        breaker_rating=50,
    )

    result = calculate_panel(build_panel([circuit], rating=100))

    assert result.summary.leg_a_current == 80
    assert result.summary.main_service_utilization_percent == 80
    assert result.summary.main_service_status == "advisory"


def test_240v_load_contributes_equal_running_current_to_both_legs() -> None:
    load = build_load(wattage=4800, voltage=240)
    circuit = build_circuit(
        [load],
        voltage=240,
        breaker_rating=30,
        leg="AB",
    )

    result = calculate_panel(build_panel([circuit]))
    point = result.weekday_demand[32]

    assert point.leg_a_amps == 20
    assert point.leg_b_amps == 20
    assert point.neutral_amps == 0


def test_neutral_current_is_difference_between_120v_legs() -> None:
    leg_a = build_circuit(
        [build_load(wattage=1200)],
        circuit_id="circuit-a",
        leg="A",
    )
    leg_b = build_circuit(
        [
            build_load(
                load_id="load-b",
                circuit_id="circuit-b",
                wattage=600,
            )
        ],
        circuit_id="circuit-b",
        leg="B",
    )

    result = calculate_panel(build_panel([leg_a, leg_b]))
    point = result.weekday_demand[32]

    assert point.leg_a_amps == 10
    assert point.leg_b_amps == 5
    assert point.neutral_amps == 5


def test_leg_imbalance_uses_simultaneous_running_currents() -> None:
    leg_a = build_circuit(
        [build_load(wattage=1200)],
        circuit_id="circuit-a",
        leg="A",
    )
    leg_b = build_circuit(
        [
            build_load(
                load_id="load-b1",
                circuit_id="circuit-b",
                wattage=960,
            ),
            build_load(
                load_id="load-b2",
                circuit_id="circuit-b",
                wattage=1200,
                weekday_periods=[period("12:00", "13:00")],
            ),
        ],
        circuit_id="circuit-b",
        leg="B",
    )

    result = calculate_panel(build_panel([leg_a, leg_b]))

    assert result.summary.leg_a_current == 10
    assert result.summary.leg_b_current == 10
    assert result.summary.leg_imbalance_percent == 20


def test_high_power_coincidence_uses_15_minute_intervals() -> None:
    dryer = build_circuit(
        [
            build_load(
                load_id="dryer-load",
                circuit_id="dryer",
                name="Dryer",
                wattage=5000,
                voltage=240,
                weekday_periods=[period("18:00", "18:30")],
            )
        ],
        circuit_id="dryer",
        voltage=240,
        breaker_rating=30,
        leg="AB",
    )
    charger = build_circuit(
        [
            build_load(
                load_id="charger-load",
                circuit_id="charger",
                name="EV charger",
                wattage=7200,
                voltage=240,
                weekday_periods=[period("18:15", "18:45")],
            )
        ],
        circuit_id="charger",
        voltage=240,
        breaker_rating=40,
        leg="AB",
    )

    result = calculate_panel(build_panel([dryer, charger], rating=100))

    assert result.summary.peak_demand_label == "18:15"
    assert result.summary.peak_demand_watts == 12200
    assert result.summary.high_concurrency_count == 1
    assert result.simultaneous_load_warnings[0].load_names == [
        "Dryer",
        "EV charger",
    ]
