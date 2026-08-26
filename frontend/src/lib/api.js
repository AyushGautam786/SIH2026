// Shared backend client + fleet helpers.
// Every REST/WS access goes through here so the preview-fallback behaviour
// lives in exactly one place (TASKS.md Phase 9 contract).

export const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws';
export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

/** GET helper that never throws - returns `fallback` when offline. */
export async function getJson(path, fallback = null) {
  try {
    const res = await fetch(`${API_URL}${path}`);
    if (!res.ok) throw new Error(String(res.status));
    return await res.json();
  } catch {
    return fallback;
  }
}

/** Demo control: inject a spike/at_risk episode (backend may be offline). */
export function injectScenario(containerId, scenario) {
  return fetch(`${API_URL}/api/inject/${containerId}/${scenario}`, { method: 'POST' }).catch(() => {});
}

export const STATE_META = {
  healthy: { label: 'HEALTHY', color: 'var(--green)', dimColor: 'var(--green-dim)', marker: 'ok' },
  transient_spike: { label: 'SPIKE', color: 'var(--orange)', dimColor: 'var(--orange-dim)', marker: 'watch' },
  at_risk: { label: 'AT RISK', color: 'var(--red)', dimColor: 'var(--red-dim)', marker: 'act' },
};

export const STATE_SEVERITY = { at_risk: 0, transient_spike: 1, healthy: 2 };

/** Pipeline status = its WORST container state (PPTX slide 11). */
export function worstState(containers) {
  return [...containers].sort(
    (a, b) => (STATE_SEVERITY[a.predicted_state] ?? 3) - (STATE_SEVERITY[b.predicted_state] ?? 3),
  )[0]?.predicted_state ?? 'healthy';
}

/** Group containers by pipeline, preserving first-seen order. */
export function groupByPipeline(containers) {
  const groups = new Map();
  for (const c of containers) {
    if (!groups.has(c.pipeline)) groups.set(c.pipeline, []);
    groups.get(c.pipeline).push(c);
  }
  return [...groups.entries()].map(([pipeline, members]) => ({ pipeline, containers: members }));
}

/**
 * Rolling per-container metric history from WS ticks. PURE: returns a new
 * Map so it can drive React state directly. Mirrors what
 * /api/history/{id} returns so charts work online AND offline.
 */
export function pushHistory(historyMap, tickContainers, cap = 60) {
  const next = new Map(historyMap);
  const ts = Date.now() / 1000;
  for (const c of tickContainers) {
    const arr = [...(next.get(c.id) ?? [])];
    arr.push({ ts, cpu: c.cpu, mem: c.mem, net: c.net });
    while (arr.length > cap) arr.shift();
    next.set(c.id, arr);
  }
  return next;
}

/** Feature readout mirrored from ml_model.py FEATURE_NAMES semantics. */
export function featuresFromHistory(history) {
  if (!history || history.length === 0) return null;
  const cpu = history.map((p) => p.cpu);
  const mem = history.map((p) => p.mem);
  const net = history.map((p) => p.net);
  return {
    cpu_avg_1m: avg(cpu.slice(-20)),
    mem_delta_30s: mem[mem.length - 1] - mem[Math.max(0, mem.length - 10)],
    net_std_1m: std(net.slice(-20)),
    cpu_mem_ratio: cpu[cpu.length - 1] / Math.max(1, mem[mem.length - 1]),
  };
}

const avg = (a) => (a.length ? a.reduce((s, v) => s + v, 0) / a.length : 0);
const std = (a) => {
  if (!a.length) return 0;
  const m = avg(a);
  return Math.sqrt(avg(a.map((v) => (v - m) ** 2)));
};
