import React from 'react';

/**
 * Lightweight SVG area/sparkline chart (no chart library - TASKS rule #3).
 * `series` is an array of numbers (already the right unit, e.g. %).
 */
export default function MetricChart({ series = [], color = 'var(--violet)', height = 72, label }) {
  const W = 300;
  const H = height;
  const pad = 4;
  const points = normalize(series);

  const path = points
    .map((v, i) => {
      const x = pad + (i / Math.max(1, points.length - 1)) * (W - pad * 2);
      const y = H - pad - v * (H - pad * 2);
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
  const area = points.length > 1 ? `${path} L${W - pad},${H - pad} L${pad},${H - pad} Z` : '';
  const gid = `grad-${sanitize(label ?? color)}-${points.length}`;

  const last = series[series.length - 1];

  return (
    <div className="metric-chart" role="img" aria-label={label ? `${label} chart` : 'metric chart'}>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
        <defs>
          <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.35" />
            <stop offset="100%" stopColor={color} stopOpacity="0.02" />
          </linearGradient>
        </defs>
        {area && <path d={area} fill={`url(#${gid})`} />}
        {path && <path d={path} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />}
        {points.length > 1 && (
          <circle
            cx={(W - pad * 2)}
            cy={H - pad - points[points.length - 1] * (H - pad * 2)}
            r="3"
            fill={color}
          />
        )}
      </svg>
      {label && (
        <span className="metric-chart-label">
          {label}
          {last !== undefined && <strong className="mono">{Math.round(last)}%</strong>}
        </span>
      )}
    </div>
  );
}

function normalize(series) {
  const clean = series.filter((v) => Number.isFinite(v));
  if (clean.length < 2) return clean.map(() => 0);
  // Percentage-style data sits in [0,100]; scale against 100 but let extreme
  // peaks still read clearly (never zoom below half-scale).
  const max = Math.max(60, ...clean);
  return clean.map((v) => Math.max(0, Math.min(1, v / max)));
}

function sanitize(s) {
  return String(s).replace(/[^a-zA-Z0-9_-]/g, '');
}
