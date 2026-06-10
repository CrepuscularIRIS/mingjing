import { describe, expect, it } from 'vitest';

import type { TraceEvent } from '../api/types';
import { mergeTraceEvents } from './trace';

function ev(id: number): TraceEvent {
  return {
    id,
    run_id: 'r1',
    agent: 'x',
    node: 'x',
    event_type: 'node_enter',
    payload_json: '{}',
    created_at: 0,
  };
}

describe('mergeTraceEvents', () => {
  it('appends only events not already present (dedup by id)', () => {
    const prev = [ev(1), ev(2)];
    const merged = mergeTraceEvents(prev, [ev(2), ev(3)]);
    expect(merged.map((e) => e.id)).toEqual([1, 2, 3]);
  });

  it('is idempotent when the SAME batch arrives twice (the StrictMode/poll-race bug)', () => {
    const batch = [ev(1), ev(2), ev(3)];
    const once = mergeTraceEvents([], batch);
    const twice = mergeTraceEvents(once, batch);
    expect(twice.map((e) => e.id)).toEqual([1, 2, 3]); // no duplicates
    expect(twice).toBe(once); // no fresh events → same reference (no re-render)
  });

  it('preserves order and returns prev reference when nothing is fresh', () => {
    const prev = [ev(1), ev(2)];
    expect(mergeTraceEvents(prev, [])).toBe(prev);
    expect(mergeTraceEvents(prev, [ev(1)])).toBe(prev);
  });

  it('keeps first occurrence and ignores later duplicates within incoming', () => {
    const merged = mergeTraceEvents([ev(1)], [ev(2), ev(2), ev(3)]);
    expect(merged.map((e) => e.id)).toEqual([1, 2, 3]);
  });
});
