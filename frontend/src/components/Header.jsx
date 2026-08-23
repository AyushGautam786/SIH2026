import React from 'react';

export default function Header({ connectionStatus, stats }) {
  const isUp = connectionStatus === 'live';

  return (
    <div className="legacy-header-bridge" aria-label="Prototype connection summary">
      <div className="connection-badge"><span className={`conn-dot ${isUp ? 'conn-live' : ''}`} />{isUp ? 'Live backend' : 'Preview data'}</div>
      <div className="legacy-stat-row"><span><strong>{stats?.total_containers ?? '—'}</strong> containers</span><span><strong>{stats?.total_actions ?? '—'}</strong> decisions logged</span></div>
    </div>
  );
}
