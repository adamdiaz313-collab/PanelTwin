import { useState } from "react";

import { StatusBadge } from "./StatusBadge";

const numberFormatter = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 2,
});

function TrashIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7m4 4v5m4-5v5" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

function EditIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="m4 20 4.5-1 10-10a2.1 2.1 0 0 0-3-3l-10 10L4 20Zm10-12 3 3" />
    </svg>
  );
}

function ChevronIcon({ expanded }) {
  return (
    <svg
      className={expanded ? "chevron chevron--open" : "chevron"}
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <path d="m8 10 4 4 4-4" />
    </svg>
  );
}

function getWarningText(circuit) {
  if (circuit.overloaded) {
    return `${numberFormatter.format(circuit.peak_running_amps)} A running current exceeds the ${circuit.breaker_rating} A breaker.`;
  }
  if (circuit.load_advisory) {
    return `${numberFormatter.format(circuit.peak_noncontinuous_amps)} A noncontinuous + 125% of ${numberFormatter.format(circuit.peak_continuous_amps)} A continuous = ${numberFormatter.format(circuit.peak_calculated_load_amps)} A.`;
  }
  return `Running peak is ${numberFormatter.format(circuit.running_utilization_percent)}% of the breaker at ${circuit.peak_period_label} ${circuit.peak_day_type}.`;
}

function periodText(periods) {
  if (!periods.length) return "off";
  return periods
    .map((item) => `${item.start_time}-${item.end_time}`)
    .join(", ");
}

function CircuitLoads({
  circuit,
  onEditLoad,
  onDeleteLoad,
  busy,
  readOnly = false,
}) {
  if (!circuit.loads.length) {
    return (
      <div className="empty-loads">
        No connected loads yet. Add equipment to generate a demand profile.
      </div>
    );
  }

  return (
    <div className="load-list load-list--detailed">
      {circuit.loads.map((load) => (
        <article className="load-item load-item--detailed" key={load.id}>
          <div className="load-item__identity">
            <span className="load-symbol" aria-hidden="true">
              {load.continuous ? "C" : "N"}
            </span>
            <div>
              <strong>{load.name}</strong>
              <small>
                Weekday: {periodText(load.weekday_periods)}
              </small>
              <small>
                Weekend: {periodText(load.weekend_periods)}
              </small>
              <span
                className={`quality-badge quality-badge--${load.data_quality.toLowerCase()}`}
              >
                {load.data_quality}
              </span>
            </div>
          </div>
          <dl className="load-item__metrics load-item__metrics--wide">
            <div>
              <dt>Real</dt>
              <dd>{numberFormatter.format(load.real_power_watts)} W</dd>
            </div>
            <div>
              <dt>Apparent</dt>
              <dd>{numberFormatter.format(load.apparent_power_va)} VA</dd>
            </div>
            <div>
              <dt>Running</dt>
              <dd>{numberFormatter.format(load.running_current_amps)} A</dd>
            </div>
            <div>
              <dt>Branch calc.</dt>
              <dd>{numberFormatter.format(load.breaker_calculation_amps)} A</dd>
            </div>
            <div>
              <dt>Startup</dt>
              <dd>
                {numberFormatter.format(load.startup_current_amps)} A /{" "}
                {numberFormatter.format(load.inrush_duration_seconds)} s
              </dd>
            </div>
            <div>
              <dt>Monthly</dt>
              <dd>{numberFormatter.format(load.monthly_kwh)} kWh</dd>
            </div>
          </dl>
          <details className="load-calculation">
            <summary>Equations and assumptions</summary>
            <p>
              Apparent power = {numberFormatter.format(load.real_power_watts)} W
              / PF {numberFormatter.format(load.power_factor)} ={" "}
              {numberFormatter.format(load.apparent_power_va)} VA.
            </p>
            <p>
              Running current = {numberFormatter.format(load.apparent_power_va)}
              VA / {load.voltage} V ={" "}
              {numberFormatter.format(load.running_current_amps)} A.
            </p>
            <p>
              Branch load = running current x{" "}
              {load.continuous ? "125% (continuous)" : "100% (noncontinuous)"}.
            </p>
            <p>
              Startup = running current x{" "}
              {numberFormatter.format(load.inrush_multiplier)} for{" "}
              {numberFormatter.format(load.inrush_duration_seconds)} seconds;
              it is not included in 15-minute demand.
            </p>
            <p>
              Monthly energy uses {numberFormatter.format(load.weekday_hours)}
              weekday h/day x 22 and{" "}
              {numberFormatter.format(load.weekend_hours)} weekend h/day x 8.
            </p>
          </details>
          <div className="load-item__actions">
            <button
              className="icon-button"
              type="button"
              onClick={() => onEditLoad(circuit, load)}
              disabled={busy || readOnly}
              title={readOnly ? "Editing is disabled in the live demo." : ""}
              aria-label={`Edit ${load.name}`}
            >
              <EditIcon />
            </button>
            <button
              className="icon-button icon-button--danger"
              type="button"
              onClick={() => onDeleteLoad(circuit, load)}
              disabled={busy || readOnly}
              title={readOnly ? "Editing is disabled in the live demo." : ""}
              aria-label={`Remove ${load.name}`}
            >
              <TrashIcon />
            </button>
          </div>
        </article>
      ))}
    </div>
  );
}

