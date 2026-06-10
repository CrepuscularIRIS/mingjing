/**
 * QAReplay integration test.
 *
 * The API client is mocked — no real backend. Given a weak→strong claim
 * history, it asserts both the WEAK pass-1 card and the STRONG pass-2 card
 * render, and the plain-language evidence-strength rule line is shown.
 */

import { act, render, screen, cleanup } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import * as client from '../api/client';
import type { ClaimHistoryResponse } from '../api/types';
import { QAReplay } from './QAReplay';

vi.mock('../api/client');

const HISTORY: ClaimHistoryResponse = {
  claim_id: 'c1',
  versions: [
    {
      id: 'c1',
      competitor: 'Acme',
      schema_field: 'pricing',
      statement: 'Acme starter plan is around $10/mo (single source).',
      evidence_strength: 'weak',
      status: 'pass',
      value: { amount: 10 },
      evidence_source_ids: ['s1'],
      version: 1,
      produced_by: 'analyst',
    },
    {
      id: 'c1',
      competitor: 'Acme',
      schema_field: 'pricing',
      statement: 'Acme starter plan costs $10/mo (two independent sources).',
      evidence_strength: 'strong',
      status: 'pass',
      value: { amount: 10 },
      evidence_source_ids: ['s1', 's2'],
      version: 2,
      produced_by: 'analyst',
    },
  ],
};

/**
 * Let the upgrade-reveal timer fire INSIDE act. When an upgraded history loads,
 * QAReplay schedules a ~150ms `setRevealed(true)` reveal animation; if the test
 * body returns before it fires, that setState lands outside act → an act()
 * warning. Awaiting past the reveal delay inside act flushes it cleanly.
 */
async function settleReveal(): Promise<void> {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 200));
  });
}

