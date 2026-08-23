import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ContainerCard from './components/ContainerCard';
import AuditLog from './components/AuditLog';

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws';
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const PREVIEW_CONTAINERS = [
  { id: 'preview-01', name: 'checkout-service-00', pipeline: 'checkout-service', cpu: 32, mem: 41, net: 48, predicted_state: 'healthy', confidence: 0.98, cooldown_seconds_left: 0, last_action: null },
  { id: 'preview-02', name: 'checkout-service-01', pipeline: 'checkout-service', cpu: 67, mem: 38, net: 73, predicted_state: 'transient_spike', confidence: 0.91, cooldown_seconds_left: 0, last_action: null },
  { id: 'preview-03', name: 'catalog-api-00', pipeline: 'catalog-api', cpu: 28, mem: 34, net: 44, predicted_state: 'healthy', confidence: 0.97, cooldown_seconds_left: 0, last_action: null },
  { id: 'preview-04', name: 'catalog-api-01', pipeline: 'catalog-api', cpu: 81, mem: 75, net: 62, predicted_state: 'at_risk', confidence: 0.94, cooldown_seconds_left: 14.2, last_action: 'restart' },
  { id: 'preview-05', name: 'payments-worker-00', pipeline: 'payments-worker', cpu: 24, mem: 29, net: 37, predicted_state: 'healthy', confidence: 0.99, cooldown_seconds_left: 0, last_action: null },
  { id: 'preview-06', name: 'payments-worker-01', pipeline: 'payments-worker', cpu: 46, mem: 51, net: 59, predicted_state: 'healthy', confidence: 0.88, cooldown_seconds_left: 0, last_action: null },
];

const PREVIEW_AUDIT = [
  { id: 'preview-audit-1', ts: Date.now() / 1000 - 92, action: 'restart', container_name: 'catalog-api-01', pipeline: 'catalog-api', confidence: 0.94 },
  { id: 'preview-audit-2', ts: Date.now() / 1000 - 418, action: 'scale', container_name: 'checkout-service-00', pipeline: 'checkout-service', confidence: 0.91 },
];

const PREVIEW_STATS = { total_containers: 6, at_risk_now: 1, total_actions: 12, tick_interval_seconds: 2 };

