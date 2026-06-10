/**
 * Shared fixtures + helpers for the FinalReport test suite.
 *
 * Extracted VERBATIM from the original FinalReport.test.tsx so the split test
 * files (FinalReport.test.tsx + FinalReport.export.test.tsx) reuse identical
 * mock payloads, the default mock wiring, and the render helpers. No assertion
 * or testid is changed here — this module only holds setup that was previously
 * duplicated at module scope.
 */

import { render } from '@testing-library/react';

import type {
  ClaimCorrectionResponse,
  ClaimHistoryResponse,
  ReportResponse,
  SourceProvenance,
  SynthesisResponse,
  TraceEvent,
} from '../api/types';
import { FinalReport } from './FinalReport';

export const MOCK_REPORT: ReportResponse = {
  sections: [
    {
      schema_field: 'pricing',
      claims: [
        {
          id: 'c1',
          competitor: 'Acme',
          statement: 'Acme starter plan costs $10/mo.',
          evidence_strength: 'strong',
          value: { amount: 10 },
          evidence_source_ids: ['s1', 's2'],
          version: 2,
        },
        {
          id: 'c2',
          competitor: 'Beta',
          statement: 'Beta lacks a free tier.',
          evidence_strength: 'weak',
          value: {},
          evidence_source_ids: ['s3'],
          version: 1,
        },
      ],
    },
    {
      schema_field: 'support',
      claims: [
        {
          id: 'c3',
          competitor: 'Acme',
          statement: 'Acme offers email support only.',
          evidence_strength: 'moderate',
          value: {},
          evidence_source_ids: ['s4'],
          version: 1,
        },
      ],
    },
  ],
  strength_tally: { strong: 1, moderate: 1, weak: 1 },
};

export const MOCK_SOURCE: SourceProvenance = {
  id: 's1',
  url: 'https://acme.example/pricing',
  source_mode: 'LIVE',
  source_type: 'web',
  fetched_at: 1780524000,
  raw_text: 'Our plans: Acme starter plan costs $10/mo. Pro is $30/mo.',
  content_hash: 'deadbeefcafe',
};

export const MOCK_HISTORY_SINGLE: ClaimHistoryResponse = {
  claim_id: 'c1',
  versions: [
    {
      id: 'c1',
      statement: 'Acme starter plan costs $10/mo.',
      evidence_strength: 'strong',
      value: { amount: 10 },
      evidence_source_ids: ['s1'],
      version: 1,
      produced_by: 'collector',
    },
  ],
};

export const MOCK_HISTORY_MULTI: ClaimHistoryResponse = {
  claim_id: 'c1',
  versions: [
    {
      id: 'c1',
      statement: 'Acme starter plan costs $10/mo.',
      evidence_strength: 'strong',
      value: { amount: 10 },
      evidence_source_ids: ['s1'],
      version: 1,
      produced_by: 'collector',
    },
    {
      id: 'c1',
      statement: 'Acme starter plan costs $10/month (corrected).',
      evidence_strength: 'strong',
      value: { amount: 10 },
      evidence_source_ids: ['s1'],
      version: 2,
      produced_by: 'human:correction',
    },
  ],
};

export const MOCK_CORRECTION_RESPONSE: ClaimCorrectionResponse = {
  claim_id: 'c1',
  version: 3,
  status: 'pass',
  produced_by: 'human:correction',
};

// A full CI-brief synthesis payload citing the ledger claim ids (c1/c2/c3).
export const MOCK_SYNTHESIS: SynthesisResponse = {
  bluf: { text: 'Acme leads on price but trails on support.', claim_ids: ['c1'] },
  recommendations: [
    { text: 'Undercut Acme support SLA to win enterprise.', claim_ids: ['c3'] },
  ],
  swot: {
    strengths: [{ text: 'Acme has the lowest entry price.', claim_ids: ['c1'] }],
    weaknesses: [{ text: 'Beta has no free tier.', claim_ids: ['c2'] }],
    opportunities: [{ text: 'Email-only support is a wedge.', claim_ids: ['c3'] }],
    threats: [{ text: 'Acme could add phone support.', claim_ids: [] }],
  },
  comparison: [{ text: 'Acme $10/mo vs Beta paid-only.', claim_ids: ['c1', 'c2'] }],
  intelligence_gap: [{ text: 'No data on enterprise discounts.', claim_ids: [] }],
  key_assumptions: [{ text: 'Public pricing reflects negotiated rates.', claim_ids: [] }],
  referenced_claim_ids: ['c1', 'c2', 'c3'],
};

export function renderReport() {
  return render(
    <FinalReport
      runId="run-1"
      events={[]}
      pollingError={false}
      onViewHistory={() => {}}
    />,
  );
}

/** Minimal TraceEvent factory for the event-driven branches. */
export function ev(
  event_type: string,
  payload?: Record<string, unknown>,
  id = 1,
): TraceEvent {
  return {
    id,
    run_id: 'run-1',
    event_type,
    payload_json: payload ? JSON.stringify(payload) : undefined,
    created_at: 1749340800,
  };
}

export function renderWithEvents(events: TraceEvent[]) {
  return render(
    <FinalReport runId="run-1" events={events} pollingError={false} onViewHistory={() => {}} />,
  );
}
