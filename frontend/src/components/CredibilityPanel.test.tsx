/**
 * CredibilityPanel characterization tests.
 *
 * Captures the current behavior of the repair_delta closed-loop banner:
 *  - renders nothing when runId is null
 *  - stays empty (advisory) when the fetch rejects
 *  - repair_delta sign/% formatting and the 真闭环确认 threshold (>= 0.05)
 *  - secondary metrics (groundedness, admission rate, rounds)
 */

import { render, screen, waitFor, cleanup, act, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import * as client from '../api/client';
import type { CredibilityResponse } from '../api/types';
import { CredibilityPanel } from './CredibilityPanel';

vi.mock('../api/client');

const RESP = (over: Partial<CredibilityResponse> = {}): CredibilityResponse => ({
  avg_groundedness: 0.8,
  claim_admission_rate: 0.5,
  coverage: 0.9,
  repair_delta: 0.12,
  rounds: 2,
  ...over,
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('CredibilityPanel', () => {
  it('renders nothing when runId is null', () => {
    const { container } = render(<CredibilityPanel runId={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when the fetch rejects (advisory, never breaks the page)', async () => {
    vi.mocked(client.getCredibility).mockRejectedValue(new Error('boom'));
    const { container } = render(<CredibilityPanel runId="r1" />);
    // The rejected promise must never populate the panel — it stays empty.
    await waitFor(() => expect(client.getCredibility).toHaveBeenCalledWith('r1'));
    expect(container).toBeEmptyDOMElement();
  });

  it('shows repair_delta as a signed positive % with the 真闭环 (weak→strong) badge when >= 0.05 AND tier upgraded', async () => {
    vi.mocked(client.getCredibility).mockResolvedValue(
      RESP({ repair_delta: 0.12, is_tier_upgrade: true }),
    );
    render(<CredibilityPanel runId="r1" />);
    expect(await screen.findByText(/\+12%/)).toBeInTheDocument();
    expect(screen.getByTestId('loop-confirmed-badge')).toBeInTheDocument();
    expect(screen.getByText(/真闭环确认/)).toBeInTheDocument();
  });

  it('shows the 真闭环 badge at exactly the 0.05 boundary when tier upgraded (>= inclusive)', async () => {
    vi.mocked(client.getCredibility).mockResolvedValue(
      RESP({ repair_delta: 0.05, is_tier_upgrade: true }),
    );
    render(<CredibilityPanel runId="r1" />);
    expect(await screen.findByText(/\+5%/)).toBeInTheDocument();
    expect(screen.getByTestId('loop-confirmed-badge')).toBeInTheDocument();
  });

  it('H1: does NOT claim 真闭环 (weak→strong) when delta >= 0.05 but NO tier upgrade — shows honest gain label', async () => {
    vi.mocked(client.getCredibility).mockResolvedValue(
      RESP({ repair_delta: 0.12, is_tier_upgrade: false }),
    );
    render(<CredibilityPanel runId="r1" />);
    const honest = await screen.findByTestId('honest-gain-badge');
    expect(screen.queryByTestId('loop-confirmed-badge')).not.toBeInTheDocument();
    expect(honest).toHaveTextContent('非弱升强');
    expect(honest).toHaveTextContent('+12%');
  });

  it('J2: shows the 等级跃升 badge (not 真闭环/honest-gain) when tier upgraded but delta < 0.05', async () => {
    // A real version-history tier jump with a small scalar delta (e.g. the
    // default flagship b1771f67: 中→强 at +0.8%) must surface the upgrade fact —
    // while the big-delta 真闭环 claim stays reserved for delta >= 0.05.
    vi.mocked(client.getCredibility).mockResolvedValue(
      RESP({ repair_delta: 0.02, is_tier_upgrade: true }),
    );
    render(<CredibilityPanel runId="r1" />);
    expect(await screen.findByText(/\+2%/)).toBeInTheDocument();
    expect(screen.getByTestId('tier-upgrade-badge')).toHaveTextContent('等级跃升确认');
    expect(screen.queryByTestId('loop-confirmed-badge')).not.toBeInTheDocument();
    expect(screen.queryByTestId('honest-gain-badge')).not.toBeInTheDocument();
  });

  it('J2: no 等级跃升 badge when delta is small and there was NO tier upgrade', async () => {
    vi.mocked(client.getCredibility).mockResolvedValue(
      RESP({ repair_delta: 0.02, is_tier_upgrade: false }),
    );
    render(<CredibilityPanel runId="r1" />);
    expect(await screen.findByText(/\+2%/)).toBeInTheDocument();
    expect(screen.queryByTestId('tier-upgrade-badge')).not.toBeInTheDocument();
    expect(screen.queryByTestId('loop-confirmed-badge')).not.toBeInTheDocument();
    expect(screen.queryByTestId('honest-gain-badge')).not.toBeInTheDocument();
  });

  it('F2: renders the neutral zero-delta state (no arrow, honest copy) when repair_delta === 0', async () => {
    vi.mocked(client.getCredibility).mockResolvedValue(RESP({ repair_delta: 0 }));
    render(<CredibilityPanel runId="r1" />);
    expect(await screen.findByText(/\+0%/)).toBeInTheDocument();
    expect(screen.getByTestId('zero-delta-neutral')).toHaveTextContent('首轮全通过 · 无需修正');
    expect(screen.queryByTestId('loop-confirmed-badge')).not.toBeInTheDocument();
    expect(screen.queryByTestId('honest-gain-badge')).not.toBeInTheDocument();
    // No up-arrow in the neutral state (it reads as a calm fact, not a positive).
    expect(screen.queryByText('↑')).not.toBeInTheDocument();
  });

  it('renders a negative repair_delta (regression) without any positive badge', async () => {
    vi.mocked(client.getCredibility).mockResolvedValue(RESP({ repair_delta: -0.1 }));
    render(<CredibilityPanel runId="r1" />);
    expect(await screen.findByText(/-10%/)).toBeInTheDocument();
    expect(screen.queryByTestId('loop-confirmed-badge')).not.toBeInTheDocument();
    expect(screen.queryByTestId('honest-gain-badge')).not.toBeInTheDocument();
    expect(screen.queryByTestId('zero-delta-neutral')).not.toBeInTheDocument();
  });

  it('renders the secondary metrics (groundedness, admission rate, rounds)', async () => {
    // Distinct values so each asserted % / count is unambiguous.
    vi.mocked(client.getCredibility).mockResolvedValue(
      RESP({ avg_groundedness: 0.81, claim_admission_rate: 0.42, rounds: 3, repair_delta: 0.12 }),
    );
    render(<CredibilityPanel runId="r1" />);
    expect(await screen.findByText('81%')).toBeInTheDocument(); // avg_groundedness
    expect(screen.getByText('42%')).toBeInTheDocument(); // claim_admission_rate
    expect(screen.getByText('3')).toBeInTheDocument(); // rounds
  });

  it('re-fetches on an interval (polls — does not fetch only once)', async () => {
    vi.useFakeTimers();
    try {
      vi.mocked(client.getCredibility).mockResolvedValue(RESP({ repair_delta: 0.12 }));
      render(<CredibilityPanel runId="r1" />);
      await act(async () => { await vi.advanceTimersByTimeAsync(0); }); // immediate first tick
      const first = vi.mocked(client.getCredibility).mock.calls.length;
      await act(async () => { await vi.advanceTimersByTimeAsync(2000); }); // next poll tick
      expect(vi.mocked(client.getCredibility).mock.calls.length).toBeGreaterThan(first);
    } finally {
      vi.useRealTimers();
    }
  });

  it('updates from pre-final zeros to final data when the run completes (no stuck +0%)', async () => {
    vi.useFakeTimers();
    try {
      vi.mocked(client.getCredibility)
        .mockResolvedValueOnce(RESP({ repair_delta: 0, avg_groundedness: 0, rounds: 0 })) // mid-run
        .mockResolvedValue(RESP({ repair_delta: 0.12, avg_groundedness: 0.8, rounds: 2, is_tier_upgrade: true })); // final
      render(<CredibilityPanel runId="r1" />);
      await act(async () => { await vi.advanceTimersByTimeAsync(0); }); // first tick: zeros
      expect(screen.getByText(/\+0%/)).toBeInTheDocument();
      expect(screen.queryByTestId('loop-confirmed-badge')).not.toBeInTheDocument();
      await act(async () => { await vi.advanceTimersByTimeAsync(2000); }); // poll picks up final data
      expect(screen.getByText(/\+12%/)).toBeInTheDocument();
      expect(screen.getByTestId('loop-confirmed-badge')).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('renders the admission waterfall (提议→准入→留存) from the new fields', async () => {
    vi.mocked(client.getCredibility).mockResolvedValue(
      RESP({ proposed_claims: 5, admitted_claims: 2, withheld_claims: 3 }),
    );
    render(<CredibilityPanel runId="r1" />);
    const waterfall = await screen.findByTestId('admission-waterfall');
    expect(within(waterfall).getByText('5')).toBeInTheDocument(); // proposed
    expect(within(waterfall).getByText('2')).toBeInTheDocument(); // admitted
    expect(within(waterfall).getByText('3')).toBeInTheDocument(); // withheld
    expect(within(waterfall).getByText('提议')).toBeInTheDocument();
    expect(within(waterfall).getByText('准入')).toBeInTheDocument();
    expect(within(waterfall).getByText('留存')).toBeInTheDocument();
  });

  it('hides the 留存 segment when nothing was withheld (admitted == proposed)', async () => {
    vi.mocked(client.getCredibility).mockResolvedValue(
      RESP({ proposed_claims: 2, admitted_claims: 2, withheld_claims: 0 }),
    );
    render(<CredibilityPanel runId="r1" />);
    const waterfall = await screen.findByTestId('admission-waterfall');
    expect(within(waterfall).queryByText('留存')).not.toBeInTheDocument();
  });

  it('renders coverage-gap field names when fields are uncovered', async () => {
    vi.mocked(client.getCredibility).mockResolvedValue(
      RESP({ covered_fields: ['pricing_model'], uncovered_fields: ['feature_tree', 'swot'] }),
    );
    render(<CredibilityPanel runId="r1" />);
    const gaps = await screen.findByTestId('coverage-gaps');
    // Field keys render via the Chinese display-label map (display-only; the
    // underlying schema_field keys are unchanged).
    expect(within(gaps).getByText('功能树')).toBeInTheDocument();
    expect(within(gaps).getByText('SWOT 分析')).toBeInTheDocument();
  });

  it('omits waterfall + coverage-gaps for older API responses (backward compatible)', async () => {
    // RESP() supplies none of the new optional fields → both sections absent.
    // tier_upgrade set so the panel shows the loop badge (no honest-gain badge
    // text collision with the ticker) — irrelevant to what this test asserts.
    vi.mocked(client.getCredibility).mockResolvedValue(RESP({ is_tier_upgrade: true }));
    render(<CredibilityPanel runId="r1" />);
    await screen.findByTestId('loop-confirmed-badge'); // panel mounted
    expect(screen.queryByTestId('admission-waterfall')).not.toBeInTheDocument();
    expect(screen.queryByTestId('coverage-gaps')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// M2 (judge P1): zero-admitted honesty — no seal/positive badge may light on a
// run where the QA gate withheld every claim.
// ---------------------------------------------------------------------------

describe('CredibilityPanel zero-admitted honesty (M2)', () => {
  it('suppresses the 真闭环 seal on a 0-admitted run even with tier upgrade + big delta', async () => {
    vi.mocked(client.getCredibility).mockResolvedValue(
      RESP({
        repair_delta: 0.224,
        is_tier_upgrade: true,
        proposed_claims: 5,
        admitted_claims: 0,
        withheld_claims: 5,
      }),
    );
    render(<CredibilityPanel runId="r-zero" />);
    // The honest disclosure replaces every positive badge.
    expect(await screen.findByTestId('zero-admitted-note')).toBeInTheDocument();
    expect(screen.queryByTestId('loop-confirmed-badge')).not.toBeInTheDocument();
    expect(screen.queryByTestId('tier-upgrade-badge')).not.toBeInTheDocument();
    expect(screen.queryByTestId('honest-gain-badge')).not.toBeInTheDocument();
    // The scalar delta itself stays visible (it is a real measured number).
    expect(screen.getByText(/\+22%/)).toBeInTheDocument();
  });

  it('control: the same delta/tier-upgrade WITH admitted claims still earns the seal', async () => {
    vi.mocked(client.getCredibility).mockResolvedValue(
      RESP({
        repair_delta: 0.224,
        is_tier_upgrade: true,
        proposed_claims: 5,
        admitted_claims: 2,
        withheld_claims: 3,
      }),
    );
    render(<CredibilityPanel runId="r-ok" />);
    expect(await screen.findByTestId('loop-confirmed-badge')).toBeInTheDocument();
    expect(screen.queryByTestId('zero-admitted-note')).not.toBeInTheDocument();
  });

  it('0-admitted + zero delta shows the disclosure, NOT the 首轮全通过 neutral badge', async () => {
    vi.mocked(client.getCredibility).mockResolvedValue(
      RESP({ repair_delta: 0, proposed_claims: 0, admitted_claims: 0, withheld_claims: 0 }),
    );
    render(<CredibilityPanel runId="r-empty" />);
    expect(await screen.findByTestId('zero-admitted-note')).toBeInTheDocument();
    // 「首轮全通过 · 无需修正」 would be a lie when nothing was admitted.
    expect(screen.queryByTestId('zero-delta-neutral')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Stop-gate regression: an IN-FLIGHT run reports pre-final zeros — the
// zero-admitted disclosure must NOT fire until the run has settled.
// ---------------------------------------------------------------------------

describe('CredibilityPanel in-flight run honesty (stop-gate)', () => {
  it('shows the in-progress note, NOT the zero-admitted disclosure, while running', async () => {
    vi.mocked(client.getCredibility).mockResolvedValue(
      RESP({
        repair_delta: 0,
        proposed_claims: 0,
        admitted_claims: 0,
        withheld_claims: 0,
        run_status: 'running',
      }),
    );
    render(<CredibilityPanel runId="r-live" />);
    expect(await screen.findByTestId('run-in-progress-note')).toBeInTheDocument();
    expect(screen.queryByTestId('zero-admitted-note')).not.toBeInTheDocument();
    // The 首轮全通过 neutral badge would also be a lie mid-run.
    expect(screen.queryByTestId('zero-delta-neutral')).not.toBeInTheDocument();
  });

  it('a SETTLED 0-admitted run (run_status=partial) still shows the disclosure', async () => {
    vi.mocked(client.getCredibility).mockResolvedValue(
      RESP({
        repair_delta: 0.224,
        is_tier_upgrade: true,
        proposed_claims: 5,
        admitted_claims: 0,
        withheld_claims: 5,
        run_status: 'partial',
      }),
    );
    render(<CredibilityPanel runId="r-settled" />);
    expect(await screen.findByTestId('zero-admitted-note')).toBeInTheDocument();
    expect(screen.queryByTestId('run-in-progress-note')).not.toBeInTheDocument();
    expect(screen.queryByTestId('loop-confirmed-badge')).not.toBeInTheDocument();
  });
});
