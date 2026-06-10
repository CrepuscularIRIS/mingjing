import { describe, expect, it } from 'vitest';

import type { TraceEvent, WithheldItem } from '../api/types';
import { issueLabel, summarizeWithheld } from './withheld';

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

describe('summarizeWithheld', () => {
  it('sums sources collected across collect_done events', () => {
    const events = [
      ev('collect_done', { sources_added: 3 }),
      ev('collect_done', { sources_added: 2 }),
    ];
    const s = summarizeWithheld(events, []);
    expect(s.sourcesCollected).toBe(5);
  });

  it('counts source_skipped and claim_skipped events', () => {
    const events = [
      ev('source_skipped', { reason: 'content_too_thin' }),
      ev('source_skipped', { reason: 'content_too_thin' }),
      ev('claim_skipped', { reason: 'analyst_call_raised:AuthenticationError' }),
    ];
    const s = summarizeWithheld(events, []);
    expect(s.sourcesSkipped).toBe(2);
    expect(s.claimsSkipped).toBe(1);
  });

  it('tallies issue codes across withheld claims', () => {
    const withheld: WithheldItem[] = [
      { claim_id: 'c1', issue_codes: ['VALUE_UNSUPPORTED', 'WEAK_EVIDENCE'], round: 2 },
      { claim_id: 'c2', issue_codes: ['VALUE_UNSUPPORTED'], round: 2 },
    ];
    const s = summarizeWithheld([], withheld);
    expect(s.claimsWithheld).toBe(2);
    expect(s.issueTally['VALUE_UNSUPPORTED']).toBe(2);
    expect(s.issueTally['WEAK_EVIDENCE']).toBe(1);
  });

  it('is empty/zeroed for a clean run with no skips or withholds', () => {
    const s = summarizeWithheld([ev('collect_done', { sources_added: 4 })], []);
    expect(s.sourcesSkipped).toBe(0);
    expect(s.claimsSkipped).toBe(0);
    expect(s.claimsWithheld).toBe(0);
    expect(Object.keys(s.issueTally)).toHaveLength(0);
  });
});

describe('issueLabel', () => {
  it('maps known issue codes to human labels', () => {
    expect(issueLabel('VALUE_UNSUPPORTED')).not.toBe('VALUE_UNSUPPORTED');
    expect(issueLabel('WEAK_EVIDENCE')).not.toBe('WEAK_EVIDENCE');
  });

  it('falls back to the raw code for unknown codes', () => {
    expect(issueLabel('SOME_NEW_CODE')).toBe('SOME_NEW_CODE');
  });
});
