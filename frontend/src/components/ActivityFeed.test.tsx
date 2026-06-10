/**
 * ActivityFeed tests — focus on consecutive-duplicate collapsing.
 *
 * Bursty collectors can emit the same line ~20x in a second, which reads like a
 * stuck loop. The feed collapses runs of consecutive identical events into one
 * row carrying a "×N" count badge, while preserving ordering and distinct rows.
 */

import { render, screen, cleanup, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import type { TraceEvent } from '../api/types';
import ActivityFeed from './ActivityFeed';

afterEach(cleanup);

function ev(id: number, agent: string, eventType: string, competitor: string): TraceEvent {
  return {
    id,
    run_id: 'r1',
    agent,
    node: null,
    event_type: eventType,
    payload: { competitor },
    created_at: 1700000000,
  };
}

describe('ActivityFeed dedup', () => {
  it('collapses consecutive identical events into one row with a count', () => {
    const dupes: TraceEvent[] = Array.from({ length: 20 }, (_, i) =>
      ev(i + 1, 'collector', 'collect_done', 'Notion'),
    );
    render(<ActivityFeed events={dupes} />);

    // 20 identical events render as a single row...
    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(1);
    // ...with a ×20 count badge.
    expect(screen.getByTestId('event-count')).toHaveTextContent('×20');
  });

  it('keeps distinct and non-consecutive events as separate rows', () => {
    const events: TraceEvent[] = [
      ev(1, 'collector', 'collect_done', 'Notion'),
      ev(2, 'collector', 'collect_done', 'Notion'),
      ev(3, 'collector', 'collect_done', 'Linear'), // different detail
      ev(4, 'collector', 'collect_done', 'Notion'), // back to Notion (non-consecutive)
    ];
    render(<ActivityFeed events={events} />);

    const items = screen.getAllByRole('listitem');
    // Notion×2, Linear×1, Notion×1 => 3 rows.
    expect(items).toHaveLength(3);
    // Only the first row carries a count badge (×2).
    const badges = screen.getAllByTestId('event-count');
    expect(badges).toHaveLength(1);
    expect(badges[0]).toHaveTextContent('×2');
    // Ordering preserved: first row is the collapsed Notion pair.
    expect(within(items[0]).getByTestId('event-count')).toBeInTheDocument();
  });

  it('renders single events without a count badge', () => {
    render(<ActivityFeed events={[ev(1, 'qa', 'qa_pass', 'Notion')]} />);
    expect(screen.getAllByRole('listitem')).toHaveLength(1);
    expect(screen.queryByTestId('event-count')).not.toBeInTheDocument();
  });
});
