import React from 'react';

const STATE_META = {
  healthy: { label: 'HEALTHY', color: 'var(--green)', dimColor: 'var(--green-dim)', marker: 'ok' },
  transient_spike: { label: 'SPIKE', color: 'var(--orange)', dimColor: 'var(--orange-dim)', marker: 'watch' },
  at_risk: { label: 'AT RISK', color: 'var(--red)', dimColor: 'var(--red-dim)', marker: 'act' },
};

export default function ContainerCard({ container, onInject, onSelect }) {
  const { id, name, pipeline, cpu, mem, net, predicted_state, confidence, cooldown_seconds_left, last_action } = container;
  const meta = STATE_META[predicted_state] || STATE_META.healthy;

  return (
    <article
      className={`container-card state-${predicted_state}`}
      style={{ '--state-color': meta.color, '--state-dim': meta.dimColor }}
      onClick={() => onSelect?.(container)}
      role={onSelect ? 'button' : undefined}
      tabIndex={onSelect ? 0 : undefined}
      onKeyDown={(e) => { if (onSelect && (e.key === 'Enter' || e.key === ' ')) onSelect(container); }}
    >
      <div className="card-topline"><span className="container-id mono">/{id.slice(-6)}</span><span className="state-badge"><span className={`state-marker ${meta.marker}`} />{meta.label}</span></div>
      <div className="card-heading"><div><h3>{name}</h3><span>{pipeline}</span></div><span className="container-menu" aria-hidden="true">···</span></div>
      <div className="card-metrics">
        <MetricRow label="CPU" value={cpu} color="var(--violet)" />
        <MetricRow label="MEM" value={mem} color="var(--blue)" />
        <MetricRow label="NET" value={net} color="var(--green)" />
      </div>
      <div className="card-footer-row"><span>Model confidence</span><strong className="mono">{Math.round(confidence * 100)}%</strong></div>
      {cooldown_seconds_left > 0 && <div className="card-cooldown"><span className="cooldown-ring" />Cooldown {cooldown_seconds_left}s <span>·</span> last action: <strong>{last_action}</strong></div>}
      <div className="card-actions"><button className="inject-btn spike-btn" onClick={() => onInject(id, 'spike')}>Inject spike <span>↗</span></button><button className="inject-btn risk-btn" onClick={() => onInject(id, 'at_risk')}>Inject at-risk <span>↗</span></button></div>
    </article>
  );
}

function MetricRow({ label, value, color }) {
  return <div className="metric-row"><span className="metric-label">{label}</span><div className="metric-bar-track"><div className="metric-bar-fill" style={{ width: `${Math.max(3, Math.min(100, value))}%`, background: color }} /></div><span className="metric-value mono">{Math.round(value)}%</span></div>;
}
