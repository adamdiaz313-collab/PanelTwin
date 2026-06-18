const numberFormatter = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 1,
});

const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
});

function buildCoordinates(points, maxWatts, dimensions) {
  const { padding, chartWidth, chartHeight } = dimensions;
  return points.map((point, index) => ({
    x: padding.left + (index / (points.length - 1)) * chartWidth,
    y:
      padding.top +
      chartHeight -
      (point.real_power_watts / maxWatts) * chartHeight,
    point,
  }));
}

function coordinatesToPath(coordinates) {
  return coordinates
    .map(({ x, y }, index) => `${index ? "L" : "M"} ${x} ${y}`)
    .join(" ");
}

function DemandChart({ weekday, weekend, summary }) {
  const width = 920;
  const height = 280;
  const padding = { top: 24, right: 18, bottom: 38, left: 52 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const dimensions = { padding, chartWidth, chartHeight };
  const maxWatts = Math.max(
    ...weekday.map((point) => point.real_power_watts),
    ...weekend.map((point) => point.real_power_watts),
    1,
  );
  const weekdayCoordinates = buildCoordinates(
    weekday,
    maxWatts,
    dimensions,
  );
  const weekendCoordinates = buildCoordinates(
    weekend,
    maxWatts,
    dimensions,
  );
  const weekdayPath = coordinatesToPath(weekdayCoordinates);
  const weekendPath = coordinatesToPath(weekendCoordinates);
  const areaPath = `${weekdayPath} L ${padding.left + chartWidth} ${
    padding.top + chartHeight
  } L ${padding.left} ${padding.top + chartHeight} Z`;
  const peakProfile =
    summary.peak_demand_day_type === "weekday" ? weekday : weekend;
  const peakPoint = peakProfile.find(
    (point) => point.label === summary.peak_demand_label,
  );
  const peakCoordinates = buildCoordinates(
    peakProfile,
    maxWatts,
    dimensions,
  ).find((item) => item.point.interval_index === peakPoint?.interval_index);

  return (
    <article className="chart-card chart-card--wide">
      <div className="section-heading section-heading--chart">
        <div>
          <span className="section-kicker">15-minute simulation</span>
          <h2>Weekday and weekend real-power demand</h2>
        </div>
        <div className="chart-legend">
          <span className="chart-key chart-key--green">
            <i />
            Weekday
          </span>
          <span className="chart-key chart-key--blue">
            <i />
            Weekend
          </span>
        </div>
      </div>
      <div className="demand-chart-wrap">
        <svg
          className="demand-chart"
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label="Weekday and weekend 15-minute real power demand profiles"
        >
          {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
            const y = padding.top + chartHeight - ratio * chartHeight;
            return (
              <g key={ratio}>
                <line
                  x1={padding.left}
                  x2={padding.left + chartWidth}
                  y1={y}
                  y2={y}
                  className="chart-grid-line"
                />
                <text x="4" y={y + 4} className="chart-axis-label">
                  {numberFormatter.format((maxWatts * ratio) / 1000)} kW
                </text>
              </g>
            );
          })}
          <path d={areaPath} className="demand-area" />
          <path d={weekdayPath} className="demand-line" />
          <path d={weekendPath} className="demand-line demand-line--weekend" />
          {weekdayCoordinates
            .filter((_, index) => index % 16 === 0)
            .map(({ x, point }) => (
              <text
                x={x}
                y={height - 10}
                textAnchor="middle"
                className="chart-axis-label"
                key={point.interval_index}
              >
                {point.label.slice(0, 2)}
              </text>
            ))}
          {peakCoordinates && (
            <circle
              cx={peakCoordinates.x}
              cy={peakCoordinates.y}
              r="5"
              className="demand-point demand-point--peak"
            >
              <title>
                {summary.peak_demand_day_type} peak at{" "}
                {summary.peak_demand_label}:{" "}
                {numberFormatter.format(summary.peak_demand_watts)} W
              </title>
            </circle>
          )}
        </svg>
      </div>
      <details className="chart-method">
        <summary>Equation, inputs, and assumptions</summary>
        <p>
          Each point sums the real watts of loads scheduled during that
          15-minute interval. Periods are treated as fully on. Startup current
          is a short transient and is intentionally excluded from this chart.
        </p>
        <code>Pinterval = sum(active load watts)</code>
      </details>
    </article>
  );
}

function BarChart({
  title,
  kicker,
  data,
  valueFormatter,
  tone,
  explanation,
}) {
  const maxValue = Math.max(...data.map((item) => item.value), 1);
  return (
    <article className="chart-card">
      <div className="section-heading section-heading--chart">
        <div>
          <span className="section-kicker">{kicker}</span>
          <h2>{title}</h2>
        </div>
      </div>
      <div className="bar-chart">
        {data.length ? (
          data.slice(0, 10).map((item) => (
            <div className="bar-row" key={item.id}>
              <div className="bar-row__copy">
                <span>{item.name}</span>
                <strong>{valueFormatter(item.value)}</strong>
              </div>
              <div className="bar-track">
                <span
                  className={`bar-fill bar-fill--${tone}`}
                  style={{ width: `${(item.value / maxValue) * 100}%` }}
                />
              </div>
            </div>
          ))
        ) : (
          <div className="chart-empty">Add loads to populate this chart.</div>
        )}
      </div>
      <details className="chart-method">
        <summary>Equation, inputs, and assumptions</summary>
        <p>{explanation}</p>
      </details>
    </article>
  );
}

export function Charts({ panel }) {
  const costData = panel.circuits.map((circuit) => ({
    id: circuit.id,
    name: circuit.name,
    value: circuit.monthly_cost,
  }));
  const energyData = panel.circuits
    .flatMap((circuit) =>
      circuit.loads.map((load) => ({
        id: load.id,
        name: `${load.name} (${load.data_quality})`,
        value: load.monthly_kwh,
      })),
    )
    .sort((a, b) => b.value - a.value);

  return (
    <section className="charts-stack" aria-label="Panel charts">
      <DemandChart
        weekday={panel.weekday_demand}
        weekend={panel.weekend_demand}
        summary={panel.summary}
      />
      <div className="charts-grid">
        <BarChart
          title="Monthly cost by circuit"
          kicker="Cost contribution"
          data={costData}
          valueFormatter={(value) => currencyFormatter.format(value)}
          tone="orange"
          explanation="Circuit cost equals the sum of load kWh for 22 weekdays and 8 weekend days, multiplied by the current electricity rate. Fees and rate tiers are excluded."
        />
        <BarChart
          title="Energy usage by load"
          kicker="Monthly consumption"
          data={energyData}
          valueFormatter={(value) => `${numberFormatter.format(value)} kWh`}
          tone="blue"
          explanation="Load energy equals real kW multiplied by scheduled hours. Labels identify whether the source value is Measured, Manufacturer, or Estimated."
        />
      </div>
    </section>
  );
}
