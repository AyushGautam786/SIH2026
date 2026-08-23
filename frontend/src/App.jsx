import React, { useState, useEffect, useCallback, useRef } from 'react';
import Header from './components/Header';
import ContainerCard from './components/ContainerCard';
import AuditLog from './components/AuditLog';

const WS_URL  = 'ws://localhost:8000/ws';
const API_URL = 'http://localhost:8000';

export default function App() {
  const [containers, setContainers]   = useState([]);
  const [auditLog,   setAuditLog]     = useState([]);
  const [stats,      setStats]        = useState(null);
  const [connStatus, setConnStatus]   = useState('connecting');
  const wsRef       = useRef(null);
  const reconnTimer = useRef(null);

  // ── Load audit log from REST (on mount + after each action) ──────────────
  const fetchAudit = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/audit?limit=100`);
      const data = await res.json();
      setAuditLog(data);
    } catch { /* silent — websocket will still show live data */ }
  }, []);

  // ── Load stats ────────────────────────────────────────────────────────────
  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/stats`);
      const data = await res.json();
      setStats(data);
    } catch { }
  }, []);

  // ── WebSocket connection with auto-reconnect ──────────────────────────────
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setConnStatus('connecting');
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnStatus('live');
      fetchAudit();
      fetchStats();
    };

    ws.onclose = () => {
      setConnStatus('disconnected');
      reconnTimer.current = setTimeout(connect, 1500);
    };

    ws.onerror = () => ws.close();

    ws.onmessage = (evt) => {
      const msg = JSON.parse(evt.data);
      if (msg.type !== 'tick') return;

      setContainers(msg.containers);

      // If any container just had an action, refresh audit + stats
      const hadAction = msg.containers.some(c => c.action_taken);
      if (hadAction) {
        fetchAudit();
        fetchStats();
      }
    };
  }, [fetchAudit, fetchStats]);

  useEffect(() => {
    connect();
    // Refresh stats every 10 s even without actions
    const statsInterval = setInterval(fetchStats, 10_000);
    return () => {
      clearTimeout(reconnTimer.current);
      clearInterval(statsInterval);
      wsRef.current?.close();
    };
  }, [connect, fetchStats]);

  // ── Inject scenario ───────────────────────────────────────────────────────
  const handleInject = useCallback(async (containerId, scenario) => {
    try {
      await fetch(`${API_URL}/api/inject/${containerId}/${scenario}`, { method: 'POST' });
    } catch { }
  }, []);

  // ── Split containers by state for ordering ────────────────────────────────
  const ordered = [...containers].sort((a, b) => {
    const priority = { at_risk: 0, transient_spike: 1, healthy: 2 };
    return (priority[a.predicted_state] ?? 3) - (priority[b.predicted_state] ?? 3);
  });

  return (
    <div className="app-layout">
      <Header connectionStatus={connStatus} stats={stats} />

      <main className="app-main">
        {/* Fleet grid */}
        <section className="fleet-section">
          <div className="section-header">
            <h2 className="section-title">
              <span className="section-icon">🖥</span>
              Live Fleet
            </h2>
            <span className="section-hint">
              {containers.length} container{containers.length !== 1 ? 's' : ''} monitored
            </span>
          </div>

          {containers.length === 0 ? (
            <div className="fleet-loading">
              <div className="spinner" />
              <span>Waiting for backend…</span>
            </div>
          ) : (
            <div className="fleet-grid">
              {ordered.map(c => (
                <ContainerCard
                  key={c.id}
                  container={c}
                  onInject={handleInject}
                />
              ))}
            </div>
          )}
        </section>

        {/* Audit log */}
        <AuditLog entries={auditLog} />
      </main>

      <footer className="app-footer">
        Pulse prototype · detect → predict → heal · Real RandomForest ML
      </footer>
    </div>
  );
}
