import React, { useEffect, useRef } from 'react';

const ACTION_META = {
  restart: { label: 'RESTART', color: 'var(--red)' },
  scale: { label: 'SCALE', color: 'var(--orange)' },
};

export default function AuditLog({ entries }) {
  const logRef = useRef(null);
  const prevCount = useRef(0);

  useEffect(() => {
    if (entries.length > prevCount.current && logRef.current) logRef.current.scrollTop = 0;
    prevCount.current = entries.length;
  }, [entries.length]);

  return <section className="audit-section"><div className="panel-heading"><div><span className="tiny-label">TRUST LAYER</span><h2>Autonomous action log</h2></div><span className="entry-count">{entries.length} entries</span></div><div className="audit-log" ref={logRef}>{entries.length === 0 ? <div className="audit-empty">No actions yet. An at-risk scenario will appear here once Pulse decides to intervene.</div> : entries.map((entry, index) => { const meta = ACTION_META[entry.action] || { label: entry.action?.toUpperCase() || 'ACTION', color: 'var(--text-secondary)' }; return <div className="audit-row" key={entry.id || `${entry.ts}-${index}`} style={{ animationDelay: `${index * 25}ms` }}><span className="audit-time mono">{new Date(entry.ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span><span className="audit-action" style={{ color: meta.color }}>{meta.label}</span><span className="audit-detail"><strong>{entry.container_name}</strong><small>{entry.pipeline}</small></span><span className="audit-confidence mono">{Math.round(entry.confidence * 100)}%</span></div>; })}</div></section>;
}
