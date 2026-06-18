const statusCopy = {
  safe: "Safe",
  advisory: "Advisory",
  overloaded: "Overloaded",
};

export function StatusBadge({ status }) {
  return (
    <span className={`status-badge status-badge--${status}`}>
      <i aria-hidden="true" />
      {statusCopy[status]}
    </span>
  );
}
