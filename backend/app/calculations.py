from dataclasses import dataclass, field

from .models import (
    Circuit,
    CircuitAnalysis,
    CircuitStatus,
    DayType,
    DemandPoint,
    LoadAnalysis,
    MINUTES_PER_DAY,
    PanelAnalysis,
    PanelState,
    PanelSummary,
    SchedulePeriod,
    ServiceStatus,
    SimultaneousLoadWarning,
    TIME_STEP_MINUTES,
    TransientEvent,
    period_segments,
    time_to_minutes,
)

CONTINUOUS_LOAD_FACTOR = 1.25
SERVICE_ADVISORY_PERCENT = 80
LEG_IMBALANCE_WARNING_PERCENT = 20
HIGH_POWER_LOAD_WATTS = 2000
WEEKDAYS_PER_MONTH = 22
WEEKEND_DAYS_PER_MONTH = 8
MONTH_DAYS = WEEKDAYS_PER_MONTH + WEEKEND_DAYS_PER_MONTH
INTERVALS_PER_DAY = MINUTES_PER_DAY // TIME_STEP_MINUTES


def rounded(value: float) -> float:
    return round(value, 3)


def period_duration_minutes(period: SchedulePeriod) -> int:
    start = time_to_minutes(period.start_time)
    end = time_to_minutes(period.end_time)
    if start == end:
        return MINUTES_PER_DAY
    if end > start:
        return end - start
    return MINUTES_PER_DAY - start + end


def schedule_hours(periods: list[SchedulePeriod]) -> float:
    return sum(period_duration_minutes(period) for period in periods) / 60


def periods_for_day(load, day_type: DayType) -> list[SchedulePeriod]:
    return (
        load.weekday_periods
        if day_type == "weekday"
        else load.weekend_periods
    )


def period_contains_minute(period: SchedulePeriod, minute: int) -> bool:
    return any(
        start <= minute < end
        for start, end in period_segments(
            period.start_time,
            period.end_time,
        )
    )


def load_is_active(load, day_type: DayType, minute: int) -> bool:
    return any(
        period_contains_minute(period, minute)
        for period in periods_for_day(load, day_type)
    )


def load_starts_at(load, day_type: DayType, minute: int) -> bool:
    return any(
        time_to_minutes(period.start_time) == minute
        for period in periods_for_day(load, day_type)
    )


