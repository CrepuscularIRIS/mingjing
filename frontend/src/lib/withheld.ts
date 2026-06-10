/**
 * Aggregate a run's "what happened to the evidence" story for the self-explaining
 * empty/partial state. A run that gathers sources but admits 0 claims must not
 * render blank — it should say how many sources were collected, how many thin
 * sources were dropped, how many fields produced no claim, and how many claims
 * the QA gate withheld (and why). This is advisory display only.
 */

import type { TraceEvent, WithheldItem } from '../api/types';

export interface WithheldSummary {
  /** Total sources persisted across all collect rounds (sum of sources_added). */
  sourcesCollected: number;
  /** Fetches dropped as too-thin SPA shells (source_skipped events). */
  sourcesSkipped: number;
  /** Fields whose analyst produced no usable claim (claim_skipped events). */
  claimsSkipped: number;
  /** Claims created but withheld from the report by the last QA round. */
  claimsWithheld: number;
  /** Count of each QA issue code across the withheld claims. */
  issueTally: Record<string, number>;
}

/** Human-readable labels for the deterministic QA issue codes. */
const ISSUE_LABELS: Record<string, string> = {
  VALUE_UNSUPPORTED: '结论的值无法在引用来源中核实',
  WEAK_EVIDENCE: '证据强度不足（来源太少或不够权威）',
  LOW_COVERAGE: '证据覆盖率低于门槛',
  SCHEMA_GAP: '缺少必填字段或推理血缘有问题',
  HALLUCINATED_SNIPPET: '引用的片段不在原文中',
  CONTRADICTION: '来源之间相互矛盾',
  INFERENCE_LINEAGE: '推理依赖的前提结论不成立',
};

/** Map a QA issue code to a human label, falling back to the raw code. */
export function issueLabel(code: string): string {
  return ISSUE_LABELS[code] ?? code;
}

function payload(ev: TraceEvent): Record<string, unknown> {
  try {
    const parsed = JSON.parse(ev.payload_json || '{}');
    return parsed && typeof parsed === 'object' ? (parsed as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

export function summarizeWithheld(
  events: TraceEvent[],
  withheld: WithheldItem[],
): WithheldSummary {
  let sourcesCollected = 0;
  let sourcesSkipped = 0;
  let claimsSkipped = 0;

  for (const ev of events) {
    if (ev.event_type === 'collect_done') {
      const n = payload(ev)['sources_added'];
      if (typeof n === 'number') sourcesCollected += n;
    } else if (ev.event_type === 'source_skipped') {
      sourcesSkipped += 1;
    } else if (ev.event_type === 'claim_skipped') {
      claimsSkipped += 1;
    }
  }

  const issueTally: Record<string, number> = {};
  for (const item of withheld) {
    for (const code of item.issue_codes) {
      issueTally[code] = (issueTally[code] ?? 0) + 1;
    }
  }

  return {
    sourcesCollected,
    sourcesSkipped,
    claimsSkipped,
    claimsWithheld: withheld.length,
    issueTally,
  };
}
