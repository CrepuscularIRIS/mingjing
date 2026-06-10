import { render, screen, cleanup } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import type { TraceEvent, WithheldItem } from '../api/types';
import { WithheldDisclosure } from './WithheldDisclosure';

afterEach(cleanup);

function ev(event_type: string, payload: Record<string, unknown>, id = 1): TraceEvent {
  return {
    id,
    run_id: 'r1',
    agent: 'x',
    node: 'x',
    event_type,
    payload_json: JSON.stringify(payload),
    created_at: 0,
  };
}

describe('WithheldDisclosure', () => {
  it('renders nothing when there is nothing to disclose (clean run)', () => {
    const { container } = render(
      <WithheldDisclosure events={[ev('collect_done', { sources_added: 3 })]} withheld={[]} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('explains a thin/0-claim run with source + skip + withheld numbers', () => {
    const events = [
      ev('collect_done', { sources_added: 10 }),
      ev('source_skipped', { reason: 'content_too_thin' }, 2),
      ev('source_skipped', { reason: 'content_too_thin' }, 3),
    ];
    const withheld: WithheldItem[] = [
      { claim_id: 'c1', issue_codes: ['VALUE_UNSUPPORTED'], round: 2 },
      { claim_id: 'c2', issue_codes: ['VALUE_UNSUPPORTED', 'WEAK_EVIDENCE'], round: 2 },
    ];
    render(<WithheldDisclosure events={events} withheld={withheld} />);
    const panel = screen.getByTestId('withheld-disclosure');
    expect(panel).toBeInTheDocument();
    // The numbers that explain the gap are present.
    expect(panel.textContent).toContain('10'); // sources collected
    expect(panel.textContent).toContain('2'); // sources skipped
    // Withheld claims + a human issue label (not the raw code only).
    expect(panel.textContent).toContain('核实'); // VALUE_UNSUPPORTED human label fragment
  });

  it('surfaces claim_skipped (analyst produced no claim) count', () => {
    const events = [
      ev('collect_done', { sources_added: 5 }),
      ev('claim_skipped', { reason: 'analyst_call_raised:AuthenticationError' }, 2),
    ];
    render(<WithheldDisclosure events={events} withheld={[]} />);
    const panel = screen.getByTestId('withheld-disclosure');
    expect(panel.textContent).toContain('1'); // one field produced no claim
  });
});