def time_label(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def service_status(current: float, rating: int) -> ServiceStatus:
    if current > rating:
        return "overloaded"
    if current / rating * 100 >= SERVICE_ADVISORY_PERCENT:
        return "advisory"
    return "safe"


def determine_circuit_status(
    peak_running_amps: float,
    peak_calculated_load_amps: float,
    breaker_rating: int,
) -> CircuitStatus:
    if peak_running_amps > breaker_rating:
        return "overloaded"
    if peak_calculated_load_amps > breaker_rating:
        return "advisory"
    return "safe"


def calculate_load(load, electricity_rate: float) -> LoadAnalysis:
    apparent_power_va = load.wattage / load.power_factor
    running_current_amps = apparent_power_va / load.voltage
    startup_current_amps = running_current_amps * load.inrush_multiplier
    weekday_hours = schedule_hours(load.weekday_periods)
    weekend_hours = schedule_hours(load.weekend_periods)
    weekday_kwh = load.wattage / 1000 * weekday_hours
    weekend_kwh = load.wattage / 1000 * weekend_hours
    monthly_kwh = (
        weekday_kwh * WEEKDAYS_PER_MONTH
        + weekend_kwh * WEEKEND_DAYS_PER_MONTH
    )

    return LoadAnalysis(
        **load.model_dump(),
        real_power_watts=rounded(load.wattage),
        apparent_power_va=rounded(apparent_power_va),
        running_current_amps=rounded(running_current_amps),
        startup_current_amps=rounded(startup_current_amps),
        inrush_extra_amps=rounded(
            startup_current_amps - running_current_amps
        ),
        breaker_calculation_amps=rounded(
            running_current_amps
            * (CONTINUOUS_LOAD_FACTOR if load.continuous else 1)
        ),
        weekday_hours=rounded(weekday_hours),
        weekend_hours=rounded(weekend_hours),
        average_daily_kwh=rounded(monthly_kwh / MONTH_DAYS),
        monthly_kwh=rounded(monthly_kwh),
        monthly_cost=rounded(monthly_kwh * electricity_rate),
    )


@dataclass
class CircuitInterval:
    minute: int
    running_amps: float = 0
    noncontinuous_amps: float = 0
    continuous_amps: float = 0
    transient_extra_amps: float = 0
    starting_loads: list = field(default_factory=list)

    @property
    def calculated_load_amps(self) -> float:
        return (
            self.noncontinuous_amps
            + CONTINUOUS_LOAD_FACTOR * self.continuous_amps
        )

    @property
    def transient_current_amps(self) -> float:
        return self.running_amps + self.transient_extra_amps


def circuit_profile(
    circuit: Circuit,
    day_type: DayType,
) -> tuple[list[CircuitInterval], list[TransientEvent]]:
    intervals = [
        CircuitInterval(minute=index * TIME_STEP_MINUTES)
        for index in range(INTERVALS_PER_DAY)
    ]

    for load in circuit.loads:
        load_va = load.wattage / load.power_factor
        running_amps = load_va / load.voltage
        for interval in intervals:
            if load_is_active(load, day_type, interval.minute):
                interval.running_amps += running_amps
                if load.continuous:
                    interval.continuous_amps += running_amps
                else:
                    interval.noncontinuous_amps += running_amps
            if (
                load.inrush_multiplier > 1
                and load_starts_at(load, day_type, interval.minute)
            ):
                interval.transient_extra_amps += (
                    running_amps * (load.inrush_multiplier - 1)
                )
                interval.starting_loads.append(load)

    transient_events = []
    for interval in intervals:
        if not interval.starting_loads:
            continue
        transient_events.append(
            TransientEvent(
                day_type=day_type,
                minute_of_day=interval.minute,
                label=time_label(interval.minute),
                circuit_id=circuit.id,
                circuit_name=circuit.name,
                load_names=[load.name for load in interval.starting_loads],
                running_amps_before_inrush=rounded(interval.running_amps),
                transient_current_amps=rounded(
                    interval.transient_current_amps
                ),
                breaker_rating=circuit.breaker_rating,
                duration_seconds=rounded(
                    min(
                        load.inrush_duration_seconds
                        for load in interval.starting_loads
                    )
                ),
                advisory=(
                    interval.transient_current_amps
                    > circuit.breaker_rating
                ),
            )
        )

    return intervals, transient_events


def calculate_circuit(
    circuit: Circuit,
    electricity_rate: float,
) -> CircuitAnalysis:
    analyzed_loads = [
        calculate_load(load, electricity_rate) for load in circuit.loads
    ]
    weekday_profile, weekday_events = circuit_profile(
        circuit,
        "weekday",
    )
    weekend_profile, weekend_events = circuit_profile(
        circuit,
        "weekend",
    )
    all_intervals = [
        ("weekday", interval) for interval in weekday_profile
    ] + [
        ("weekend", interval) for interval in weekend_profile
    ]
    peak_day_type, peak_interval = max(
        all_intervals,
        key=lambda item: item[1].running_amps,
    )
    peak_running = max(
        interval.running_amps for _, interval in all_intervals
    )
    _, calculated_peak_interval = max(
        all_intervals,
        key=lambda item: item[1].calculated_load_amps,
    )
    peak_noncontinuous = calculated_peak_interval.noncontinuous_amps
    peak_continuous = calculated_peak_interval.continuous_amps
    peak_calculated = calculated_peak_interval.calculated_load_amps
    transient_events = weekday_events + weekend_events
    transient_peak = max(
        (
            event.transient_current_amps
            for event in transient_events
        ),
        default=0,
    )
    status = determine_circuit_status(
        peak_running,
        peak_calculated,
        circuit.breaker_rating,
    )
    monthly_kwh = sum(load.monthly_kwh for load in analyzed_loads)

    return CircuitAnalysis(
        id=circuit.id,
        panel_id=circuit.panel_id,
        name=circuit.name,
        voltage=circuit.voltage,
        breaker_rating=circuit.breaker_rating,
        leg=circuit.leg,
        connected_watts=rounded(sum(load.wattage for load in circuit.loads)),
        connected_va=rounded(
            sum(load.wattage / load.power_factor for load in circuit.loads)
        ),
        connected_amps=rounded(
            sum(
                (load.wattage / load.power_factor) / load.voltage
                for load in circuit.loads
            )
        ),
        peak_running_amps=rounded(peak_running),
        peak_noncontinuous_amps=rounded(peak_noncontinuous),
        peak_continuous_amps=rounded(peak_continuous),
        peak_calculated_load_amps=rounded(peak_calculated),
        running_utilization_percent=rounded(
            peak_running / circuit.breaker_rating * 100
        ),
        calculated_load_utilization_percent=rounded(
            peak_calculated / circuit.breaker_rating * 100
        ),
        overloaded=peak_running > circuit.breaker_rating,
        load_advisory=(
            peak_running <= circuit.breaker_rating
            and peak_calculated > circuit.breaker_rating
        ),
        transient_peak_amps=rounded(transient_peak),
        transient_advisory=any(
            event.advisory for event in transient_events
        ),
        status=status,
        peak_period_label=time_label(peak_interval.minute),
        peak_day_type=peak_day_type,
        average_daily_kwh=rounded(monthly_kwh / MONTH_DAYS),
        monthly_kwh=rounded(monthly_kwh),
        monthly_cost=rounded(monthly_kwh * electricity_rate),
        loads=analyzed_loads,
    )


def calculate_demand_profile(
    panel: PanelState,
    day_type: DayType,
) -> tuple[
    list[DemandPoint],
    list[SimultaneousLoadWarning],
]:
    points: list[DemandPoint] = []
    concurrency_warnings: list[SimultaneousLoadWarning] = []

    for index in range(INTERVALS_PER_DAY):
        minute = index * TIME_STEP_MINUTES
        real_watts = 0.0
        apparent_va = 0.0
        leg_a_amps = 0.0
        leg_b_amps = 0.0
        neutral_a_amps = 0.0
        neutral_b_amps = 0.0
        active_load_count = 0
        high_power_names: list[str] = []
        high_power_watts = 0.0

        for circuit in panel.circuits:
            for load in circuit.loads:
                if not load_is_active(load, day_type, minute):
                    continue
                load_va = load.wattage / load.power_factor
                current = load_va / load.voltage
                real_watts += load.wattage
                apparent_va += load_va
                active_load_count += 1
                if load.wattage >= HIGH_POWER_LOAD_WATTS:
                    high_power_names.append(load.name)
                    high_power_watts += load.wattage

                if circuit.voltage == 240:
                    leg_a_amps += current
                    leg_b_amps += current
                elif circuit.leg == "A":
                    leg_a_amps += current
                    neutral_a_amps += current
                else:
                    leg_b_amps += current
                    neutral_b_amps += current

        label = time_label(minute)
        points.append(
            DemandPoint(
                interval_index=index,
                minute_of_day=minute,
                day_type=day_type,
                label=label,
                real_power_watts=rounded(real_watts),
                apparent_power_va=rounded(apparent_va),
                leg_a_amps=rounded(leg_a_amps),
                leg_b_amps=rounded(leg_b_amps),
                neutral_amps=rounded(
                    abs(neutral_a_amps - neutral_b_amps)
                ),
                active_load_count=active_load_count,
                high_power_loads=high_power_names,
            )
        )

        if len(high_power_names) >= 2:
            concurrency_warnings.append(
                SimultaneousLoadWarning(
                    day_type=day_type,
                    minute_of_day=minute,
                    label=label,
                    load_names=high_power_names,
                    combined_watts=rounded(high_power_watts),
                )
            )

    return points, concurrency_warnings


def calculate_panel(panel: PanelState) -> PanelAnalysis:
    circuits = [
        calculate_circuit(circuit, panel.electricity_rate)
        for circuit in panel.circuits
    ]
    weekday_demand, weekday_warnings = calculate_demand_profile(
        panel,
        "weekday",
    )
    weekend_demand, weekend_warnings = calculate_demand_profile(
        panel,
        "weekend",
    )
    all_points = weekday_demand + weekend_demand
    concurrency_warnings = weekday_warnings + weekend_warnings
    transient_events = []
    for circuit in panel.circuits:
        for day_type in ("weekday", "weekend"):
            _, events = circuit_profile(circuit, day_type)
            transient_events.extend(events)

    peak_point = max(
        all_points,
        key=lambda point: point.real_power_watts,
    )
    leg_a_peak = max(point.leg_a_amps for point in all_points)
    leg_b_peak = max(point.leg_b_amps for point in all_points)
    neutral_peak = max(point.neutral_amps for point in all_points)
    service_peak_point = max(
        all_points,
        key=lambda point: max(point.leg_a_amps, point.leg_b_amps),
    )
    larger_leg = max(leg_a_peak, leg_b_peak)
    service_peak_larger_leg = max(
        service_peak_point.leg_a_amps,
        service_peak_point.leg_b_amps,
    )
    imbalance_percent = (
        abs(
            service_peak_point.leg_a_amps
            - service_peak_point.leg_b_amps
        )
        / service_peak_larger_leg
        * 100
        if service_peak_larger_leg
        else 0
    )
    main_utilization = (
        larger_leg / panel.main_service_rating * 100
        if panel.main_service_rating
        else 0
    )
    monthly_kwh = sum(circuit.monthly_kwh for circuit in circuits)
    loads = [
        load
        for circuit in panel.circuits
        for load in circuit.loads
    ]

    return PanelAnalysis(
        home=panel.home,
        electricity_rate=panel.electricity_rate,
        main_service_rating=panel.main_service_rating,
        summary=PanelSummary(
            connected_watts=rounded(
                sum(circuit.connected_watts for circuit in circuits)
            ),
            connected_va=rounded(
                sum(circuit.connected_va for circuit in circuits)
            ),
            leg_a_current=rounded(leg_a_peak),
            leg_b_current=rounded(leg_b_peak),
            neutral_current=rounded(neutral_peak),
            leg_imbalance_percent=rounded(imbalance_percent),
            main_service_rating=panel.main_service_rating,
            main_service_utilization_percent=rounded(main_utilization),
            main_service_status=service_status(
                larger_leg,
                panel.main_service_rating,
            ),
            leg_a_status=service_status(
                leg_a_peak,
                panel.main_service_rating,
            ),
            leg_b_status=service_status(
                leg_b_peak,
                panel.main_service_rating,
            ),
            peak_demand_watts=peak_point.real_power_watts,
            peak_demand_label=peak_point.label,
            peak_demand_day_type=peak_point.day_type,
            average_daily_kwh=rounded(monthly_kwh / MONTH_DAYS),
            monthly_kwh=rounded(monthly_kwh),
            monthly_cost=rounded(monthly_kwh * panel.electricity_rate),
            circuit_count=len(circuits),
            load_count=len(loads),
            safe_count=sum(circuit.status == "safe" for circuit in circuits),
            advisory_count=sum(
                circuit.status == "advisory" for circuit in circuits
            ),
            overloaded_count=sum(
                circuit.status == "overloaded" for circuit in circuits
            ),
            transient_advisory_count=sum(
                event.advisory for event in transient_events
            ),
            high_concurrency_count=len(concurrency_warnings),
            leg_unbalanced=(
                imbalance_percent >= LEG_IMBALANCE_WARNING_PERCENT
            ),
            measured_load_count=sum(
                load.data_quality == "Measured" for load in loads
            ),
            manufacturer_load_count=sum(
                load.data_quality == "Manufacturer" for load in loads
            ),
            estimated_load_count=sum(
                load.data_quality == "Estimated" for load in loads
            ),
        ),
        circuits=circuits,
        weekday_demand=weekday_demand,
        weekend_demand=weekend_demand,
        transient_events=transient_events,
        simultaneous_load_warnings=concurrency_warnings,
    )