function useRoute() {
  const getRoute = () => window.location.hash === '#prototype' ? 'prototype' : 'home';
  const [route, setRoute] = useState(getRoute);

  useEffect(() => {
    const revealItems = document.querySelectorAll('[data-reveal]');
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -40px' });
    revealItems.forEach((item) => observer.observe(item));
    return () => observer.disconnect();
  }, [route]);

  useEffect(() => {
    const onHashChange = () => setRoute(getRoute());
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  const navigate = useCallback((nextRoute) => {
    window.location.hash = nextRoute === 'prototype' ? 'prototype' : 'home';
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, []);

  return { route, navigate };
}

export default function App() {
  const { route, navigate } = useRoute();
  const [containers, setContainers] = useState(PREVIEW_CONTAINERS);
  const [auditLog, setAuditLog] = useState(PREVIEW_AUDIT);
  const [stats, setStats] = useState(PREVIEW_STATS);
  const [connStatus, setConnStatus] = useState('connecting');
  const wsRef = useRef(null);
  const reconnTimer = useRef(null);
  const connectRef = useRef(null);

  const fetchAudit = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/audit?limit=100`);
      if (!res.ok) throw new Error('Audit unavailable');
      setAuditLog(await res.json());
    } catch {
      // Keep the seeded preview log when the optional local backend is offline.
    }
  }, []);

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/stats`);
      if (!res.ok) throw new Error('Stats unavailable');
      setStats(await res.json());
    } catch {
      // Preview values keep the testing workspace useful before the backend starts.
    }
  }, []);

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
      reconnTimer.current = setTimeout(() => connectRef.current?.(), 4000);
    };

    ws.onerror = () => ws.close();

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type !== 'tick') return;
        setContainers(msg.containers);
        if (msg.containers.some((container) => container.action_taken)) {
          fetchAudit();
          fetchStats();
        }
      } catch {
        // Ignore malformed development payloads without breaking the UI.
      }
    };
  }, [fetchAudit, fetchStats]);

  useEffect(() => {
    connectRef.current = connect;
    connect();
    const statsInterval = setInterval(fetchStats, 10000);
    return () => {
      clearTimeout(reconnTimer.current);
      clearInterval(statsInterval);
      wsRef.current?.close();
    };
  }, [connect, fetchStats]);

  const handleInject = useCallback(async (containerId, scenario) => {
    setContainers((current) => current.map((container) => container.id === containerId ? {
      ...container,
      predicted_state: scenario === 'at_risk' ? 'at_risk' : 'transient_spike',
      confidence: scenario === 'at_risk' ? 0.94 : 0.91,
      cpu: scenario === 'at_risk' ? 86 : 78,
      mem: scenario === 'at_risk' ? 78 : 38,
      net: scenario === 'at_risk' ? 65 : 84,
    } : container));

    try {
      await fetch(`${API_URL}/api/inject/${containerId}/${scenario}`, { method: 'POST' });
    } catch {
      if (scenario === 'at_risk') {
        const target = containers.find((container) => container.id === containerId);
        if (target) {
          setAuditLog((entries) => [{
            id: `preview-${Date.now()}`,
            ts: Date.now() / 1000,
            action: 'restart',
            container_name: target.name,
            pipeline: target.pipeline,
            confidence: 0.94,
          }, ...entries]);
          setStats((current) => ({ ...current, total_actions: current.total_actions + 1, at_risk_now: 1 }));
        }
      }
    }

    window.setTimeout(() => {
      setContainers((current) => current.map((container) => container.id === containerId ? {
        ...container,
        predicted_state: 'healthy',
        confidence: 0.97,
        cpu: 31,
        mem: 36,
        net: 49,
        cooldown_seconds_left: 0,
      } : container));
    }, scenario === 'at_risk' ? 6500 : 4200);
  }, [containers]);

  return (
    <div className="site-shell">
      <div className="ambient-canvas" aria-hidden="true"><span className="ambient-orb ambient-orb-one" /><span className="ambient-orb ambient-orb-two" /><span className="ambient-orb ambient-orb-three" /></div>
      <SiteNav route={route} onNavigate={navigate} />
      {route === 'prototype' ? (
        <PrototypePage
          containers={containers}
          auditLog={auditLog}
          stats={stats}
          connStatus={connStatus}
          onInject={handleInject}
          onNavigate={navigate}
        />
      ) : (
        <LandingPage onNavigate={navigate} />
      )}
    </div>
  );
}

