import { useCallback, useEffect, useState } from "react";

import { panelApi } from "./api";
import { Charts } from "./components/Charts";
import { CircuitForm } from "./components/CircuitForm";
import { CircuitTable } from "./components/CircuitTable";
import { DashboardCards } from "./components/DashboardCards";
import { HomeForm } from "./components/HomeForm";
import { LoadForm } from "./components/LoadForm";
import { Modal } from "./components/Modal";

const SELECTED_HOME_KEY = "paneltwin-selected-home";
const READ_ONLY_DEMO_MESSAGE =
  "The GitHub Pages demo is read-only. Run the FastAPI backend locally for editing and SQLite persistence.";

function BoltIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M13.1 2 5.8 13h5.1L10.2 22l8-12h-5.1l0-8Z" />
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

function ResetIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4.9 7.7A8 8 0 1 1 4 14M4 4v5h5" />
    </svg>
  );
}

function LoadingScreen() {
  return (
    <main className="loading-screen">
      <span className="loading-mark">
        <BoltIcon />
      </span>
      <strong>Starting the time-based digital twin</strong>
      <p>Loading the persistent panel model and 15-minute profiles...</p>
    </main>
  );
}

function WarningCenter({ panel }) {
  const normalWarnings = [];
  const { summary } = panel;

  if (summary.main_service_status !== "safe") {
    normalWarnings.push({
      level: summary.main_service_status,
      title: `Main service running demand is ${summary.main_service_status}`,
      body: `${summary.main_service_utilization_percent.toFixed(1)}% = max running leg current / ${summary.main_service_rating} A. Startup transients are excluded.`,
    });
  }
  if (summary.leg_unbalanced) {
    normalWarnings.push({
      level: "advisory",
      title: "Service legs are unbalanced",
      body: `Legs differ by ${summary.leg_imbalance_percent.toFixed(1)}%; estimated neutral running current peaks at ${summary.neutral_current.toFixed(1)} A.`,
    });
  }
  if (summary.high_concurrency_count) {
    normalWarnings.push({
      level: "advisory",
      title: "High-power loads overlap",
      body: `${summary.high_concurrency_count} 15-minute interval${summary.high_concurrency_count === 1 ? "" : "s"} contain multiple loads rated at 2 kW or more.`,
    });
  }
  panel.circuits
    .filter((circuit) => circuit.status !== "safe")
    .forEach((circuit) => {
      normalWarnings.push({
        level: circuit.status,
        title: `${circuit.name}: ${circuit.status === "overloaded" ? "normal running overload" : "branch-load advisory"}`,
        body:
          circuit.status === "overloaded"
            ? `${circuit.peak_running_amps.toFixed(1)} A running current exceeds the ${circuit.breaker_rating} A breaker.`
            : `${circuit.peak_noncontinuous_amps.toFixed(1)} A noncontinuous + 125% of ${circuit.peak_continuous_amps.toFixed(1)} A continuous = ${circuit.peak_calculated_load_amps.toFixed(1)} A.`,
      });
    });

  const transientWarnings = panel.transient_events.filter(
    (event) => event.advisory,
  );

  if (!normalWarnings.length && !transientWarnings.length) return null;

  return (
    <div className="warning-groups">
      {normalWarnings.length > 0 && (
        <section className="warning-center" aria-label="Normal load warnings">
          <div className="warning-center__heading">
            <span className="warning-strip__icon">!</span>
            <div>
              <strong>
                {normalWarnings.length} normal-load warning
                {normalWarnings.length === 1 ? "" : "s"}
              </strong>
              <p>
                Based on running current and noncontinuous + 125% continuous
                branch-load calculations.
              </p>
            </div>
          </div>
          <div className="warning-center__list">
            {normalWarnings.map((warning) => (
              <article
                className={`warning-chip warning-chip--${warning.level}`}
                key={`${warning.title}-${warning.body}`}
              >
                <strong>{warning.title}</strong>
                <span>{warning.body}</span>
              </article>
            ))}
          </div>
        </section>
      )}

      {transientWarnings.length > 0 && (
        <section
          className="warning-center warning-center--transient"
          aria-label="Startup transient advisories"
        >
          <div className="warning-center__heading">
            <span className="warning-strip__icon">T</span>
            <div>
              <strong>
                {transientWarnings.length} startup transient advisor
                {transientWarnings.length === 1 ? "y" : "ies"}
              </strong>
              <p>
                These short events are not counted as normal overloads or
                service utilization.
              </p>
            </div>
          </div>
          <div className="warning-center__list">
            {transientWarnings.slice(0, 8).map((event) => (
              <article
                className="warning-chip warning-chip--transient"
                key={`${event.day_type}-${event.circuit_id}-${event.minute_of_day}`}
              >
                <strong>
                  {event.circuit_name} / {event.day_type} {event.label}
                </strong>
                <span>
                  {event.transient_current_amps.toFixed(1)} A for about{" "}
                  {event.duration_seconds.toFixed(1)} s versus a{" "}
                  {event.breaker_rating} A breaker. Started:{" "}
                  {event.load_names.join(", ")}.
                </span>
              </article>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

export function App() {
  const isDemoMode = panelApi.isDemoMode;
  const isPublicSandbox = import.meta.env.PROD && !isDemoMode;
  const [homes, setHomes] = useState([]);
  const [selectedHomeId, setSelectedHomeId] = useState("");
  const [panel, setPanel] = useState(null);
  const [presets, setPresets] = useState([]);
  const [settings, setSettings] = useState({
    electricity_rate: "0.18",
    main_service_rating: "200",
  });
  const [modal, setModal] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");

  const closeModal = useCallback(() => {
    if (!busy) setModal(null);
  }, [busy]);

  useEffect(() => {
    const controller = new AbortController();

    Promise.all([
      panelApi.getHomes(controller.signal),
      panelApi.getPresets(controller.signal),
    ])
      .then(async ([homeData, presetData]) => {
        setHomes(homeData);
        setPresets(presetData);
        const savedHomeId = localStorage.getItem(SELECTED_HOME_KEY);
        const selected =
          homeData.find((home) => home.id === savedHomeId) ?? homeData[0];
        if (!selected) return;
        setSelectedHomeId(selected.id);
        const panelData = await panelApi.getPanel(
          selected.id,
          controller.signal,
        );
        applyPanel(panelData);
      })
      .catch((requestError) => {
        if (requestError.name !== "AbortError") setError(requestError.message);
      });

    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!toast) return undefined;
    const timer = window.setTimeout(() => setToast(""), 2600);
    return () => window.clearTimeout(timer);
  }, [toast]);

  function applyPanel(updatedPanel) {
    setPanel(updatedPanel);
    setSettings({
      electricity_rate: String(updatedPanel.electricity_rate),
      main_service_rating: String(updatedPanel.main_service_rating),
    });
  }

  async function selectHome(homeId) {
    setSelectedHomeId(homeId);
    localStorage.setItem(SELECTED_HOME_KEY, homeId);
    setPanel(null);
    setError("");
    try {
      applyPanel(await panelApi.getPanel(homeId));
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function runMutation(action, successMessage, closeAfter = false) {
    setBusy(true);
    setError("");
    try {
      const updatedPanel = await action();
      applyPanel(updatedPanel);
      setToast(successMessage);
      if (closeAfter) setModal(null);
      return true;
    } catch (requestError) {
      setError(requestError.message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function handleSettingsSubmit(event) {
    event.preventDefault();
    if (isDemoMode) {
      setToast(READ_ONLY_DEMO_MESSAGE);
      return;
    }
    await runMutation(
      () =>
        panelApi.updateSettings(selectedHomeId, {
          electricity_rate: Number(settings.electricity_rate),
          main_service_rating: Number(settings.main_service_rating),
        }),
      "Panel settings updated",
    );
  }

  async function handleCreateHome(homeInput) {
    if (isDemoMode) {
      setToast(READ_ONLY_DEMO_MESSAGE);
      return;
    }
    setBusy(true);
    setError("");
    try {
      const home = await panelApi.createHome(homeInput);
      const updatedHomes = await panelApi.getHomes();
      setHomes(updatedHomes);
      setModal(null);
      setToast(`${home.name} created`);
      await selectHome(home.id);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleUpdateHome(homeInput) {
    if (isDemoMode) {
      setToast(READ_ONLY_DEMO_MESSAGE);
      return;
    }
    setBusy(true);
    setError("");
    try {
      const home = await panelApi.updateHome(selectedHomeId, homeInput);
      setHomes((current) =>
        current.map((item) => (item.id === home.id ? home : item)),
      );
      setPanel((current) =>
        current ? { ...current, home } : current,
      );
      setModal(null);
      setToast("Home details updated");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveCircuit(circuitInput) {
    if (isDemoMode) {
      setToast(READ_ONLY_DEMO_MESSAGE);
      return;
    }
    const editingCircuit = modal?.circuit;
    await runMutation(
      () =>
        editingCircuit
          ? panelApi.updateCircuit(
              selectedHomeId,
              editingCircuit.id,
              circuitInput,
            )
          : panelApi.createCircuit(selectedHomeId, circuitInput),
      `${circuitInput.name} ${editingCircuit ? "updated" : "added"}`,
      true,
    );
  }

  async function handleSaveLoad(loadInput) {
    if (isDemoMode) {
      setToast(READ_ONLY_DEMO_MESSAGE);
      return;
    }
    const circuit = modal?.circuit;
    const editingLoad = modal?.load;
    if (!circuit) return;
    await runMutation(
      () =>
        editingLoad
          ? panelApi.updateLoad(
              selectedHomeId,
              circuit.id,
              editingLoad.id,
              loadInput,
            )
          : panelApi.createLoad(selectedHomeId, circuit.id, loadInput),
      `${loadInput.name} ${editingLoad ? "updated" : "added"}`,
      true,
    );
  }

  async function handleDeleteCircuit(circuit) {
    if (isDemoMode) {
      setToast(READ_ONLY_DEMO_MESSAGE);
      return;
    }
    if (
      !window.confirm(
        `Remove ${circuit.name} and all connected schedules?`,
      )
    ) {
      return;
    }
    await runMutation(
      () => panelApi.deleteCircuit(selectedHomeId, circuit.id),
      `${circuit.name} removed`,
    );
  }

  async function handleDeleteLoad(circuit, load) {
    if (isDemoMode) {
      setToast(READ_ONLY_DEMO_MESSAGE);
      return;
    }
    if (!window.confirm(`Remove ${load.name} from ${circuit.name}?`)) return;
    await runMutation(
      () =>
        panelApi.deleteLoad(selectedHomeId, circuit.id, load.id),
      `${load.name} removed`,
    );
  }

  async function handleReset() {
    if (isDemoMode) {
      setToast(READ_ONLY_DEMO_MESSAGE);
      return;
    }
    if (
      !window.confirm(
        "Reset the database to the sample split-phase residence?",
      )
    ) {
      return;
    }
    setBusy(true);
    try {
      const updatedPanel = await panelApi.resetPanel();
      const updatedHomes = await panelApi.getHomes();
      setHomes(updatedHomes);
      setSelectedHomeId(updatedPanel.home.id);
      localStorage.setItem(SELECTED_HOME_KEY, updatedPanel.home.id);
      applyPanel(updatedPanel);
      setToast("Sample digital twin restored");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  if (!panel && !error) return <LoadingScreen />;

  if (!panel) {
    return (
      <main className="connection-error">
        <span className="connection-error__code">API</span>
        <h1>PanelTwin could not load the persistent panel.</h1>
        <p>{error}</p>
      </main>
    );
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="PanelTwin home">
          <span className="brand-mark">
            <BoltIcon />
          </span>
          <span>
            <strong>PanelTwin</strong>
            <small>Time-based panel digital twin</small>
          </span>
        </a>

        <div className="topbar__actions">
          <label className="home-switcher">
            <span>Home</span>
            <select
              value={selectedHomeId}
              onChange={(event) => selectHome(event.target.value)}
              disabled={busy || isDemoMode}
            >
              {homes.map((home) => (
                <option value={home.id} key={home.id}>
                  {home.name}
                </option>
              ))}
            </select>
          </label>
          <button
            className="icon-button"
            type="button"
            onClick={() => setModal({ type: "edit-home" })}
            disabled={busy || isDemoMode}
            title={isDemoMode ? "Editing is disabled in the live demo." : ""}
            aria-label="Edit current home"
          >
            <EditIcon />
          </button>
          <button
            className="icon-button"
            type="button"
            onClick={handleReset}
            disabled={busy || isDemoMode}
            title={isDemoMode ? "Reset is disabled in the live demo." : ""}
            aria-label="Reset sample database"
          >
            <ResetIcon />
          </button>
          <button
            className="button button--primary"
            type="button"
            onClick={() => setModal({ type: "circuit" })}
            disabled={busy || isDemoMode}
            title={isDemoMode ? "Editing is disabled in the live demo." : ""}
          >
            <PlusIcon />
            Add circuit
          </button>
        </div>
      </header>

      <main id="top">
        {isDemoMode && (
          <aside className="demo-banner" aria-label="Live demo notice">
            <strong>Live GitHub Pages demo</strong>
            <span>
              This page uses static sample data so it can run directly from
              GitHub. Editing and SQLite persistence are available when the
              FastAPI backend is running locally.
            </span>
          </aside>
        )}
        {isPublicSandbox && (
          <aside className="demo-banner" aria-label="Public sandbox notice">
            <strong>Editable public sandbox</strong>
            <span>
              Changes are saved in the hosted database and are visible to all
              visitors. Do not enter private or sensitive information.
            </span>
          </aside>
        )}

        <section className="hero hero--twin">
          <div className="hero__copy">
            <span className="section-kicker">Persistent split-phase model</span>
            <h1>{panel.home.name}, 15 minutes at a time.</h1>
            <p>
              Compare weekday and weekend running demand, calculate continuous
              branch loads at 125%, and review startup transients separately.
            </p>
            <div className="hero__meta">
              <span>
                {isDemoMode ? "Static live demo" : "Database persistence"}
              </span>
              <span>{panel.circuits.length} circuits</span>
              <span>{panel.summary.load_count} scheduled loads</span>
              <span>
                {panel.summary.measured_load_count} measured /{" "}
                {panel.summary.manufacturer_load_count} manufacturer /{" "}
                {panel.summary.estimated_load_count} estimated
              </span>
            </div>
          </div>

          <form className="settings-control" onSubmit={handleSettingsSubmit}>
            <label>
              <span>Electricity rate</span>
              <div className="rate-control__input">
                <span>$</span>
                <input
                  type="number"
                  min="0"
                  max="10"
                  step="0.01"
                  value={settings.electricity_rate}
                  disabled={isDemoMode}
                  onChange={(event) =>
                    setSettings((current) => ({
                      ...current,
                      electricity_rate: event.target.value,
                    }))
                  }
                />
                <span>/ kWh</span>
              </div>
            </label>
            <label>
              <span>Main service</span>
              <select
                value={settings.main_service_rating}
                disabled={isDemoMode}
                onChange={(event) =>
                  setSettings((current) => ({
                    ...current,
                    main_service_rating: event.target.value,
                  }))
                }
              >
                <option value="100">100 A</option>
                <option value="150">150 A</option>
                <option value="200">200 A</option>
              </select>
            </label>
            <button type="submit" disabled={busy || isDemoMode}>
              {isDemoMode ? "Read-only" : "Apply"}
            </button>
          </form>
        </section>

        {error && (
          <div className="error-banner" role="alert">
            <strong>PanelTwin needs attention.</strong>
            <span>{error}</span>
            <button type="button" onClick={() => setError("")}>
              Dismiss
            </button>
          </div>
        )}

        <DashboardCards summary={panel.summary} />
        <WarningCenter panel={panel} />

        <section className="panel-section">
          <div className="section-heading">
            <div>
              <span className="section-kicker">Editable circuit directory</span>
              <h2>Split-phase breaker panel</h2>
              <p>
                Expand circuits to inspect equations, 15-minute schedules,
                data quality, normal branch loading, and transient startup.
              </p>
            </div>
            <div className="panel-health">
              <div>
                <span>Safe</span>
                <strong>{panel.summary.safe_count}</strong>
              </div>
              <div>
                <span>Advisory</span>
                <strong>{panel.summary.advisory_count}</strong>
              </div>
              <div
                className={
                  panel.summary.overloaded_count ? "has-danger" : ""
                }
              >
                <span>Overloaded</span>
                <strong>{panel.summary.overloaded_count}</strong>
              </div>
            </div>
          </div>

          <CircuitTable
            circuits={panel.circuits}
            onAddLoad={(circuit) =>
              setModal({ type: "load", circuit })
            }
            onEditCircuit={(circuit) =>
              setModal({ type: "circuit", circuit })
            }
            onDeleteCircuit={handleDeleteCircuit}
            onEditLoad={(circuit, load) =>
              setModal({ type: "load", circuit, load })
            }
            onDeleteLoad={handleDeleteLoad}
            busy={busy}
            readOnly={isDemoMode}
          />
        </section>

        <Charts panel={panel} />

        <section className="formula-section">
          <div>
            <span className="section-kicker">Calculation model</span>
            <h2>Real power is only part of the picture.</h2>
            <p>
              The backend converts real watts into apparent power and current,
              evaluates normal branch loading, and builds separate 15-minute
              weekday and weekend profiles. Transients never inflate service
              utilization.
            </p>
          </div>
          <div className="formula-grid formula-grid--six">
            <div>
              <span>Apparent power</span>
              <code>VA = W / PF</code>
            </div>
            <div>
              <span>Current</span>
              <code>I = VA / V</code>
            </div>
            <div>
              <span>Branch calculation</span>
              <code>Icalc = Inoncontinuous + 1.25 x Icontinuous</code>
            </div>
            <div>
              <span>Startup transient</span>
              <code>Istart = Irunning x multiplier, for duration seconds</code>
            </div>
            <div>
              <span>Neutral estimate</span>
              <code>Ineutral = |IA(120V) - IB(120V)|</code>
            </div>
            <div>
              <span>Monthly energy</span>
              <code>kWh = kW x (weekday h x 22 + weekend h x 8)</code>
            </div>
          </div>
        </section>
      </main>

      <footer>
        <span>PanelTwin time-based residential digital twin</span>
        <span>
          Educational estimates only; not an NEC-compliant design tool.
        </span>
      </footer>

      {modal?.type === "circuit" && (
        <Modal
          kicker={modal.circuit ? "Edit breaker" : "New breaker"}
          title={modal.circuit ? "Edit panel circuit" : "Add a panel circuit"}
          onClose={closeModal}
        >
          <CircuitForm
            circuit={modal.circuit}
            onSubmit={handleSaveCircuit}
            onCancel={closeModal}
            busy={busy}
          />
        </Modal>
      )}

      {modal?.type === "load" && (
        <Modal
          kicker={modal.load ? "Edit schedule" : "Connected equipment"}
          title={modal.load ? "Edit electrical load" : "Add an electrical load"}
          onClose={closeModal}
        >
          <LoadForm
            circuit={modal.circuit}
            load={modal.load}
            presets={presets}
            onSubmit={handleSaveLoad}
            onCancel={closeModal}
            busy={busy}
          />
        </Modal>
      )}

      {modal?.type === "new-home" && (
        <Modal kicker="Persistent model" title="Create a home" onClose={closeModal}>
          <HomeForm
            onSubmit={handleCreateHome}
            onCancel={closeModal}
            busy={busy}
          />
        </Modal>
      )}

      {modal?.type === "edit-home" && (
        <Modal kicker="Home details" title="Edit current home" onClose={closeModal}>
          <HomeForm
            home={panel.home}
            onSubmit={handleUpdateHome}
            onCancel={closeModal}
            busy={busy}
          />
        </Modal>
      )}

      <button
        className="floating-home-button"
        type="button"
        onClick={() => setModal({ type: "new-home" })}
        disabled={isDemoMode}
        title={isDemoMode ? "Editing is disabled in the live demo." : ""}
      >
        <PlusIcon />
        New home
      </button>

      <div className={toast ? "toast toast--visible" : "toast"} role="status">
        {toast}
      </div>
    </div>
  );
}
