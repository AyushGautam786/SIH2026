import React, { useEffect, useRef } from 'react';

const ACTION_META = {
  restart: { icon: '↺', color: 'var(--red)',    label: 'RESTART' },
  scale:   { icon: '⬆', color: 'var(--orange)', label: 'SCALE'   },
};

export default function AuditLog({ entries }) {
  const logRef = useRef(null);
  const prevCount = useRef(0);

  // Scroll to top only when a new entry appears
  useEffect(() => {
    if (entries.length > prevCount.current && logRef.current) {
      logRef.current.scrollTop = 0;
    }
    prevCount.current = entries.length;
  }, [entries.length]);

  return (
    <section className="audit-section">
      <div className="section-header">
        <h2 className="section-title">
          <span className="section-icon">📋</span>
          Autonomous Action Log
        </h2>
        <span className="entry-count">{entries.length} entries</span>
      </div>

      <div className="audit-log" ref={logRef}>
        {entries.length === 0 ? (
          <div className="audit-empty">
            No autonomous actions yet — inject an At-Risk scenario above to see healing in action.
          </div>
        ) : (
          entries.map((entry, i) => {
            const meta = ACTION_META[entry.action] || { icon: '?', color: 'var(--text-secondary)', label: entry.action?.toUpperCase() };
            const ts = new Date(entry.ts * 1000).toLocaleTimeString();
            return (
              <div className="audit-row" key={entry.id} style={{ animationDelay: `${i * 20}ms` }}>
                <span className="audit-time mono">{ts}</span>
                <span className="audit-action" style={{ color: meta.color }}>
                  {meta.icon} {meta.label}
                </span>
                <span className="audit-detail">
                  on <strong>{entry.container_name}</strong>
                  <span className="audit-pipeline"> · {entry.pipeline}</span>
                </span>
                <span className="audit-confidence mono">
                  {Math.round(entry.confidence * 100)}%
                </span>
              </div>
            );
          })
        )}
      </div>
    </section>
  );
}
