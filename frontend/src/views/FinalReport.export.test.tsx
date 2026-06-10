/**
 * FinalReport integration tests — brief structure / states / run-switch /
 * copy-as-Markdown export.
 *
 * Split out of FinalReport.test.tsx (which keeps the core render / ledger /
 * citation / drawer tests). The API client is fully mocked — no real backend.
 * These tests assert:
 *   - 建议 / SWOT 2x2 / 对比 / 情报缺口 sections render in order;
 *   - BLUF appears before the deterministic claim ledger in DOM order;
 *   - states: 情报缺口 empty (synthesis null), loading skeleton, synthesis-error
 *     fallback to the deterministic ledger, per-section "本节数据不足";
 *   - run-switch clears the prior run's brief/ledger under the new id, and a
 *     stale prior-run fetch resolving after the switch does not overwrite it;
 *   - copy-as-Markdown clipboard feedback (failure notice + 已复制 success).
 *
 * Shared fixtures + render helpers live in FinalReport.testkit.tsx.
 */

import { act, render, screen, waitFor, within, cleanup, fireEvent } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import * as client from '../api/client';
import type { ReportResponse, SynthesisResponse } from '../api/types';
import { FinalReport } from './FinalReport';
import {
  MOCK_CORRECTION_RESPONSE,
  MOCK_HISTORY_SINGLE,
  MOCK_REPORT,
  MOCK_SOURCE,
  MOCK_SYNTHESIS,
  renderReport,
} from './FinalReport.testkit';

vi.mock('../api/client');

