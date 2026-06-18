const numberFormatter = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 1,
});

const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
});

function CardIcon({ type }) {
  if (type === "balance") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 3v18M5 7h14M7 7l-4 7h8L7 7Zm10 0-4 7h8l-4-7Z" />
      </svg>
    );
  }
  if (type === "service") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M5 19a8 8 0 1 1 14 0M12 12l4-4" />
        <path d="M8 19h8" />
      </svg>
    );
  }
  if (type === "peak") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="m3 18 5-7 4 4 4-9 5 12" />
      </svg>
    );
  }
  if (type === "cost") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="9" />
        <path d="M15 8.5c-.8-.7-1.8-1-3-1-1.7 0-3 .8-3 2s1.2 1.8 3 2c1.8.3 3 1 3 2.3 0 1.2-1.3 2.2-3 2.2-1.3 0-2.5-.5-3.3-1.3M12 5.5v13" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="m13 2-8 12h7l-1 8 8-12h-7l1-8Z" />
    </svg>
  );
}

function MetricCard({ card }) {
  return (
    <article className={`metric-card metric-card--${card.tone}`}>
      <div className="metric-card__top">
        <span>{card.label}</span>
        <span className="metric-icon">
          <CardIcon type={card.icon} />
        </span>
      </div>
      <strong>{card.value}</strong>
      <p>{card.note}</p>
      <details className="calculation-note">
        <summary>How calculated</summary>
        <code>{card.formula}</code>
        <span>{card.inputs}</span>
        <small>{card.assumption}</small>
      </details>
    </article>
  );
}

export function DashboardCards({ summary }) {
  const legAPercent =
    (summary.leg_a_current / summary.main_service_rating) * 100;
  const legBPercent =
    (summary.leg_b_current / summary.main_service_rating) * 100;
  const cards = [
    {
      label: "Leg A running peak",
      value: `${numberFormatter.format(summary.leg_a_current)} A`,
      note: `${numberFormatter.format(legAPercent)}% of service rating`,
      tone: summary.leg_a_status,
      icon: "bolt",
      formula: "Ileg = sum(active load VA / load V)",
      inputs: `${numberFormatter.format(summary.leg_a_current)} A / ${summary.main_service_rating} A = ${numberFormatter.format(legAPercent)}%`,
      assumption:
        "Maximum 15-minute running interval across weekday and weekend profiles. Inrush is excluded.",
    },
    {
      label: "Leg B running peak",
      value: `${numberFormatter.format(summary.leg_b_current)} A`,
      note: `${numberFormatter.format(legBPercent)}% of service rating`,
      tone: summary.leg_b_status,
      icon: "bolt",
      formula: "Ileg = sum(active load VA / load V)",
      inputs: `${numberFormatter.format(summary.leg_b_current)} A / ${summary.main_service_rating} A = ${numberFormatter.format(legBPercent)}%`,
      assumption:
        "Maximum 15-minute running interval across weekday and weekend profiles. Inrush is excluded.",
    },
    {
      label: "Neutral running peak",
      value: `${numberFormatter.format(summary.neutral_current)} A`,
      note: `${numberFormatter.format(summary.leg_imbalance_percent)}% service-peak imbalance`,
      tone: summary.leg_unbalanced ? "advisory" : "safe",
      icon: "balance",
      formula: "Ineutral = |IA(120V) - IB(120V)|",
      inputs: `Peak neutral ${numberFormatter.format(summary.neutral_current)} A; leg imbalance ${numberFormatter.format(summary.leg_imbalance_percent)}%`,
      assumption:
        "Uses simultaneous fundamental current from 120V loads only; nonlinear harmonics are not modeled.",
    },
    {
      label: "Main service utilization",
      value: `${numberFormatter.format(summary.main_service_utilization_percent)}%`,
      note: `${summary.main_service_rating} A split-phase service`,
      tone: summary.main_service_status,
      icon: "service",
      formula: "utilization = max(IA, IB) / service rating x 100",
      inputs: `${numberFormatter.format(Math.max(summary.leg_a_current, summary.leg_b_current))} A / ${summary.main_service_rating} A`,
      assumption:
        "Running demand only. Startup transients are reported separately and do not inflate service utilization.",
    },
    {
      label: "Peak real demand",
      value: `${numberFormatter.format(summary.peak_demand_watts / 1000)} kW`,
      note: `${summary.peak_demand_day_type} peak at ${summary.peak_demand_label}`,
      tone: summary.high_concurrency_count ? "advisory" : "safe",
      icon: "peak",
      formula: "Ppeak = max(sum(active load watts))",
      inputs: `${numberFormatter.format(summary.peak_demand_watts)} W at ${summary.peak_demand_label}`,
      assumption:
        "Highest 15-minute scheduled interval; short inrush events are excluded from real-power demand.",
    },
    {
      label: "Estimated monthly cost",
      value: currencyFormatter.format(summary.monthly_cost),
      note: `${numberFormatter.format(summary.monthly_kwh)} kWh per month`,
      tone: "primary",
      icon: "cost",
      formula: "cost = monthly kWh x electricity rate",
      inputs: `${numberFormatter.format(summary.monthly_kwh)} kWh in a 30-day model`,
      assumption:
        "Uses 22 weekdays and 8 weekend days. Utility fees, tiers, taxes, and seasonal changes are excluded.",
    },
  ];

  return (
    <section
      className="dashboard-grid dashboard-grid--six"
      aria-label="Panel dashboard"
    >
      {cards.map((card) => (
        <MetricCard card={card} key={card.label} />
      ))}
    </section>
  );
}