beforeEach(() => {
  vi.mocked(client.getClaimHistory).mockResolvedValue(HISTORY);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('QAReplay', () => {
  it('renders both the WEAK pass-1 and STRONG pass-2 cards and the rule line', async () => {
    render(<QAReplay runId="run-1" claimId="c1" events={[]} live={false} />);

    // Pass-1 weak card.
    expect(
      await screen.findByText(/single source/i),
    ).toBeInTheDocument();
    const pass1Badge = await screen.findByTestId('pass1-badge');
    expect(pass1Badge.textContent).toMatch(/Weak/);

    // Pass-2 strong card.
    expect(screen.getByText(/two independent sources/i)).toBeInTheDocument();
    const pass2Badge = screen.getByTestId('pass2-badge');
    expect(pass2Badge.textContent).toMatch(/Strong/);

    // Plain-language, tier-aware evidence-strength rule line (Simplified Chinese).
    const rule = screen.getByTestId('strength-rule');
    expect(rule.textContent).toMatch(/强\s*=/);
    expect(rule.textContent).toMatch(/权威来源/);
    await settleReveal();
  });

  it('shows the G11 numeric before→after upgrade delta (source count + tier)', async () => {
    render(<QAReplay runId="run-1" claimId="c1" events={[]} live={false} />);
    const delta = await screen.findByTestId('qa-delta');
    // Source count climbs 1 → 2 (pass-1 ['s1'] → pass-2 ['s1','s2']).
    expect(delta.textContent).toMatch(/1\s*来源/);
    expect(delta.textContent).toMatch(/2\s*来源/);
    // Tier flips 弱 → 强.
    expect(delta.textContent).toContain('弱');
    expect(delta.textContent).toContain('强');
    await settleReveal();
  });

  it('celebrates a weak→MODERATE upgrade (canonical money-shot, not only weak→strong)', async () => {
    // The canonical demo claim 4c892067 goes weak→moderate with 1→5 sources;
    // the reveal/delta must fire for moderate too (regression: it only fired on strong).
    vi.mocked(client.getClaimHistory).mockResolvedValue({
      claim_id: 'cm',
      versions: [
        {
          id: 'cm', competitor: 'Notion', schema_field: 'pricing_model',
          statement: 'Notion 定价（单一来源，弱）。', evidence_strength: 'weak',
          status: 'pass', value: {}, evidence_source_ids: ['s1'], version: 1, produced_by: 'analyst',
        },
        {
          id: 'cm', competitor: 'Notion', schema_field: 'pricing_model',
          statement: 'Notion 定价（多来源印证，中）。', evidence_strength: 'moderate',
          status: 'pass', value: {}, evidence_source_ids: ['s1', 's2', 's3', 's4', 's5'], version: 4, produced_by: 'analyst',
        },
      ],
    });
    render(<QAReplay runId="run-m" claimId="cm" events={[]} live={false} />);

    const pass2 = await screen.findByTestId('pass2-badge');
    expect(pass2.textContent).toMatch(/Moderate/);
    const delta = screen.getByTestId('qa-delta');
    expect(delta.textContent).toMatch(/1\s*来源/);
    expect(delta.textContent).toMatch(/5\s*来源/);
    expect(delta.textContent).toContain('弱');
    expect(delta.textContent).toContain('中');
    // Tier-aware rule reflects the MODERATE target, not strong.
    const rule = screen.getByTestId('strength-rule');
    expect(rule.textContent).toMatch(/中\s*=/);
    // +4 sources added shown on the revision step.
    expect(screen.getByTestId('added-evidence').textContent).toMatch(/\+4\s*来源/);
    await settleReveal();
  });

  it('calls getClaimHistory with the run and claim ids', async () => {
    render(<QAReplay runId="run-9" claimId="c1" events={[]} live={false} />);
    await screen.findByText(/single source/i);
    expect(client.getClaimHistory).toHaveBeenCalledWith('run-9', 'c1');
    await settleReveal();
  });

  it('shows the empty prompt when no claim is selected and nothing is replayable', () => {
    render(<QAReplay runId="run-1" claimId={null} events={[]} live={false} />);
    expect(screen.getByText(/还没有可回放的结论/)).toBeInTheDocument();
  });

  it('auto-selects a rejected claim from the trace when none was navigated-to', async () => {
    const events = [
      {
        id: 1,
        run_id: 'run-1',
        agent: 'qa',
        node: 'qa',
        event_type: 'qa_fail',
        payload_json: JSON.stringify({ claim_id: 'c1', code: 'WEAK_EVIDENCE' }),
        created_at: 0,
      },
    ];
    render(<QAReplay runId="run-1" claimId={null} events={events} live={false} />);
    // Auto-selected c1 → history fetched → weak→strong flow renders, no empty prompt.
    expect(await screen.findByText(/single source/i)).toBeInTheDocument();
    expect(client.getClaimHistory).toHaveBeenCalledWith('run-1', 'c1');
    expect(screen.queryByText(/还没有可回放的结论/)).not.toBeInTheDocument();
    await settleReveal();
  });

  it('no longer renders the dead "coming soon" stub panels', async () => {
    render(<QAReplay runId="run-1" claimId="c1" events={[]} live={false} />);
    expect(screen.queryByText(/coming soon/i)).not.toBeInTheDocument();
    // claimId='c1' triggers a real getClaimHistory fetch (default 2-version
    // upgrade mock); await its load + reveal so their setState lands inside act.
    await screen.findByText(/single source/i);
    await settleReveal();
  });

  it('(F3) shows animate-pulse skeleton while claim history is loading', () => {
    // Never-resolving promise keeps the component in the loading state.
    vi.mocked(client.getClaimHistory).mockReturnValue(new Promise(() => {}));
    render(<QAReplay runId="run-1" claimId="c1" events={[]} live={false} />);
    // Skeleton container must be present while loading.
    expect(screen.getByTestId('qa-loading-skeleton')).toBeInTheDocument();
    // The old bare loading text must not appear.
    expect(screen.queryByText(/Loading claim history/i)).not.toBeInTheDocument();
  });

  it('(F4) shows positive first-pass note with ✓ when claim has only one version', async () => {
    vi.mocked(client.getClaimHistory).mockResolvedValue({
      claim_id: 'c1',
      versions: [
        {
          id: 'c1',
          competitor: 'Acme',
          schema_field: 'pricing',
          statement: 'Acme starter plan costs $10/mo (first pass, strong).',
          evidence_strength: 'strong',
          status: 'pass',
          value: {},
          evidence_source_ids: ['s1', 's2'],
          version: 1,
          produced_by: 'analyst',
        },
      ],
    });
    render(<QAReplay runId="run-1" claimId="c1" events={[]} live={false} />);
    const note = await screen.findByTestId('first-pass-note');
    // Must contain ✓ prefix and the Chinese text.
    expect(note.textContent).toContain('✓');
    expect(note.textContent).toContain('一次通过');
    // Must use strong-tier styling (positive, not error/disabled).
    expect(note.className).toMatch(/strong/);
  });
});
