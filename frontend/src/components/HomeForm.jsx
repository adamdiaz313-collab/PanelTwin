import { useState } from "react";

export function HomeForm({ home, onSubmit, onCancel, busy }) {
  const [form, setForm] = useState({
    name: home?.name ?? "",
    address: home?.address ?? "",
  });

  function updateField(event) {
    setForm((current) => ({
      ...current,
      [event.target.name]: event.target.value,
    }));
  }

  function handleSubmit(event) {
    event.preventDefault();
    onSubmit({
      name: form.name.trim(),
      address: form.address.trim(),
    });
  }

  return (
    <form className="panel-form" onSubmit={handleSubmit}>
      <label className="field field--full">
        <span>Home name</span>
        <input
          name="name"
          value={form.name}
          onChange={updateField}
          placeholder="e.g. Diaz residence"
          required
          autoFocus
        />
      </label>
      <label className="field field--full">
        <span>Address or description</span>
        <input
          name="address"
          value={form.address}
          onChange={updateField}
          placeholder="Optional"
        />
      </label>
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
          {busy ? "Saving..." : home ? "Save home" : "Create home"}
        </button>
      </div>
    </form>
  );
}
