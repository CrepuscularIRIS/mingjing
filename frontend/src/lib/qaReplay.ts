/**
 * Auto-select a claim for QA Replay when the user lands on the tab without one.
 *
 * The QA Replay view is the headline differentiator (weak→strong self-correction),
 * but it used to render an empty "pick a claim" prompt until the user manually
 * navigated from the Final Report. This picks the best replayable claim from the
 * run's trace so the view self-demonstrates: a claim that was rejected by QA
 * (qa_fail → it has ≥2 versions) is replayable; one that was rejected AND later
 * passed (qa_pass carries `claim_ids`) tells the complete weak→strong story and
 * is preferred.
 */

import type { TraceEvent } from '../api/types';
import { parseEventPayload } from './trace';

/** Evidence-tier ordering, lowest→highest. Drives "did the claim get stronger?". */
export const EVIDENCE_RANK: Record<string, number> = { weak: 0, moderate: 1, strong: 2 };

/**
 * True when `to` is a strictly stronger evidence tier than `from`.
 * Used so the QA Replay reveal/celebration fires for weak→moderate AND
 * weak→strong — not only weak→strong (the canonical money-shot is weak→moderate).
 */
export function isStrengthUpgrade(from: string, to: string): boolean {
  return (EVIDENCE_RANK[to] ?? 0) > (EVIDENCE_RANK[from] ?? 0);
}

export interface ReplayClaimSummary {
  id: string;
  /** True = rejected by QA and later re-passed (full weak→strong arc). */
  upgraded: boolean;
}

/**
 * Every replayable claim for a run, ordered so the strongest story comes first:
 * rejected-then-passed claims (full weak→strong arc, `upgraded: true`) before
 * claims that were rejected but not yet re-passed. Lets the QA Replay view offer
 * a selector across all reworked claims instead of only the single best one.
 */
export function replayClaimSummaries(events: TraceEvent[]): ReplayClaimSummary[] {
  const failedOrder: string[] = [];
  const failed = new Set<string>();
  const passedAfterFail = new Set<string>();

  for (const ev of events) {
    const payload = parseEventPayload(ev);
    if (ev.event_type === 'qa_fail') {
      const cid = payload['claim_id'];
      if (typeof cid === 'string' && !failed.has(cid)) {
        failed.add(cid);
        failedOrder.push(cid);
      }
    } else if (ev.event_type === 'qa_pass') {
      const ids = payload['claim_ids'];
      if (Array.isArray(ids)) {
        for (const id of ids) {
          if (typeof id === 'string' && failed.has(id)) passedAfterFail.add(id);
        }
      }
    }
  }

  const passed = failedOrder
    .filter((cid) => passedAfterFail.has(cid))
    .map((id) => ({ id, upgraded: true }));
  const onlyFailed = failedOrder
    .filter((cid) => !passedAfterFail.has(cid))
    .map((id) => ({ id, upgraded: false }));
  return [...passed, ...onlyFailed];
}

/** All replayable claim ids (strongest story first). */
export function pickReplayClaimIds(events: TraceEvent[]): string[] {
  return replayClaimSummaries(events).map((s) => s.id);
}

/**
 * The single best replayable claim (full weak→strong story preferred). Kept as a
 * thin wrapper for the auto-select-on-landing path.
 */
export function pickReplayClaimId(events: TraceEvent[]): string | null {
  const ids = pickReplayClaimIds(events);
  return ids.length > 0 ? ids[0] : null;
}
