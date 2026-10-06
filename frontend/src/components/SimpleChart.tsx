import type { ChartSpec } from "../types";

const W = 480;
const H = 260;
const PAD = { top: 12, right: 12, bottom: 62, left: 52 };
const MAX_POINTS = 50;

const compact = (v: number) =>
  Math.abs(v) >= 1000
    ? new Intl.NumberFormat("en", { notation: "compact" }).format(v)
    : String(Math.round(v * 100) / 100);

/** Dependency-free SVG bar/line chart; enough for previews, swap for a charting lib later. */
export function SimpleChart({ spec }: { spec: ChartSpec }) {
  const xi = spec.data.columns.indexOf(spec.x);
  const yi = spec.data.columns.indexOf(spec.y);
  const points = spec.data.rows
    .map((r) => ({ label: String(r[xi] ?? ""), value: Number(r[yi]) }))
    .filter((p) => Number.isFinite(p.value))
    .slice(0, MAX_POINTS);

  if (points.length === 0) {
    return <p className="text-xs text-slate-500">No numeric values in “{spec.y}” to chart.</p>;
  }

  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  const max = Math.max(0, ...points.map((p) => p.value));
  const min = Math.min(0, ...points.map((p) => p.value));
  const range = max - min || 1;
  const yPos = (v: number) => PAD.top + (1 - (v - min) / range) * innerH;
  const band = innerW / points.length;
  const cx = (i: number) => PAD.left + band * (i + 0.5);
  const ticks = [0, 1, 2, 3, 4].map((i) => min + (range * i) / 4);
  const labelEvery = Math.ceil(points.length / 12);

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="w-full"
      role="img"
      aria-label={`${spec.y} by ${spec.x}`}
    >
      {ticks.map((t) => (
        <g key={t}>
          <line
            x1={PAD.left}
            x2={W - PAD.right}
            y1={yPos(t)}
            y2={yPos(t)}
            className="stroke-slate-200"
          />
          <text
            x={PAD.left - 6}
            y={yPos(t) + 3}
            textAnchor="end"
            className="fill-slate-500 text-[10px]"
          >
            {compact(t)}
          </text>
        </g>
      ))}
      {spec.chart_type === "bar" ? (
        points.map((p, i) => (
          <rect
            key={i}
            x={cx(i) - (band * 0.7) / 2}
            y={Math.min(yPos(p.value), yPos(0))}
            width={band * 0.7}
            height={Math.abs(yPos(p.value) - yPos(0))}
            className="fill-indigo-500"
          >
            <title>{`${p.label}: ${p.value}`}</title>
          </rect>
        ))
      ) : (
        <>
          <polyline
            fill="none"
            className="stroke-indigo-500"
            strokeWidth={2}
            points={points.map((p, i) => `${cx(i)},${yPos(p.value)}`).join(" ")}
          />
          {points.map((p, i) => (
            <circle key={i} cx={cx(i)} cy={yPos(p.value)} r={3} className="fill-indigo-500">
              <title>{`${p.label}: ${p.value}`}</title>
            </circle>
          ))}
        </>
      )}
      {points.map(
        (p, i) =>
          i % labelEvery === 0 && (
            <text
              key={i}
              transform={`translate(${cx(i)}, ${H - PAD.bottom + 12}) rotate(35)`}
              className="fill-slate-600 text-[10px]"
            >
              {p.label.length > 14 ? `${p.label.slice(0, 13)}…` : p.label}
            </text>
          ),
      )}
    </svg>
  );
}
