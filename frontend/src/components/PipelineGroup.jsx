import React from 'react';
import ContainerCard from './ContainerCard';
import { STATE_META, worstState } from '../lib/api';

/**
 * Fleet-overview grouping (PPTX slide 11): pipelines rendered as sections,
 * each labelled with its WORST container state for instant health reads.
 */
export default function PipelineGroup({ group, onInject, onSelect }) {
  const status = worstState(group.containers);
  const meta = STATE_META[status] ?? STATE_META.healthy;
  const counts = group.containers.reduce((acc, c) => {
    acc[c.predicted_state] = (acc[c.predicted_state] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <section className="pipeline-group">
      <header className="pipeline-head" style={{ '--state-color': meta.color }}>
        <div className="pipeline-title">
          <span className="pipeline-marker" />
          <h3>{group.pipeline}</h3>
          <span className="state-badge small"><span className={`state-marker ${meta.marker}`} />{meta.label}</span>
        </div>
        <div className="pipeline-meta mono">
          {group.containers.length} containers
          {counts.at_risk ? ` · ${counts.at_risk} at risk` : ''}
          {counts.transient_spike ? ` · ${counts.transient_spike} spiking` : ''}
        </div>
      </header>
      <div className="fleet-grid">
        {group.containers.map((container) => (
          <ContainerCard key={container.id} container={container} onInject={onInject} onSelect={onSelect} />
        ))}
      </div>
    </section>
  );
}