export function CircuitTable({
  circuits,
  onAddLoad,
  onEditCircuit,
  onDeleteCircuit,
  onEditLoad,
  onDeleteLoad,
  busy,
  readOnly = false,
}) {
  const [expandedIds, setExpandedIds] = useState(() => new Set());

  function toggleCircuit(circuitId) {
    setExpandedIds((current) => {
      const next = new Set(current);
      if (next.has(circuitId)) next.delete(circuitId);
      else next.add(circuitId);
      return next;
    });
  }

  if (!circuits.length) {
    return (
      <div className="empty-panel">
        <span className="empty-panel__mark">+</span>
        <h3>This home has an empty panel</h3>
        <p>Add a breaker circuit to begin the 15-minute simulation.</p>
      </div>
    );
  }

  return (
    <div className="circuit-table">
      <div
        className="circuit-table__head circuit-table__head--twin"
        aria-hidden="true"
      >
        <span>Circuit / breaker</span>
        <span>Leg</span>
        <span>Loads</span>
        <span>Peak running</span>
        <span>Calculated load</span>
        <span>Startup transient</span>
        <span>Normal status</span>
        <span>Actions</span>
      </div>

      {circuits.map((circuit, index) => {
        const expanded = expandedIds.has(circuit.id);
        return (
          <article
            className={`circuit-entry circuit-entry--${circuit.status}`}
            key={circuit.id}
          >
            <div className="circuit-row circuit-row--twin">
              <button
                className="circuit-identity"
                type="button"
                onClick={() => toggleCircuit(circuit.id)}
                aria-expanded={expanded}
                aria-controls={`loads-${circuit.id}`}
              >
                <span className="breaker-number">{index + 1}</span>
                <span>
                  <strong>{circuit.name}</strong>
                  <small>
                    {circuit.voltage}V / {circuit.breaker_rating}A{" "}
                    {circuit.voltage === 240 ? "double-pole" : "single-pole"}
                  </small>
                </span>
                <ChevronIcon expanded={expanded} />
              </button>

              <span
                className={`leg-badge leg-badge--${circuit.leg.toLowerCase()}`}
              >
                {circuit.leg === "AB" ? "A + B" : `Leg ${circuit.leg}`}
              </span>

              <div className="circuit-load-count">
                <strong>{circuit.loads.length}</strong>
                <span>{circuit.loads.length === 1 ? "load" : "loads"}</span>
              </div>

              <div className="circuit-value">
                <strong>
                  {numberFormatter.format(circuit.peak_running_amps)}
                </strong>
                <span>
                  A / {numberFormatter.format(circuit.running_utilization_percent)}%
                </span>
              </div>

              <div className="circuit-value">
                <strong>
                  {numberFormatter.format(circuit.peak_calculated_load_amps)}
                </strong>
                <span>
                  A / {numberFormatter.format(circuit.calculated_load_utilization_percent)}%
                </span>
              </div>

              <div className="transient-cell">
                <strong>
                  {numberFormatter.format(circuit.transient_peak_amps)} A
                </strong>
                <span>
                  {circuit.transient_advisory
                    ? "Transient advisory"
                    : "No transient advisory"}
                </span>
              </div>

              <div className="status-cell">
                <StatusBadge status={circuit.status} />
                <small>{getWarningText(circuit)}</small>
              </div>

              <div className="circuit-actions">
                <button
                  className="small-button"
                  type="button"
                  onClick={() => onAddLoad(circuit)}
                  disabled={busy || readOnly}
                  title={readOnly ? "Editing is disabled in the live demo." : ""}
                >
                  <PlusIcon />
                  Load
                </button>
                <button
                  className="icon-button"
                  type="button"
                  onClick={() => onEditCircuit(circuit)}
                  disabled={busy || readOnly}
                  title={readOnly ? "Editing is disabled in the live demo." : ""}
                  aria-label={`Edit ${circuit.name}`}
                >
                  <EditIcon />
                </button>
                <button
                  className="icon-button icon-button--danger"
                  type="button"
                  onClick={() => onDeleteCircuit(circuit)}
                  disabled={busy || readOnly}
                  title={readOnly ? "Editing is disabled in the live demo." : ""}
                  aria-label={`Remove ${circuit.name}`}
                >
                  <TrashIcon />
                </button>
              </div>
            </div>

            {expanded && (
              <div className="circuit-details" id={`loads-${circuit.id}`}>
                <div className="circuit-details__heading">
                  <div>
                    <span className="section-kicker">Scheduled equipment</span>
                    <h3>{circuit.name} loads</h3>
                  </div>
                  <div className="continuous-summary">
                    <span>Normal breaker calculation</span>
                    <strong>
                      {numberFormatter.format(circuit.peak_noncontinuous_amps)}
                      A + 125% x{" "}
                      {numberFormatter.format(circuit.peak_continuous_amps)}A
                    </strong>
                    <small>
                      ={" "}
                      {numberFormatter.format(
                        circuit.peak_calculated_load_amps,
                      )}{" "}
                      A versus a {circuit.breaker_rating} A breaker
                    </small>
                  </div>
                </div>
                <CircuitLoads
                  circuit={circuit}
                  onEditLoad={onEditLoad}
                  onDeleteLoad={onDeleteLoad}
                  busy={busy}
                  readOnly={readOnly}
                />
              </div>
            )}
          </article>
        );
      })}
    </div>
  );
}
