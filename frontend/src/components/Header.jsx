import React from 'react';

export default function Header({ connectionStatus, stats }) {
  const isUp = connectionStatus === 'live';

  return (
    <header className="app-header">
      <div className="header-brand">
        <div className="brand-logo">
          <span className="logo-pulse-ring" />
          <span className="logo-icon">⬡</span>
        </div>
        <div>
          <h1 className="brand-name">Pulse</h1>
          <p className="brand-tagline">Predictive Utilisation &amp; Self-Healing Engine</p>
        </div>
      </div>

      <div className="header-stats">
        <StatChip label="Containers" value={stats?.total_containers ?? '—'} color="var(--blue)" />
        <StatChip label="At Risk"    value={stats?.at_risk_now    ?? '—'} color="var(--red)"  />
        <StatChip label="Actions"    value={stats?.total_actions  ?? '—'} color="var(--orange)" />
      </div>

      <div className={`connection-badge ${isUp ? 'badge-up' : 'badge-down'}`}>
        <span className="conn-dot" />
        {connectionStatus === 'live'         && 'Live'}
        {connectionStatus === 'connecting'   && 'Connecting…'}
        {connectionStatus === 'disconnected' && 'Reconnecting…'}
      </div>
    </header>
  );
}

function StatChip({ label, value, color }) {
  return (
    <div className="stat-chip">
      <span className="stat-value" style={{ color }}>{value}</span>
      <span className="stat-label">{label}</span>
    </div>
  );
}
