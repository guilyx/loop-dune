import { percent } from "@/lib/format";

/** label · value (+unit) · optional signed delta vs a named period. */
export function StatTile({
  label,
  value,
  unit,
  delta,
  deltaLabel,
  note,
}: {
  label: string;
  value: string;
  unit?: string;
  delta?: number | null;
  deltaLabel?: string;
  /** Free-text context line, used instead of a delta. */
  note?: string;
}) {
  return (
    <div className="card">
      <div className="stat-label">{label}</div>
      <div className="stat-value">
        {value}
        {unit && value !== "–" && <span className="stat-unit">{unit}</span>}
      </div>
      {note && <div className="stat-delta">{note}</div>}
      {delta !== undefined && (
        <div className="stat-delta">
          {delta === null ? "–" : `${delta > 0 ? "+" : delta < 0 ? "−" : ""}${percent(Math.abs(delta), 1)}`}
          {deltaLabel ? ` ${deltaLabel}` : ""}
        </div>
      )}
    </div>
  );
}