beforeEach(() => {
  vi.mocked(client.getReport).mockResolvedValue(MOCK_REPORT);
  vi.mocked(client.getSource).mockResolvedValue(MOCK_SOURCE);
  // Default: single-version history (no version selector shown)
  vi.mocked(client.getClaimHistory).mockResolvedValue(MOCK_HISTORY_SINGLE);
  // Default: correctClaim resolves
  vi.mocked(client.correctClaim).mockResolvedValue(MOCK_CORRECTION_RESPONSE);
  // Default: a full synthesis brief is available.
  vi.mocked(client.getSynthesis).mockResolvedValue(MOCK_SYNTHESIS);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('FinalReport', () => {
  // -------------------------------------------------------------------------
  // NEW: CI brief structure (BLUF first, ledger collapsible)
  // -------------------------------------------------------------------------

  it('renders the brief sections in order: BLUF → 建议 → SWOT → 对比 → 缺口', async () => {
    renderReport();
    await screen.findByTestId('bluf-hero');
    expect(screen.getByTestId('recommendation-band')).toBeInTheDocument();
    expect(screen.getByTestId('swot-grid')).toBeInTheDocument();
    expect(screen.getByTestId('comparison-section')).toBeInTheDocument();
    expect(screen.getByTestId('intelligence-gap-panel')).toBeInTheDocument();
  });

  it('renders the SWOT 2x2 quadrants', async () => {
    renderReport();
    await screen.findByTestId('bluf-hero');
    expect(screen.getByTestId('swot-strengths')).toBeInTheDocument();
    expect(screen.getByTestId('swot-weaknesses')).toBeInTheDocument();
    expect(screen.getByTestId('swot-opportunities')).toBeInTheDocument();
    expect(screen.getByTestId('swot-threats')).toBeInTheDocument();
  });

  it('BLUF appears before the claim ledger in DOM order', async () => {
    const { container } = renderReport();
    const hero = await screen.findByTestId('bluf-hero');
    const ledger = screen.getByTestId('claim-ledger');
    // compareDocumentPosition: FOLLOWING (4) means ledger comes AFTER hero.
    expect(hero.compareDocumentPosition(ledger) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(container).toBeTruthy();
  });

  it('claim ledger is expanded by default and shows the verified-claim count', async () => {
    renderReport();
    const ledger = (await screen.findByTestId('claim-ledger')) as HTMLDetailsElement;
    expect(ledger.tagName.toLowerCase()).toBe('details');
    // Expanded by default (open attribute present).
    expect(ledger.open).toBe(true);
    // Summary shows the heading text and the count (3 claims across pricing + support).
    expect(within(ledger).getByText('全部已验证结论')).toBeInTheDocument();
    expect(within(ledger).getByText('(3)')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // NEW: sentence citation chips
  // -------------------------------------------------------------------------

  it('clicking a BLUF citation chip opens the EvidenceDrawer for that claim id', async () => {
    renderReport();
    const hero = await screen.findByTestId('bluf-hero');
    // BLUF cites c1.
    const chip = within(hero).getByTestId('citation-chip-c1');
    fireEvent.click(chip);

    // The in-place drawer opens (no tab switch) and getSource is fetched for c1.
    await waitFor(() => {
      expect(client.getSource).toHaveBeenCalled();
    });
    expect(await screen.findByLabelText('Evidence drawer')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // NEW: states (empty / loading / synthesis error)
  // -------------------------------------------------------------------------

  it('renders the 情报缺口 empty state when getSynthesis returns null', async () => {
    vi.mocked(client.getSynthesis).mockResolvedValue(null);
    renderReport();
    // Ledger still has claims, but no brief → calm empty state, not a blank.
    expect(await screen.findByTestId('intelligence-gap-empty')).toBeInTheDocument();
    // With verified claims present, the panel must NOT claim "no credible
    // conclusions" (that would contradict the ledger) — it points to the ledger.
    expect(screen.queryByTestId('no-passing-claims')).not.toBeInTheDocument();
    expect(screen.getByTestId('synthesis-absent-note')).toHaveTextContent(
      /综合简报暂未生成，请查阅下方/,
    );
    // The deterministic ledger is still available below.
    expect(screen.getByTestId('claim-ledger')).toBeInTheDocument();
  });

  it('renders the loading skeleton with a caption while synthesis is unresolved', async () => {
    // Never-resolving synthesis fetch → stays in the loading state.
    vi.mocked(client.getSynthesis).mockImplementation(() => new Promise(() => {}));
    renderReport();
    expect(await screen.findByTestId('synthesis-skeleton')).toBeInTheDocument();
    expect(screen.getByTestId('synthesis-skeleton-caption')).toHaveTextContent(
      /正在综合已验证结论生成 BLUF/,
    );
    // Never a blank hero — no BLUF hero shown yet.
    expect(screen.queryByTestId('bluf-hero')).not.toBeInTheDocument();
  });

  it('falls back to the deterministic ledger with a banner on synthesis error', async () => {
    vi.mocked(client.getSynthesis).mockRejectedValue(new Error('parse fail'));
    renderReport();
    expect(await screen.findByTestId('synthesis-error-banner')).toHaveTextContent(
      /综合分析生成失败，已展示原始结论账本/,
    );
    // The deterministic ledger claims are still rendered (never lost).
    expect(screen.getAllByText('Beta lacks a free tier.').length).toBeGreaterThanOrEqual(1);
    // No BLUF hero on the fallback path.
    expect(screen.queryByTestId('bluf-hero')).not.toBeInTheDocument();
  });

  it('keeps the deterministic claim ledger visible while synthesis is loading', async () => {
    // Report has passing claims, but getSynthesis never resolves (slow/hangs).
    vi.mocked(client.getSynthesis).mockImplementation(() => new Promise(() => {}));
    renderReport();
    // Skeleton is shown (still loading)...
    expect(await screen.findByTestId('synthesis-skeleton')).toBeInTheDocument();
    // ...AND the verified claim ledger remains accessible underneath it.
    const ledger = screen.getByTestId('claim-ledger');
    expect(ledger).toBeInTheDocument();
    expect(within(ledger).getByText('全部已验证结论')).toBeInTheDocument();
    expect(within(ledger).getByText('(3)')).toBeInTheDocument();
  });

  it('shows the 情报缺口 gap empty state + ledger when report has zero passing claims', async () => {
    // Report resolves with empty sections (no passing claims) and synthesis null.
    vi.mocked(client.getReport).mockResolvedValue({
      sections: [],
      strength_tally: { strong: 0, moderate: 0, weak: 0 },
    });
    vi.mocked(client.getSynthesis).mockResolvedValue(null);
    renderReport();
    // The 情报缺口 calm empty state renders (not the generic waiting branch).
    expect(await screen.findByTestId('intelligence-gap-empty')).toBeInTheDocument();
    // The ledger appendix still renders (with 0 claims).
    expect(screen.getByTestId('claim-ledger')).toBeInTheDocument();
    // The generic waiting/agent-status branch must NOT be shown.
    expect(screen.queryByTestId('empty-status')).not.toBeInTheDocument();
    expect(screen.queryByTestId('agent-status')).not.toBeInTheDocument();
  });

  it('renders a per-section "本节数据不足" placeholder when a section is empty', async () => {
    vi.mocked(client.getSynthesis).mockResolvedValue({
      ...MOCK_SYNTHESIS,
      comparison: [],
    });
    renderReport();
    await screen.findByTestId('bluf-hero');
    expect(screen.getByTestId('comparison-empty')).toHaveTextContent('本节数据不足');
  });

  // -------------------------------------------------------------------------
  // NEW: run-switch — clear the prior run's brief/ledger under the new id
  // -------------------------------------------------------------------------

  it('clears run A brief + ledger when switching to a different run id B', async () => {
    // B's synthesis BLUF + report differ from A's so we can detect a stale leak.
    const SYNTH_B: SynthesisResponse = {
      ...MOCK_SYNTHESIS,
      bluf: { text: 'Brand-new run B bottom line.', claim_ids: [] },
    };
    const REPORT_B: ReportResponse = {
      sections: [
        {
          schema_field: 'pricing',
          claims: [
            {
              id: 'cB',
              competitor: 'Gamma',
              statement: 'Gamma is run B only.',
              evidence_strength: 'strong',
              value: {},
              evidence_source_ids: [],
              version: 1,
            },
          ],
        },
      ],
      strength_tally: { strong: 1, moderate: 0, weak: 0 },
    };
    vi.useFakeTimers();
    try {
      vi.mocked(client.getSynthesis).mockImplementation(async (id) =>
        id === 'B' ? SYNTH_B : MOCK_SYNTHESIS,
      );
      vi.mocked(client.getReport).mockImplementation(async (id) =>
        id === 'B' ? REPORT_B : MOCK_REPORT,
      );

      const { rerender } = render(
        <FinalReport runId="A" events={[]} pollingError={false} onViewHistory={() => {}} />,
      );
      await act(async () => { await vi.advanceTimersByTimeAsync(0); });
      const hero = screen.getByTestId('bluf-hero');
      expect(within(hero).getByText(/Acme leads on price/i)).toBeInTheDocument();

      // Switch to a DIFFERENT run — reset effect clears A's brief immediately.
      rerender(
        <FinalReport runId="B" events={[]} pollingError={false} onViewHistory={() => {}} />,
      );
      expect(screen.queryByText(/Acme leads on price/i)).not.toBeInTheDocument();

      // B's brief loads on the next poll tick.
      await act(async () => { await vi.advanceTimersByTimeAsync(2100); });
      expect(screen.getByText(/Brand-new run B bottom line/i)).toBeInTheDocument();
      expect(screen.queryByText(/Acme leads on price/i)).not.toBeInTheDocument();
      expect(screen.queryByText('Beta lacks a free tier.')).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('stale: a run A report+synthesis resolving AFTER switching to B does not overwrite B', async () => {
    let resolveReportA: (r: ReportResponse) => void = () => {};
    let resolveSynthA: (s: SynthesisResponse) => void = () => {};
    const SYNTH_B: SynthesisResponse = {
      ...MOCK_SYNTHESIS,
      bluf: { text: 'Run B bottom line.', claim_ids: [] },
    };
    vi.useFakeTimers();
    try {
      vi.mocked(client.getReport).mockImplementation((id) => {
        if (id === 'A') return new Promise<ReportResponse>((res) => { resolveReportA = res; });
        return Promise.resolve(MOCK_REPORT);
      });
      vi.mocked(client.getSynthesis).mockImplementation((id) => {
        if (id === 'A') return new Promise<SynthesisResponse | null>((res) => { resolveSynthA = res; });
        return Promise.resolve(SYNTH_B);
      });

      const { rerender } = render(
        <FinalReport runId="A" events={[]} pollingError={false} onViewHistory={() => {}} />,
      );
      // A is in-flight; switch to B before A resolves.
      rerender(
        <FinalReport runId="B" events={[]} pollingError={false} onViewHistory={() => {}} />,
      );

      // Resolve A's stale fetches — both must be dropped by the ref guard (id !== B).
      await act(async () => {
        resolveReportA(MOCK_REPORT);
        resolveSynthA(MOCK_SYNTHESIS);
        await Promise.resolve();
      });
      expect(screen.queryByText(/Acme leads on price/i)).not.toBeInTheDocument();

      // The next poll tick (now bound to B) loads B's brief.
      await act(async () => { await vi.advanceTimersByTimeAsync(2100); });
      expect(screen.getByText(/Run B bottom line/i)).toBeInTheDocument();
      expect(screen.queryByText(/Acme leads on price/i)).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('FinalReport copy-as-Markdown clipboard feedback', () => {
  const originalClipboard = navigator.clipboard;

  afterEach(() => {
    Object.defineProperty(navigator, 'clipboard', {
      value: originalClipboard,
      configurable: true,
    });
  });

  function mockClipboard(writeText: () => Promise<void>): void {
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    });
  }

  it('shows a visible failure notice when the clipboard write rejects', async () => {
    mockClipboard(() => Promise.reject(new Error('not allowed in insecure context')));
    render(
      <FinalReport runId="run-1" events={[]} pollingError={false} onViewHistory={() => {}} />,
    );

    const btn = await screen.findByTestId('copy-markdown-btn');
    await act(async () => {
      fireEvent.click(btn);
      await Promise.resolve();
    });

    const feedback = await screen.findByTestId('copy-feedback');
    expect(feedback).toHaveTextContent('复制失败');
    // Failure must NOT show the success label.
    expect(btn).not.toHaveTextContent('已复制');
  });

  it('shows 已复制 and no failure notice on a successful copy', async () => {
    mockClipboard(() => Promise.resolve());
    render(
      <FinalReport runId="run-1" events={[]} pollingError={false} onViewHistory={() => {}} />,
    );

    const btn = await screen.findByTestId('copy-markdown-btn');
    await act(async () => {
      fireEvent.click(btn);
      await Promise.resolve();
    });

    expect(btn).toHaveTextContent('已复制');
    expect(screen.queryByTestId('copy-feedback')).not.toBeInTheDocument();
  });
});
