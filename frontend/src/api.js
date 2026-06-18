const API_BASE_URL = import.meta.env.VITE_API_URL ?? "/backend/api";
const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === "true";
const DEMO_BASE_URL = `${import.meta.env.BASE_URL.replace(/\/$/, "")}/demo`;

let demoPanelPromise;
let demoPresetsPromise;

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
    ...options,
  });

  if (!response.ok) {
    let detail = "The request could not be completed.";
    try {
      const body = await response.json();
      detail = Array.isArray(body.detail)
        ? body.detail.map((item) => item.msg).join(" ")
        : body.detail ?? detail;
    } catch {
      detail = response.statusText || detail;
    }
    throw new Error(detail);
  }

  return response.json();
}

function homeQuery(homeId) {
  return `home_id=${encodeURIComponent(homeId)}`;
}

async function getDemoPanel() {
  if (!demoPanelPromise) {
    demoPanelPromise = fetch(`${DEMO_BASE_URL}/panel.json`).then((response) => {
      if (!response.ok) {
        throw new Error("The static demo panel could not be loaded.");
      }
      return response.json();
    });
  }
  return demoPanelPromise;
}

async function getDemoPresets() {
  if (!demoPresetsPromise) {
    demoPresetsPromise = fetch(`${DEMO_BASE_URL}/presets.json`).then(
      (response) => {
        if (!response.ok) {
          throw new Error("The static demo presets could not be loaded.");
        }
        return response.json();
      },
    );
  }
  return demoPresetsPromise;
}

function rejectDemoMutation() {
  return Promise.reject(
    new Error(
      "The GitHub Pages demo is read-only. Run the FastAPI backend locally for editing and SQLite persistence.",
    ),
  );
}

const liveApi = {
  isDemoMode: false,
  getHomes(signal) {
    return request("/homes", { signal });
  },
  createHome(home) {
    return request("/homes", {
      method: "POST",
      body: JSON.stringify(home),
    });
  },
  updateHome(homeId, home) {
    return request(`/homes/${homeId}`, {
      method: "PUT",
      body: JSON.stringify(home),
    });
  },
  getPanel(homeId, signal) {
    return request(`/panel?${homeQuery(homeId)}`, { signal });
  },
  getPresets(signal) {
    return request("/presets", { signal });
  },
  updateSettings(homeId, settings) {
    return request(`/panel/settings?${homeQuery(homeId)}`, {
      method: "PUT",
      body: JSON.stringify(settings),
    });
  },
  createCircuit(homeId, circuit) {
    return request(`/circuits?${homeQuery(homeId)}`, {
      method: "POST",
      body: JSON.stringify(circuit),
    });
  },
  updateCircuit(homeId, circuitId, circuit) {
    return request(`/circuits/${circuitId}?${homeQuery(homeId)}`, {
      method: "PUT",
      body: JSON.stringify(circuit),
    });
  },
  deleteCircuit(homeId, circuitId) {
    return request(`/circuits/${circuitId}?${homeQuery(homeId)}`, {
      method: "DELETE",
    });
  },
  createLoad(homeId, circuitId, load) {
    return request(
      `/circuits/${circuitId}/loads?${homeQuery(homeId)}`,
      {
        method: "POST",
        body: JSON.stringify(load),
      },
    );
  },
  updateLoad(homeId, circuitId, loadId, load) {
    return request(
      `/circuits/${circuitId}/loads/${loadId}?${homeQuery(homeId)}`,
      {
        method: "PUT",
        body: JSON.stringify(load),
      },
    );
  },
  deleteLoad(homeId, circuitId, loadId) {
    return request(
      `/circuits/${circuitId}/loads/${loadId}?${homeQuery(homeId)}`,
      { method: "DELETE" },
    );
  },
  resetPanel() {
    return request("/panel/reset", { method: "POST" });
  },
};

const demoApi = {
  isDemoMode: true,
  async getHomes() {
    const panel = await getDemoPanel();
    return [panel.home];
  },
  createHome: rejectDemoMutation,
  updateHome: rejectDemoMutation,
  getPanel() {
    return getDemoPanel();
  },
  getPresets() {
    return getDemoPresets();
  },
  updateSettings: rejectDemoMutation,
  createCircuit: rejectDemoMutation,
  updateCircuit: rejectDemoMutation,
  deleteCircuit: rejectDemoMutation,
  createLoad: rejectDemoMutation,
  updateLoad: rejectDemoMutation,
  deleteLoad: rejectDemoMutation,
  resetPanel() {
    return getDemoPanel();
  },
};

export const panelApi = DEMO_MODE ? demoApi : liveApi;
