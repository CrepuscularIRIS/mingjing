import { describe, expect, it } from 'vitest';

import type { TraceEvent } from '../api/types';
import { pickReplayClaimId } from './qaReplay';

function ev(event_type: string, payload: Record<string, unknown>, id = 1): TraceEvent {
  return {
    id,
    run_id: 'r1',
    agent: 'qa',
    node: 'qa',
    event_type,
    payload_json: JSON.stringify(payload),
    created_at: 0,
  };
}

describe('pickReplayClaimId', () => {
  it('returns null when no claim was ever rejected', () => {
    expect(pickReplayClaimId([])).toBeNull();
    expect(pickReplayClaimId([ev('qa_pass', { claim_ids: ['c1'] })])).toBeNull();
  });

  it('picks a rejected claim (it has ≥2 versions to replay)', () => {
    const events = [ev('qa_fail', { claim_id: 'c1', code: 'WEAK_EVIDENCE' })];
    expect(pickReplayClaimId(events)).toBe('c1');
  });

  it('prefers a claim that was rejected then later passed (complete weak→strong story)', () => {
    // c1 only failed; c2 failed then passed → c2 is the better self-demo.
    const events = [
      ev('qa_fail', { claim_id: 'c1', code: 'WEAK_EVIDENCE' }, 1),
      ev('qa_fail', { claim_id: 'c2', code: 'LOW_COVERAGE' }, 2),
      ev('qa_pass', { claim_ids: ['c2'] }, 3),
    ];
    expect(pickReplayClaimId(events)).toBe('c2');
  });

  it('falls back to a rejected-only claim when none passed after failing', () => {
    const events = [
      ev('qa_fail', { claim_id: 'c1', code: 'WEAK_EVIDENCE' }, 1),
      ev('qa_fail', { claim_id: 'c1', code: 'WEAK_EVIDENCE' }, 2),
    ];
    expect(pickReplayClaimId(events)).toBe('c1');
  });
});
