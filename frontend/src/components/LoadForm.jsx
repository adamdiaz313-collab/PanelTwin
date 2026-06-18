import { useState } from "react";

const DEFAULT_PERIOD = { start_time: "08:00", end_time: "10:00" };
let nextPeriodId = 0;

function createPeriod(periodValue = DEFAULT_PERIOD) {
  nextPeriodId += 1;
  return { ...periodValue, local_id: `period-${nextPeriodId}` };
}

function timeToMinutes(value) {
  const [hour, minute] = value.split(":").map(Number);
  return hour * 60 + minute;
}

function periodMinutes(period) {
  const start = timeToMinutes(period.start_time);
  const end = timeToMinutes(period.end_time);
  if (start === end) return 24 * 60;
  return end > start ? end - start : 24 * 60 - start + end;
}

function scheduleHours(periods) {
  return periods.reduce((total, item) => total + periodMinutes(item), 0) / 60;
}

function periodSlots(period) {
  const start = timeToMinutes(period.start_time);
  const duration = periodMinutes(period);
  return Array.from(
    { length: duration / 15 },
    (_, index) => (start + index * 15) % (24 * 60),
  );
}

function schedulesOverlap(periods) {
  const occupied = new Set();
  for (const item of periods) {
    for (const slot of periodSlots(item)) {
      if (occupied.has(slot)) return true;
      occupied.add(slot);
    }
  }
  return false;
}

function clonePeriods(periods) {
  return periods.map((item) => createPeriod(item));
}

function defaultForm(circuit, load) {
  if (load) {
    return {
      name: load.name,
      wattage: load.wattage,
      voltage: load.voltage,
      continuous: load.continuous,
      power_factor: load.power_factor,
      inrush_multiplier: load.inrush_multiplier,
      inrush_duration_seconds: load.inrush_duration_seconds,
      data_quality: load.data_quality,
      weekday_periods: clonePeriods(load.weekday_periods),
      weekend_periods: clonePeriods(load.weekend_periods),
      preset_key: load.preset_key ?? "",
    };
  }
  return {
    name: "",
    wattage: 1200,
    voltage: circuit.voltage,
    continuous: false,
    power_factor: 1,
    inrush_multiplier: 1,
    inrush_duration_seconds: 0,
    data_quality: "Estimated",
    weekday_periods: [createPeriod()],
    weekend_periods: [
      createPeriod({ start_time: "09:00", end_time: "11:00" }),
    ],
    preset_key: "",
  };
}

