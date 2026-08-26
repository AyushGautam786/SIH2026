import React from 'react';
import { STATE_META, groupByPipeline, worstState } from '../lib/api';

/**
 * Interactive topology graph (PPTX slide 11): pipeline nodes connected to
 * their container nodes. Pure SVG - no diagram library (TASKS rule #3).
 * Edge/node colour = state; click a container node to drill in.
 */
export default function TopologyGraph({ containers, selectedId, onSelect }) {
  const groups = groupByPipeline(containers);

  const NODE_W = 168;
  const NODE_H = 44;
  const GAP_X = 40;
  const GAP_Y = 16;
  const TOP = 96;
  const colW = NODE_W + GAP_X;
  const width = Math.max(560, groups.length * colW + GAP_X);
  const maxRows = Math.max(...groups.map((g) => g.containers.length), 1);
  const height = TOP + maxRows * (NODE_H + GAP_Y) + 24;

  return (
    <div className="topology-wrap">
      <svg viewBox={`0 0 ${width} ${height}`} className="topology-svg" role="img" aria-label="Fleet topology graph">
        {groups.map((group, gi) => {
          const cx = GAP_X + gi * colW + NODE_W / 2;
          const status = worstState(group.containers);
          const meta = STATE_META[status] ?? STATE_META.healthy;
          return (
            <g key={group.pipeline}>
              {/* pipeline node */}
              <rect
                x={cx - NODE_W / 2} y={20} width={NODE_W} height={48} rx={12}
                fill="var(--surface)" stroke={meta.color} strokeWidth={status === 'healthy' ? 1 : 2}
              />
              <text x={cx} y={40} textAnchor="middle" className="topo-pipeline-name">{group.pipeline}</text>
              <text x={cx} y={56} textAnchor="middle" className="topo-pipeline-status" fill={meta.color}>
                {meta.label}
              </text>

              {group.containers.map((c, ci) => {
                const cmeta = STATE_META[c.predicted_state] ?? STATE_META.healthy;
                const nx = GAP_X + gi * colW;
                const ny = TOP + ci * (NODE_H + GAP_Y);
                const selected = selectedId === c.id;
                return (
                  <g key={c.id} className="topo-container" onClick={() => onSelect?.(c)}>
                    {/* edge */}
                    <line
                      x1={cx} y1={68} x2={nx + NODE_W / 2} y2={ny}
                      stroke={cmeta.color} strokeWidth={selected ? 2.4 : 1.2} strokeOpacity={selected ? 1 : 0.55}
                    />
                    <rect
                      x={nx} y={ny} width={NODE_W} height={NODE_H} rx={10}
                      fill={selected ? 'var(--canvas-warm)' : 'var(--canvas-warm)'}
                      stroke={cmeta.color} strokeWidth={selected ? 2.4 : 1}
                    />
                    <circle cx={nx + 16} cy={ny + NODE_H / 2} r={5} fill={cmeta.color} />
                    <text x={nx + 30} y={ny + 19} className="topo-cname">{truncate(c.name)}</text>
                    <text x={nx + 30} y={ny + 33} className="topo-cmeta">
                      cpu {Math.round(c.cpu)}% · mem {Math.round(c.mem)}%
                    </text>
                  </g>
                );
              })}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function truncate(s, n = 22) {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s;
}