function SiteNav({ route, onNavigate }) {
  const [scrollState, setScrollState] = useState({ scrolled: false, progress: 0 });

  useEffect(() => {
    const onScroll = () => {
      const maxScroll = document.documentElement.scrollHeight - window.innerHeight;
      setScrollState({ scrolled: window.scrollY > 12, progress: maxScroll > 0 ? (window.scrollY / maxScroll) * 100 : 0 });
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <header className={`site-nav ${scrollState.scrolled ? 'site-nav-scrolled' : ''}`}>
      <span className="scroll-progress" style={{ width: `${scrollState.progress}%` }} aria-hidden="true" />
      <button className="brand-lockup" onClick={() => onNavigate('home')} aria-label="Pulse home">
        <span className="brand-mark" aria-hidden="true"><span /><span /></span>
        <span className="brand-word">pulse<span className="brand-dot">.</span></span>
      </button>
      <nav className="primary-nav" aria-label="Primary navigation">
        <a href="#how-it-works">How it works</a>
        <a href="#architecture">Architecture</a>
        <button className={route === 'prototype' ? 'nav-link active' : 'nav-link'} onClick={() => onNavigate('prototype')}>Open prototype <span aria-hidden="true">↗</span></button>
      </nav>
      <div className="nav-status"><span className="status-pip" /> Research prototype</div>
    </header>
  );
}

function LandingPage({ onNavigate }) {
  return (
    <main>
      <section className="hero-section section-pad" data-reveal="hero">
        <div className="hero-grid page-width">
          <div className="hero-copy">
            <p className="eyebrow"><span className="eyebrow-line" /> Predictive infrastructure / 01</p>
            <h1>Keep your services<br /><em>one step ahead.</em></h1>
            <p className="hero-lede">Pulse watches the shape of container health, not just the threshold. It learns the difference between a harmless burst and the slow failure already forming underneath.</p>
            <div className="hero-actions">
              <button className="button button-primary" onClick={() => onNavigate('prototype')}>Run the live prototype <span aria-hidden="true">↗</span></button>
              <a className="text-link" href="#how-it-works">See how Pulse thinks <span aria-hidden="true">↓</span></a>
            </div>
            <div className="hero-proof"><span className="proof-rule" /><span>Real RandomForest model</span><span>·</span><span>WebSocket telemetry</span><span>·</span><span>Autonomous healing</span></div>
          </div>
          <HeroTelemetry />
        </div>
      </section>

      <section className="signal-strip" data-reveal="strip"><div className="page-width strip-grid"><div><span className="strip-number">01</span><span>Observe the signal</span></div><div><span className="strip-number">02</span><span>Interpret the pattern</span></div><div className="strip-numbered-active"><span className="strip-number">03</span><span>Make the smallest safe move</span></div><div className="strip-note">A calm system is a system that can explain itself.</div></div></section>

      <section id="how-it-works" className="story-section section-pad page-width" data-reveal="section">
        <div className="section-intro"><p className="eyebrow"><span className="eyebrow-line" /> The detect → predict → heal loop</p><h2>Not another alarm.<br /><span>A decision engine.</span></h2><p>Most monitors tell you something is wrong after it is already expensive. Pulse keeps a short memory of every container, combines present load with what came before, and acts only when the pattern deserves intervention.</p></div>
        <div className="loop-grid">
          <LoopStep index="01" title="Detect" accent="violet" detail="A lightweight telemetry source samples CPU, memory, and network behavior across the fleet." visual={<SignalVisual />} />
          <LoopStep index="02" title="Predict" accent="blue" detail="A six-feature RandomForest classifier separates healthy flow, transient spikes, and sustained risk." visual={<ModelVisual />} />
          <LoopStep index="03" title="Heal" accent="green" detail="Pulse chooses a restart or scale action, respects a cooldown, and records the decision." visual={<HealVisual />} />
        </div>
      </section>

      <section id="architecture" className="architecture-section section-pad" data-reveal="section"><div className="page-width"><div className="section-intro compact"><p className="eyebrow"><span className="eyebrow-line" /> Designed for the hand-off to production</p><h2>Prototype today.<br /><span>Replace pieces, not the idea.</span></h2></div><div className="architecture-grid"><ArchitectureCard label="Telemetry source" prototype="SimulatedFleet" production="DockerTelemetrySource" /><ArchitectureCard label="Cooldown guard" prototype="In-memory store" production="Redis / TTL" /><ArchitectureCard label="Audit trail" prototype="SQLite" production="Postgres / TimescaleDB" /><ArchitectureCard label="Action executor" prototype="Simulated actions" production="Docker / HPA APIs" /></div></div></section>

      <section className="proof-section section-pad page-width" data-reveal="section"><div className="proof-layout"><div className="proof-copy"><p className="eyebrow"><span className="eyebrow-line" /> Why this matters</p><h2>Context is the<br /><em>reliability feature.</em></h2><p>A spike is not a failure. A rising rolling average with growing memory delta might be. Pulse gives the model enough context to tell those stories apart—so your team gets fewer false positives and more useful actions.</p><button className="button button-secondary" onClick={() => onNavigate('prototype')}>Test both scenarios <span aria-hidden="true">↗</span></button></div><ComparisonPanel /></div></section>

      <section className="cta-section section-pad" data-reveal="section"><div className="page-width cta-card"><div><p className="eyebrow"><span className="eyebrow-line" /> Your turn</p><h2>Give the fleet<br /><em>a little foresight.</em></h2></div><div className="cta-side"><p>Inject a transient spike. Then inject sustained risk. Watch what Pulse ignores—and what it quietly fixes.</p><button className="button button-primary" onClick={() => onNavigate('prototype')}>Open the prototype <span aria-hidden="true">↗</span></button></div></div></section>

      <footer className="site-footer page-width"><div className="footer-brand"><span className="brand-mark small" aria-hidden="true"><span /><span /></span><span>pulse.</span></div><p>Predictive Utilisation &amp; Self-Healing Engine · SIH 2026</p><p className="footer-note">Built to detect the difference.</p></footer>
    </main>
  );
}

function HeroTelemetry() {
  const points = [34, 42, 38, 51, 46, 68, 59, 74, 69, 86, 72, 64, 57, 62, 55];
  return <div className="hero-visual"><div className="visual-topline"><span><span className="live-dot" /> Live fleet signal</span><span className="mono">T+00:02.18</span></div><div className="telemetry-card"><div className="telemetry-heading"><div><span className="tiny-label">CURRENT OBSERVATION</span><strong>checkout-service-01</strong></div><span className="state-pill state-pill-spike">TRANSIENT SPIKE</span></div><div className="telemetry-chart" aria-label="Telemetry signal chart">{points.map((point, index) => <span key={index} style={{ height: `${point}%`, animationDelay: `${index * 50}ms` }} />)}<div className="chart-baseline" /></div><div className="telemetry-readings"><div><span>CPU</span><strong>78.4%</strong></div><div><span>MEM</span><strong>38.1%</strong></div><div><span>ROLLING AVG</span><strong className="reading-calm">41.2%</strong></div></div><div className="telemetry-verdict"><span className="verdict-icon">✓</span><div><span className="tiny-label">MODEL VERDICT</span><strong>Watch, don’t wake the team.</strong></div><span className="verdict-confidence mono">91%</span></div></div><div className="visual-caption"><span className="mono">/ pulse-model /</span><span>short-lived load is not an incident</span></div></div>;
}

function LoopStep({ index, title, accent, detail, visual }) { return <article className={`loop-step loop-step-${accent}`}><div className="step-head"><span className="step-index">{index}</span><h3>{title}</h3></div><p>{detail}</p>{visual}</article>; }
function SignalVisual() { return <div className="step-visual signal-visual"><div className="signal-bars">{[42, 58, 38, 71, 46, 82, 63, 49].map((height, index) => <span key={index} style={{ height: `${height}%` }} />)}</div><div className="visual-label"><span className="signal-dot" /> six features in, one signal out</div></div>; }
function ModelVisual() { return <div className="step-visual model-visual"><div className="model-node node-a">cpu</div><div className="model-node node-b">mem</div><div className="model-node node-c">avg</div><div className="model-node node-d">risk</div><div className="model-connectors" /><div className="visual-label">context over thresholds</div></div>; }
function HealVisual() { return <div className="step-visual heal-visual"><div className="heal-ring"><span>OK</span></div><div><span className="tiny-label">ACTION LOGGED</span><strong>restart · 94%</strong></div></div>; }
function ArchitectureCard({ label, prototype, production }) { return <article className="architecture-card"><span className="tiny-label">{label}</span><div className="architecture-row"><span className="arch-key">Prototype</span><strong>{prototype}</strong></div><div className="architecture-row production-row"><span className="arch-key">Production</span><strong>{production}</strong></div></article>; }
function ComparisonPanel() { return <div className="comparison-panel"><div className="comparison-header"><span>Scenario</span><span>Model sees</span><span>Response</span></div><div className="comparison-row"><span className="comparison-scenario"><i className="scenario-dot orange" /> Short burst</span><span><strong>High CPU</strong><small>low rolling avg</small></span><span className="response-muted">Observe</span></div><div className="comparison-row active"><span className="comparison-scenario"><i className="scenario-dot red" /> Sustained risk</span><span><strong>High CPU + MEM</strong><small>rising over time</small></span><span className="response-live">Heal <span>↗</span></span></div><div className="comparison-foot"><span className="mono">6 features</span><span>make the context count</span></div></div>; }

function PrototypePage({ containers, auditLog, stats, connStatus, onInject, onNavigate }) {
  const ordered = useMemo(() => [...containers].sort((a, b) => ({ at_risk: 0, transient_spike: 1, healthy: 2 }[a.predicted_state] ?? 3) - ({ at_risk: 0, transient_spike: 1, healthy: 2 }[b.predicted_state] ?? 3)), [containers]);
  return <main className="prototype-page"><section className="prototype-hero page-width" data-reveal="hero"><div><button className="back-link" onClick={() => onNavigate('home')}>← Back to overview</button><p className="eyebrow"><span className="eyebrow-line" /> Prototype workspace</p><h1>See Pulse<br /><em>make the call.</em></h1><p>Inject two very different kinds of pressure into the fleet. The model will decide when to stay calm—and when to act.</p></div><div className="prototype-legend"><div className="legend-line"><span className="live-dot" /> <strong>{connStatus === 'live' ? 'Backend connected' : 'Preview mode'}</strong></div><span className="mono">TICK / {stats?.tick_interval_seconds ?? 2}s</span><span className="legend-copy">{connStatus === 'live' ? 'Streaming live telemetry from FastAPI + WebSocket.' : 'Showing seeded telemetry. Start the backend for live updates.'}</span></div></section><section className="workspace page-width" data-reveal="section"><div className="workspace-toolbar"><div><span className="tiny-label">FLEET OVERVIEW</span><h2>Six containers, one clear picture.</h2></div><div className="toolbar-stats"><HeaderStat label="Monitored" value={stats?.total_containers ?? containers.length} /><HeaderStat label="At risk" value={stats?.at_risk_now ?? 0} accent="red" /><HeaderStat label="Actions" value={stats?.total_actions ?? auditLog.length} accent="violet" /></div></div><div className="workspace-grid"><section className="fleet-panel"><div className="panel-heading"><div><span className="tiny-label">LIVE CONTAINERS</span><p>{containers.length} services · sorted by urgency</p></div><span className="panel-dot"><span /> streaming</span></div><div className="fleet-grid">{ordered.map((container) => <ContainerCard key={container.id} container={container} onInject={onInject} />)}</div></section><aside className="workspace-side"><AuditLog entries={auditLog} /><section className="test-card"><span className="tiny-label">QUICK TEST</span><h3>Watch the model reason.</h3><p>Try a short spike first. It should be noticed, but not healed. Then create sustained risk to trigger an autonomous action.</p><div className="test-rule"><span>01</span><span>Inject Spike</span><span>→</span></div><div className="test-rule"><span>02</span><span>Inject At-Risk</span><span>→</span></div></section></aside></div></section><footer className="site-footer page-width"><div className="footer-brand"><span className="brand-mark small" aria-hidden="true"><span /><span /></span><span>pulse.</span></div><p>Prototype workspace · <button className="footer-link" onClick={() => onNavigate('home')}>Return to the story</button></p><p className="footer-note">detect → predict → heal</p></footer></main>;
}
function HeaderStat({ label, value, accent }) { return <div className={`header-stat ${accent ? `header-stat-${accent}` : ''}`}><strong>{value}</strong><span>{label}</span></div>; }