function PeriodEditor({
  label,
  periods,
  onChange,
}) {
  function updatePeriod(index, field, value) {
    onChange(
      periods.map((item, itemIndex) =>
        itemIndex === index ? { ...item, [field]: value } : item,
      ),
    );
  }

  function removePeriod(index) {
    onChange(periods.filter((_, itemIndex) => itemIndex !== index));
  }

  return (
    <section
      className="schedule-editor field--full"
      aria-label={label}
    >
      <div className="schedule-editor__heading">
        <div>
          <strong>{label}</strong>
          <small>
            {periods.length
              ? `${scheduleHours(periods).toFixed(2)} scheduled h/day`
              : "No operation scheduled"}
          </small>
        </div>
        <button
          className="small-button"
          type="button"
          onClick={() => onChange([...periods, createPeriod()])}
          disabled={periods.length >= 16}
        >
          + Period
        </button>
      </div>
      <div className="schedule-periods">
        {periods.map((item, index) => (
          <div
            className="schedule-period"
            key={item.local_id}
          >
            <label>
              <span>Start</span>
              <input
                type="time"
                step="900"
                value={item.start_time}
                onChange={(event) =>
                  updatePeriod(index, "start_time", event.target.value)
                }
                required
              />
            </label>
            <label>
              <span>End</span>
              <input
                type="time"
                step="900"
                value={item.end_time}
                onChange={(event) =>
                  updatePeriod(index, "end_time", event.target.value)
                }
                required
              />
            </label>
            <span className="schedule-period__duration">
              {(periodMinutes(item) / 60).toFixed(2)} h
            </span>
            <button
              className="icon-button icon-button--danger"
              type="button"
              onClick={() => removePeriod(index)}
              aria-label={`Remove ${label.toLowerCase()} period ${index + 1}`}
            >
              x
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}

export function LoadForm({
  circuit,
  load,
  presets,
  onSubmit,
  onCancel,
  busy,
}) {
  const [form, setForm] = useState(() => defaultForm(circuit, load));

  const watts = Number(form.wattage) || 0;
  const voltage = Number(form.voltage) || circuit.voltage;
  const powerFactor = Number(form.power_factor) || 1;
  const multiplier = Number(form.inrush_multiplier) || 1;
  const duration = Number(form.inrush_duration_seconds) || 0;
  const apparentPower = watts / powerFactor;
  const runningAmps = apparentPower / voltage;
  const startupAmps = runningAmps * multiplier;
  const breakerAmps = runningAmps * (form.continuous ? 1.25 : 1);
  const weekdayHours = scheduleHours(form.weekday_periods);
  const weekendHours = scheduleHours(form.weekend_periods);
  const monthlyKwh =
    (watts / 1000) * (weekdayHours * 22 + weekendHours * 8);
  const voltageMismatch = Number(form.voltage) !== circuit.voltage;
  const scheduleMissing =
    !form.weekday_periods.length && !form.weekend_periods.length;
  const scheduleOverlap =
    schedulesOverlap(form.weekday_periods) ||
    schedulesOverlap(form.weekend_periods);
  const inrushInvalid = multiplier > 1 && duration <= 0;

  function updateField(event) {
    const { name, type, value, checked } = event.target;
    setForm((current) => ({
      ...current,
      [name]:
        type === "checkbox"
          ? checked
          : ["name", "preset_key", "data_quality"].includes(name)
            ? value
            : Number(value),
    }));
  }

  function applyPreset(event) {
    const preset = presets.find((item) => item.key === event.target.value);
    if (!preset) {
      setForm((current) => ({ ...current, preset_key: "" }));
      return;
    }
    setForm({
      name: preset.name,
      wattage: preset.wattage,
      voltage: preset.voltage,
      continuous: preset.continuous,
      power_factor: preset.power_factor,
      inrush_multiplier: preset.inrush_multiplier,
      inrush_duration_seconds: preset.inrush_duration_seconds,
      data_quality: preset.data_quality,
      weekday_periods: clonePeriods(preset.weekday_periods),
      weekend_periods: clonePeriods(preset.weekend_periods),
      preset_key: preset.key,
    });
  }

  async function handleSubmit(event) {
    event.preventDefault();
    await onSubmit({
      ...form,
      name: form.name.trim(),
      preset_key: form.preset_key || null,
      weekday_periods: form.weekday_periods.map(
        ({ start_time, end_time }) => ({ start_time, end_time }),
      ),
      weekend_periods: form.weekend_periods.map(
        ({ start_time, end_time }) => ({ start_time, end_time }),
      ),
    });
  }

  const invalid =
    voltageMismatch ||
    scheduleMissing ||
    scheduleOverlap ||
    inrushInvalid;

  return (
    <form className="panel-form panel-form--load" onSubmit={handleSubmit}>
      <div className="form-context field--full">
        <span>{load ? "Editing equipment on" : "Adding equipment to"}</span>
        <strong>{circuit.name}</strong>
        <small>
          {circuit.voltage}V / {circuit.breaker_rating}A / Leg {circuit.leg}
        </small>
      </div>

      <label className="field field--full">
        <span>Appliance preset library</span>
        <select value={form.preset_key} onChange={applyPreset}>
          <option value="">Custom load</option>
          {presets.map((preset) => (
            <option value={preset.key} key={preset.key}>
              {preset.category} / {preset.name}
            </option>
          ))}
        </select>
        <small className="field-help">
          Presets are starting estimates. Replace them with nameplate or
          measured values when available.
        </small>
      </label>

      <label className="field field--full">
        <span>Load name</span>
        <input
          name="name"
          value={form.name}
          onChange={updateField}
          placeholder="e.g. Well pump"
          required
          autoFocus
        />
      </label>

      <label className="field">
        <span>Real power</span>
        <div className="input-unit">
          <input
            name="wattage"
            type="number"
            value={form.wattage}
            onChange={updateField}
            min="1"
            max="50000"
            step="1"
            required
          />
          <span>W</span>
        </div>
      </label>

      <label className="field">
        <span>Voltage</span>
        <select name="voltage" value={form.voltage} onChange={updateField}>
          <option value="120">120 V</option>
          <option value="240">240 V</option>
        </select>
      </label>

      <label className="field">
        <span>Power factor</span>
        <input
          name="power_factor"
          type="number"
          value={form.power_factor}
          onChange={updateField}
          min="0.1"
          max="1"
          step="0.01"
          required
        />
      </label>

      <label className="field">
        <span>Data quality</span>
        <select
          name="data_quality"
          value={form.data_quality}
          onChange={updateField}
        >
          <option value="Measured">Measured</option>
          <option value="Manufacturer">Manufacturer</option>
          <option value="Estimated">Estimated</option>
        </select>
        <small className="field-help">
          Measured is strongest; Estimated carries the most uncertainty.
        </small>
      </label>

      <label className="field">
        <span>Inrush multiplier</span>
        <div className="input-unit">
          <input
            name="inrush_multiplier"
            type="number"
            value={form.inrush_multiplier}
            onChange={updateField}
            min="1"
            max="12"
            step="0.1"
            required
          />
          <span>x</span>
        </div>
      </label>

      <label className="field">
        <span>Inrush duration</span>
        <div className="input-unit">
          <input
            name="inrush_duration_seconds"
            type="number"
            value={form.inrush_duration_seconds}
            onChange={updateField}
            min="0"
            max="300"
            step="0.1"
            required
          />
          <span>s</span>
        </div>
      </label>

      <label className="check-field field--full">
        <input
          name="continuous"
          type="checkbox"
          checked={form.continuous}
          onChange={updateField}
        />
        <span className="check-box" aria-hidden="true" />
        <span>
          <strong>Continuous load</strong>
          <small>
            Apply 125% of this load current in the branch-circuit calculation.
          </small>
        </span>
      </label>

      <PeriodEditor
        label="Weekday periods"
        periods={form.weekday_periods}
        onChange={(weekday_periods) =>
          setForm((current) => ({ ...current, weekday_periods }))
        }
      />
      <PeriodEditor
        label="Weekend periods"
        periods={form.weekend_periods}
        onChange={(weekend_periods) =>
          setForm((current) => ({ ...current, weekend_periods }))
        }
      />

      <div className="calculation-preview field--full">
        <div>
          <span>Apparent power</span>
          <strong>{apparentPower.toFixed(0)} VA</strong>
          <small>{watts.toFixed(0)} W / PF {powerFactor.toFixed(2)}</small>
        </div>
        <div>
          <span>Running current</span>
          <strong>{runningAmps.toFixed(1)} A</strong>
          <small>{apparentPower.toFixed(0)} VA / {voltage} V</small>
        </div>
        <div>
          <span>Calculated branch load</span>
          <strong>{breakerAmps.toFixed(1)} A</strong>
          <small>
            {form.continuous ? "Running current x 125%" : "Running current x 100%"}
          </small>
        </div>
        <div>
          <span>Startup transient</span>
          <strong>{startupAmps.toFixed(1)} A</strong>
          <small>{runningAmps.toFixed(1)} A x {multiplier} for {duration} s</small>
        </div>
        <p>
          Monthly energy: {monthlyKwh.toFixed(1)} kWh = kW x
          (weekday hours x 22 + weekend hours x 8).
        </p>
      </div>

      {voltageMismatch && (
        <div className="form-error field--full" role="alert">
          This preset uses {form.voltage}V, but {circuit.name} is a{" "}
          {circuit.voltage}V circuit.
        </div>
      )}
      {scheduleMissing && (
        <div className="form-error field--full" role="alert">
          Add at least one weekday or weekend operating period.
        </div>
      )}
      {scheduleOverlap && (
        <div className="form-error field--full" role="alert">
          Operating periods within the same day type cannot overlap.
        </div>
      )}
      {inrushInvalid && (
        <div className="form-error field--full" role="alert">
          Enter an inrush duration when the multiplier is greater than 1.
        </div>
      )}

      <div className="form-actions field--full">
        <button
          className="button button--ghost"
          type="button"
          onClick={onCancel}
          disabled={busy}
        >
          Cancel
        </button>
        <button
          className="button button--primary"
          type="submit"
          disabled={busy || invalid}
        >
          {busy ? "Saving..." : load ? "Save load" : "Add load"}
        </button>
      </div>
    </form>
  );
}
