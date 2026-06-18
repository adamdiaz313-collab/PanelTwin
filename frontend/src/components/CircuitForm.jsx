import { useState } from "react";

function initialValues(circuit) {
  return circuit
    ? {
        name: circuit.name,
        voltage: circuit.voltage,
        breaker_rating: circuit.breaker_rating,
        leg: circuit.leg,
      }
    : {
        name: "",
        voltage: 120,
        breaker_rating: 15,
        leg: "A",
      };
}

export function CircuitForm({ circuit, onSubmit, onCancel, busy }) {
  const [form, setForm] = useState(() => initialValues(circuit));

  function updateField(event) {
    const { name, value } = event.target;
    setForm((current) => {
      const next = {
        ...current,
        [name]:
          name === "name" || name === "leg" ? value : Number(value),
      };
      if (name === "voltage") {
        next.leg = Number(value) === 240 ? "AB" : "A";
      }
      return next;
    });
  }

  async function handleSubmit(event) {
    event.preventDefault();
    await onSubmit({ ...form, name: form.name.trim() });
  }

  const editing = Boolean(circuit);

  return (
    <form className="panel-form" onSubmit={handleSubmit}>
      <label className="field field--full">
        <span>Circuit name</span>
        <input
          name="name"
          value={form.name}
          onChange={updateField}
          placeholder="e.g. Garage receptacles"
          maxLength="80"
          required
          autoFocus
        />
      </label>

      <label className="field">
        <span>Supply voltage</span>
        <select name="voltage" value={form.voltage} onChange={updateField}>
          <option value="120">120V single-pole</option>
          <option value="240">240V double-pole</option>
        </select>
      </label>

      <label className="field">
        <span>Breaker rating</span>
        <select
          name="breaker_rating"
          value={form.breaker_rating}
          onChange={updateField}
        >
          {[15, 20, 30, 40, 50].map((rating) => (
            <option value={rating} key={rating}>
              {rating} A
            </option>
          ))}
        </select>
      </label>

      <label className="field field--full">
        <span>Panel leg assignment</span>
        <select
          name="leg"
          value={form.leg}
          onChange={updateField}
          disabled={form.voltage === 240}
        >
          {form.voltage === 240 ? (
            <option value="AB">Leg A + Leg B</option>
          ) : (
            <>
              <option value="A">Leg A</option>
              <option value="B">Leg B</option>
            </>
          )}
        </select>
      </label>

      <div className="form-note field--full">
        <strong>
          {form.voltage === 240
            ? "A 240V breaker contributes equal current to both service legs."
            : `This circuit contributes current to Leg ${form.leg}.`}
        </strong>
        <span>
          Existing loads must be removed before changing a circuit to a
          different voltage.
        </span>
      </div>

      <div className="form-actions field--full">
        <button
          className="button button--ghost"
          type="button"
          onClick={onCancel}
          disabled={busy}
        >
          Cancel
        </button>
        <button className="button button--primary" type="submit" disabled={busy}>
          {busy ? "Saving..." : editing ? "Save circuit" : "Add circuit"}
        </button>
      </div>
    </form>
  );
}
