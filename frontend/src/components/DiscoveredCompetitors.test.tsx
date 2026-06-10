/**
 * DiscoveredCompetitors panel — renders the Discovery-Mode outcome from the
 * polled trace stream across its three states (in-progress / empty / done), and
 * renders nothing for a Directed-Mode run (no discovery events).
 */
import { render, screen, cleanup } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import type { TraceEvent } from '../api/types';
import { DiscoveredCompetitors } from './DiscoveredCompetitors';

afterEach(cleanup);

function ev(id: number, type: string, payload: Record<string, unknown>): TraceEvent {
  return {
    id,
    run_id: 'r',
    agent: 'collector',
    node: 'discover',
    event_type: type,
    payload_json: JSON.stringify(payload),
    created_at: 1749340800,
  };
}

describe('DiscoveredCompetitors', () => {
  it('renders nothing for a Directed-Mode run (no discovery events)', () => {
    const { container } = render(<DiscoveredCompetitors events={[ev(1, 'collect_start', {})]} />);
    expect(container.firstChild).toBeNull();
  });

  it('shows an in-progress message when only discovery_started is present', () => {
    render(<DiscoveredCompetitors events={[ev(1, 'discovery_started', { category: 'CRM' })]} />);
    expect(screen.getByTestId('discovered-competitors')).toBeInTheDocument();
    expect(screen.getByText(/正在从/)).toBeInTheDocument();
  });

  it('shows an honest empty state for discovery_empty', () => {
    render(
      <DiscoveredCompetitors
        events={[ev(1, 'discovery_started', { category: 'X' }), ev(2, 'discovery_empty', {})]}
      />,
    );
    expect(screen.getByText(/未发现可分析的竞品/)).toBeInTheDocument();
  });

  it('renders selected chips + ranked candidates for competitors_discovered', () => {
    render(
      <DiscoveredCompetitors
        events={[
          ev(1, 'discovery_started', { category: 'AI Agent' }),
          ev(2, 'competitors_discovered', {
            selected: ['Manus', 'Coze'],
            candidates: [
              { name: 'Manus', source_count: 4, has_official: true },
              { name: 'Coze', source_count: 2, has_official: true },
              { name: 'Noise', source_count: 1, has_official: false },
            ],
            queries: ['q'],
          }),
        ]}
      />,
    );
    const chips = screen.getAllByTestId('discovered-chip');
    expect(chips.map((c) => c.textContent)).toEqual(['Manus', 'Coze']);
    // A non-selected candidate still appears in the ranked list.
    expect(screen.getByText(/Noise/)).toBeInTheDocument();
    expect(screen.getByText(/4 来源/)).toBeInTheDocument();
    // The "N 来源" chip carries a tooltip clarifying it is a discovery signal count,
    // NOT QA-admitted evidence — prevents judges from misreading it as proven sources.
    const sourceChips = screen.getAllByTitle(/发现阶段的提及/);
    expect(sourceChips.length).toBeGreaterThan(0);
    expect(sourceChips[0].title).toContain('非已通过 QA 采信的证据来源');
  });
});
