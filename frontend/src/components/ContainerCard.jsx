import React from 'react';

const STATE_META = {
  healthy:          { label: 'HEALTHY',   color: 'var(--green)',  dimColor: 'var(--green-dim)'  },
  transient_spike:  { label: 'SPIKE',     color: 'var(--orange)', dimColor: 'var(--orange-dim)' },
  at_risk:          { label: 'AT RISK',   color: 'var(--red)',    dimColor: 'var(--red-dim)'    },
};

export default function ContainerCard({ container, onInject }) {
  const { id, name, pipeline, cpu, mem, net, predicted_state, confidence, cooldown_seconds_left, last_action } = container;
  const meta = STATE_META[predicted_state] || STATE_META.healthy;
  const isAtRisk = predicted_state === 'at_risk';
  const isSpike  = predicted_state === 'transient_spike';

  return (
    <div
      className="container-card"
      style={{
        '--state-color': meta.color,
        '--state-dim':   meta.dimColor,
      }}
    >
      {/* Animated glow border */}
      <div className="card-glow" />

      {/* Header */}
      <div className="card-header">
        <div>
          <div className="card-name">{name}</div>
          <div className="card-pipeline">{pipeline}</div>
        </div>
        <div className="state-badge" style={{ background: meta.dimColor, color: meta.color }}>
          {isAtRisk && <span className="badge-dot" />}
          {meta.label}
        </div>
      </div>

      {/* Metrics */}
      <div className="card-metrics">
        <MetricRow label="CPU" value={cpu} color="var(--blue)"   />
        <MetricRow label="MEM" value={mem} color="var(--purple)" />
        <MetricRow label="NET" value={net} color="var(--green)"  />
      </div>

      {/* Confidence */}
      <div className="card-confidence">
        <span className="conf-label">Model confidence</span>
        <span className="conf-value">{Math.round(confidence * 100)}%</span>
      </div>

      {/* Cooldown notice */}
      {cooldown_seconds_left > 0 && (
        <div className="card-cooldown">
          <span className="cooldown-icon">⏱</span>
          Cooldown {cooldown_seconds_left}s &nbsp;·&nbsp; last: <strong>{last_action}</strong>
        </div>
      )}

      {/* Demo buttons */}
      <div className="card-actions">
        <button
          className="inject-btn spike-btn"
          onClick={() => onInject(id, 'spike')}
          title="Inject a transient spike — should NOT trigger healing"
        >
          ⚡ Inject Spike
        </button>
        <button
          className="inject-btn risk-btn"
          onClick={() => onInject(id, 'at_risk')}
          title="Inject sustained load — should trigger autonomous healing"
        >
          🔥 Inject At-Risk
        </button>
      </div>
    </div>
  );
}

function MetricRow({ label, value, color }) {
  return (
    <div className="metric-row">
      <span className="metric-label">{label}</span>
      <div className="metric-bar-track">
        <div
          className="metric-bar-fill"
          style={{ width: `${value}%`, background: color }}
        />
      </div>
      <span className="metric-value mono">{value}%</span>
    </div>
  );
}
