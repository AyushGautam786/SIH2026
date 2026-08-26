import React from 'react';
import MetricChart from './MetricChart';
import { STATE_META, featuresFromHistory } from '../lib/api';

/**
 * Container drill-down drawer (PPTX slide 8/11): big live charts, the exact
 * feature readout the model sees, confidence, cooldown and last action.
 */
export default function ContainerDetail({ container, history = [], onClose }) {
  if (!container) return null;
  const meta = STATE_META[container.predicted_state] ?? STATE_META.healthy;
  const features = featuresFromHistory(history);

  return (
    <>
      <div className="drawer-scrim" onClick={onClose} />
      <aside className={`detail-drawer state-${container.predicted_state}`} style={{ '--state-color': meta.color }} role="dialog" aria-label={`${container.name} detail`}>
        <header className="drawer-head">
          <div>
            <span className="tiny-label">CONTAINER DRILL-DOWN</span>
            <h2>{container.name}</h2>
            <span className="mono drawer-sub">/{container.id.slice(-6)} · {container.pipeline}</span>
          </div>
          <div className="drawer-head-right">
            <span className="state-badge"><span className={`state-marker ${meta.marker}`} />{meta.label}</span>
            <button className="drawer-close" onClick={onClose} aria-label="Close">✕</button>
          </div>
        </header>

        <div className="drawer-charts">
          <MetricChart series={history.map((p) => p.cpu)} color="var(--violet)" label="CPU %" height={92} />
          <MetricChart series={history.map((p) => p.mem)} color="var(--blue)" label="MEM %" height={92} />
          <MetricChart series={history.map((p) => p.net)} color="var(--green)" label="NET %" height={92} />
        </div>

        <section className="drawer-section">
          <span className="tiny-label">WHAT THE MODEL SEES</span>
          {features ? (
            <div className="feature-grid mono">
              <Feature label="cpu_avg_1m" value={`${features.cpu_avg_1m.toFixed(1)}%`} />
              <Feature label="mem_delta_30s" value={`${features.mem_delta_30s >= 0 ? '+' : ''}${features.mem_delta_30s.toFixed(1)}`} accent={features.mem_delta_30s > 4} />
              <Feature label="net_std_1m" value={features.net_std_1m.toFixed(1)} />
              <Feature label="cpu_mem_ratio" value={features.cpu_mem_ratio.toFixed(2)} />
            </div>
          ) : (
            <p className="drawer-empty">Waiting for telemetry ticks…</p>
          )}
        </section>

        <section className="drawer-section">
          <span className="tiny-label">DECISION STATE</span>
          <div className="decision-rows">
            <Row k="Model confidence" v={`${Math.round((container.confidence ?? 0) * 100)}%`} />
            <Row k="Cooldown left" v={container.cooldown_seconds_left > 0 ? `${container.cooldown_seconds_left}s` : '—'} />
            <Row k="Last action" v={container.last_action ?? 'none'} />
            <Row k="Memory" v={`${container.mem_used_mb ?? '—'} / ${container.mem_limit_mb ?? '—'} MB`} />
            <Row k="TCP connections" v={container.tcp_connections ?? '—'} />
            <Row k="Packet drops (tick)" v={container.packet_drops ?? '—'} />
          </div>
        </section>

        <p className="drawer-note">Charts stream live over WebSocket; the model re-classifies every {3}s tick.</p>
      </aside>
    </>
  );
}

function Feature({ label, value, accent }) {
  return (
    <div className={`feature-cell ${accent ? 'feature-accent' : ''}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Row({ k, v }) {
  return <div className="decision-row"><span>{k}</span><strong className="mono">{v}</strong></div>;
}
