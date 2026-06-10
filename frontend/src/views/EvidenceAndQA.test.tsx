/**
 * EvidenceAndQA integration tests.
 *
 * Covers:
 *   - Left claim list shows all claims.
 *   - Selecting a claim shows its evidence sources (SourceProvenanceTag / URL)
 *     and a 查看原文 button.
 *   - Clicking 查看原文 opens EvidenceDrawer (source content appears).
 *   - getSource is called with the correct id.
 *   - QA pane shows weak→strong flow for a 2-version claim.
 *   - Single-version claim shows the "一次通过" note.
 *   - Claim with no sources shows "暂无引用来源".
 *   - No runId → "Start a run" message; getReport not called.
 */

import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import * as client from '../api/client';
import type { ClaimHistoryResponse, ReportResponse, SourceProvenance } from '../api/types';
import { EvidenceAndQA } from './EvidenceAndQA';

vi.mock('../api/client');

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const MOCK_SOURCE: SourceProvenance = {
  id: 's1',
  url: 'https://example.com/pricing',
  source_mode: 'LIVE',
  source_type: 'web',
  fetched_at: 1780524000,
  raw_text: 'Acme starter plan costs $10/mo. Great value for money.',
  content_hash: 'deadbeef1234',
};

const MOCK_REPORT: ReportResponse = {
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
          evidence_source_ids: ['s1'],
          version: 2,
        },
        {
          id: 'c2',
          competitor: 'Beta',
          statement: 'Beta lacks a free tier.',
          evidence_strength: 'weak',
          value: {},
          evidence_source_ids: [],
          version: 1,
        },
      ],
    },
  ],
  strength_tally: { strong: 1, moderate: 0, weak: 1 },
};

/** c1 — two versions (weak → strong upgrade), v2 with a human correction note */
const MOCK_HISTORY_MULTI: ClaimHistoryResponse = {
  claim_id: 'c1',
  versions: [
    {
      id: 'c1',
      statement: 'Acme starter plan costs $10/mo. (weak draft)',
      evidence_strength: 'weak',
      value: {},
      evidence_source_ids: [],
      version: 1,
      produced_by: 'collector',
    },
    {
      id: 'c1',
      statement: 'Acme starter plan costs $10/mo.',
      evidence_strength: 'strong',
      value: { amount: 10 },
      evidence_source_ids: ['s1'],
      version: 2,
      produced_by: 'human:correction',
      note: '第三方报告交叉核实，人工采信',
    },
  ],
};

/** c2 — single version (never revised) */
const MOCK_HISTORY_SINGLE: ClaimHistoryResponse = {
  claim_id: 'c2',
  versions: [
    {
      id: 'c2',
      statement: 'Beta lacks a free tier.',
      evidence_strength: 'weak',
      value: {},
      evidence_source_ids: [],
      version: 1,
      produced_by: 'collector',
    },
  ],
};

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.mocked(client.getReport).mockResolvedValue(MOCK_REPORT);
  vi.mocked(client.getSource).mockResolvedValue(MOCK_SOURCE);
  vi.mocked(client.getSurveyDesign).mockResolvedValue({});
  vi.mocked(client.getClaimHistory).mockImplementation(async (_runId, claimId) => {
    if (claimId === 'c1') return MOCK_HISTORY_MULTI;
    return MOCK_HISTORY_SINGLE;
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderPage(runId: string | null = 'run-1') {
  return render(<EvidenceAndQA runId={runId} events={[]} />);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('EvidenceAndQA', () => {
  // ---- No runId ----

  it('shows the no-run empty message when no runId and does not call getReport', () => {
    renderPage(null);
    expect(screen.getByText(/发起一次运行后,可在此核验证据与 QA 判决/)).toBeInTheDocument();
    expect(client.getReport).not.toHaveBeenCalled();
  });

  // ---- Claim list ----

  it('renders both claims in the left list', async () => {
    renderPage();
    expect(await screen.findByText('Acme starter plan costs $10/mo.')).toBeInTheDocument();
    expect(screen.getByText('Beta lacks a free tier.')).toBeInTheDocument();
  });

  it('shows the schema_field label in the left column', async () => {
    renderPage();
    await screen.findByText('Acme starter plan costs $10/mo.');
    // The field label appears at least once (column header)
    expect(screen.getAllByText('pricing').length).toBeGreaterThanOrEqual(1);
  });

  // ---- Evidence column for claim with source ----

  it('default-selects the first claim and shows its source', async () => {
    renderPage();
    // Source row should appear without needing a click (default selection)
    const sourceRow = await screen.findByTestId('source-row');
    expect(sourceRow).toBeInTheDocument();
    expect(within(sourceRow).getByText('LIVE')).toBeInTheDocument();
    expect(within(sourceRow).getByText('https://example.com/pricing')).toBeInTheDocument();
  });

  it('selecting a claim with a source shows the SourceProvenanceTag and 查看原文 button', async () => {
    renderPage();
    // Click claim c1 explicitly
    const claimBtn = await screen.findByRole('button', {
      name: /Acme starter plan costs/i,
    });
    fireEvent.click(claimBtn);

    const sourceRow = await screen.findByTestId('source-row');
    expect(within(sourceRow).getByText('LIVE')).toBeInTheDocument();
    expect(within(sourceRow).getByText('https://example.com/pricing')).toBeInTheDocument();

    const jumpBtn = within(sourceRow).getByTestId('jump-to-source-btn');
    expect(jumpBtn).toHaveTextContent('查看原文');
  });

  it('getSource is called with the correct source id', async () => {
    renderPage();
    // Wait for the default-selected claim's sources to be fetched
    await screen.findByTestId('source-row');
    expect(client.getSource).toHaveBeenCalledWith('s1');
  });

  it('clicking 查看原文 opens EvidenceDrawer with the source content', async () => {
    renderPage();
    const jumpBtn = await screen.findByTestId('jump-to-source-btn');
    fireEvent.click(jumpBtn);

    // EvidenceDrawer should now be visible
    const drawer = await screen.findByLabelText('Evidence drawer');
    expect(drawer).toBeInTheDocument();
    expect(within(drawer).getByText('https://example.com/pricing')).toBeInTheDocument();
    expect(within(drawer).getByText('LIVE')).toBeInTheDocument();
  });

  // ---- Claim with no sources ----

  it('claim with no sources shows "暂无引用来源"', async () => {
    renderPage();
    // Click c2 (no sources)
    const c2Btn = await screen.findByRole('button', {
      name: /Beta lacks a free tier/i,
    });
    fireEvent.click(c2Btn);

    const msg = await screen.findByTestId('no-sources-msg');
    expect(msg).toHaveTextContent('暂无引用来源');
  });

  // ---- QA pane: 2-version claim ----

  it('QA pane shows weak→strong flow for 2-version claim (pass1/pass2 badges)', async () => {
    renderPage();
    // c1 is default-selected; wait for history to load
    // QAReplayFlow renders pass1-badge (weak) and pass2-badge (strong)
    const pass1 = await screen.findByTestId('pass1-badge');
    const pass2 = await screen.findByTestId('pass2-badge');
    expect(pass1).toBeInTheDocument();
    expect(pass2).toBeInTheDocument();
  });

  it('QA pane shows both version statements', async () => {
    renderPage();
    // The weak-draft statement appears in the version summary (and again as the
    // Pass-1 card in the money-shot flow) — assert ≥1 occurrence so the now-reliable
    // money-shot rendering (no canvas) doesn't trip findByText's single-match rule.
    const drafts = await screen.findAllByText('Acme starter plan costs $10/mo. (weak draft)');
    expect(drafts.length).toBeGreaterThanOrEqual(1);
  });

  // ---- QA pane: single-version claim ----

  it('single-version claim shows "一次通过" note', async () => {
    renderPage();
    // Click c2 (single version)
    const c2Btn = await screen.findByRole('button', {
      name: /Beta lacks a free tier/i,
    });
    fireEvent.click(c2Btn);

    const note = await screen.findByTestId('single-version-note');
    expect(note).toHaveTextContent('此结论一次通过，无打回记录');
  });

  it('switching from a 2-version claim to a single-version claim hides the flow', async () => {
    renderPage();
    // Wait for c1 (default) to load with its flow
    await screen.findByTestId('pass1-badge');

    // Switch to c2
    const c2Btn = await screen.findByRole('button', {
      name: /Beta lacks a free tier/i,
    });
    fireEvent.click(c2Btn);

    await screen.findByTestId('single-version-note');
    expect(screen.queryByTestId('pass1-badge')).not.toBeInTheDocument();
  });

  // ---- REGRESSION: BUG 1 — poll must not stomp selection ------------------

  it('BUG1-regression: a 2s poll re-resolving getReport with FRESH object refs keeps the selection', async () => {
    vi.useFakeTimers();
    try {
      // Each getReport call returns a brand-new object graph (distinct refs,
      // structurally equal) — exactly what the live 2s poll produces. With the
      // old object-reference selection this orphaned the highlight; the
      // keyed-by-id selection must survive a fresh-object poll.
      vi.mocked(client.getReport).mockImplementation(() =>
        Promise.resolve(JSON.parse(JSON.stringify(MOCK_REPORT)) as ReportResponse),
      );
      renderPage();

      // Flush the mount fetch so the claim list renders.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });

      // Select the second claim.
      fireEvent.click(screen.getByRole('button', { name: /Beta lacks a free tier/i }));
      expect(
        screen.getByRole('button', { name: /Beta lacks a free tier/i }),
      ).toHaveAttribute('aria-pressed', 'true');

      // Advance one full 2s poll cycle: getReport re-resolves with a FRESH
      // object graph, so allClaims is recomputed from new references.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2100);
      });

      // The second claim must STILL be selected (selection is keyed by id, not
      // by the now-orphaned object reference).
      expect(
        screen.getByRole('button', { name: /Beta lacks a free tier/i }),
      ).toHaveAttribute('aria-pressed', 'true');
      // The first claim must NOT be selected.
      expect(
        screen.getByRole('button', { name: /Acme starter plan costs/i }),
      ).toHaveAttribute('aria-pressed', 'false');
    } finally {
      vi.useRealTimers();
    }
  });

  // ---- REGRESSION: BUG 2 — one bad source must not blank the pane ---------

  it('BUG2-regression: a single failing source does not blank the sources pane', async () => {
    // Claim c1 now has two source ids; s2 will reject.
    vi.mocked(client.getReport).mockResolvedValue({
      ...MOCK_REPORT,
      sections: [
        {
          ...MOCK_REPORT.sections[0],
          claims: [
            {
              ...MOCK_REPORT.sections[0].claims[0],
              evidence_source_ids: ['s1', 's2'],
            },
            MOCK_REPORT.sections[0].claims[1],
          ],
        },
      ],
    });

    // s1 resolves; s2 rejects.
    vi.mocked(client.getSource).mockImplementation(async (id) => {
      if (id === 's1') return MOCK_SOURCE;
      throw new Error(`source ${id} not found`);
    });

    renderPage();

    // The first source (s1) should still render even though s2 failed.
    const sourceRow = await screen.findByTestId('source-row');
    expect(sourceRow).toBeInTheDocument();
    expect(within(sourceRow).getByText('https://example.com/pricing')).toBeInTheDocument();

    // The pane must NOT show a full error instead of the resolved source.
    expect(screen.queryByText(/Failed to load/i)).not.toBeInTheDocument();
  });

  // ---- run-switch: clear the prior run's claims under the new id ----------

  it('clears run A claims when switching to a different run id B', async () => {
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
      vi.mocked(client.getReport).mockImplementation(async (id) =>
        id === 'B' ? REPORT_B : MOCK_REPORT,
      );

      const { rerender } = render(<EvidenceAndQA runId="A" events={[]} />);
      await act(async () => { await vi.advanceTimersByTimeAsync(0); });
      expect(screen.getAllByText('Acme starter plan costs $10/mo.').length).toBeGreaterThanOrEqual(1);

      // Switch to a DIFFERENT run — reset effect clears A's claims immediately.
      rerender(<EvidenceAndQA runId="B" events={[]} />);
      expect(screen.queryByText('Acme starter plan costs $10/mo.')).not.toBeInTheDocument();

      // B's claim loads on the next poll tick.
      await act(async () => { await vi.advanceTimersByTimeAsync(2100); });
      expect(screen.getAllByText('Gamma is run B only.').length).toBeGreaterThanOrEqual(1);
      expect(screen.queryByText('Acme starter plan costs $10/mo.')).not.toBeInTheDocument();
      expect(screen.queryByText('Beta lacks a free tier.')).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('stale: a run A report resolving AFTER switching to B does not overwrite B', async () => {
    let resolveA: (r: ReportResponse) => void = () => {};
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
      vi.mocked(client.getReport).mockImplementation((id) => {
        if (id === 'A') return new Promise<ReportResponse>((res) => { resolveA = res; });
        return Promise.resolve(REPORT_B);
      });

      const { rerender } = render(<EvidenceAndQA runId="A" events={[]} />);
      // A in-flight; switch to B before A resolves.
      rerender(<EvidenceAndQA runId="B" events={[]} />);

      // Resolve A's stale fetch — must be dropped by the ref guard (id !== B).
      await act(async () => {
        resolveA(MOCK_REPORT);
        await Promise.resolve();
      });
      expect(screen.queryByText('Acme starter plan costs $10/mo.')).not.toBeInTheDocument();

      // The next poll tick (now bound to B) loads B's claim.
      await act(async () => { await vi.advanceTimersByTimeAsync(2100); });
      expect(screen.getAllByText('Gamma is run B only.').length).toBeGreaterThanOrEqual(1);
      expect(screen.queryByText('Acme starter plan costs $10/mo.')).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});

// ---------------------------------------------------------------------------
// ContradictionCard surfacing (source-vs-source conflict)
// ---------------------------------------------------------------------------

describe('EvidenceAndQA — ContradictionCard', () => {
  const REPORT_WITH_CONFLICT: ReportResponse = {
    sections: [
      {
        schema_field: 'pricing',
        claims: [
          {
            id: 'c1',
            competitor: 'Acme',
            statement: 'Acme starter plan costs $10/mo.',
            evidence_strength: 'weak',
            value: { amount: 10 },
            evidence_source_ids: ['s1'],
            version: 1,
            contradiction: {
              source_a: { label: 'acme.com', url: 'https://acme.com/p', grade: 'B2' },
              source_b: { label: 'trustpilot.com', url: 'https://trustpilot.com/p' },
              from: 'strong',
              to: 'weak',
            },
          },
        ],
      },
    ],
    strength_tally: { strong: 0, moderate: 0, weak: 1 },
  };

  it('renders the ContradictionCard when the selected claim has a conflict', async () => {
    vi.mocked(client.getReport).mockResolvedValue(REPORT_WITH_CONFLICT);
    renderPage();
    const card = await screen.findByTestId('contradiction-card');
    expect(card).toBeInTheDocument();
    expect(within(card).getByText('acme.com')).toBeInTheDocument();
    expect(within(card).getByText('trustpilot.com')).toBeInTheDocument();
  });

  it('renders no ContradictionCard when the claim has no conflict', async () => {
    // default MOCK_REPORT (no contradiction field)
    renderPage();
    await screen.findByText('Acme starter plan costs $10/mo.');
    expect(screen.queryByTestId('contradiction-card')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// GA8: version note display
// ---------------------------------------------------------------------------

describe('EvidenceAndQA — version note display (GA8)', () => {
  it('displays the note from a correction version in the history panel', async () => {
    renderPage();
    // c1 is default-selected; MOCK_HISTORY_MULTI v2 has a correction note
    const noteEl = await screen.findByTestId('version-note');
    expect(noteEl).toBeInTheDocument();
    expect(noteEl.textContent).toContain('修正说明：');
    expect(noteEl.textContent).toContain('第三方报告交叉核实，人工采信');
  });

  it('does not render version-note for versions without a note', async () => {
    // Use a history where neither version has a note
    vi.mocked(client.getClaimHistory).mockImplementation(async () => ({
      claim_id: 'c1',
      versions: [
        {
          id: 'c1',
          statement: 'No-note weak draft.',
          evidence_strength: 'weak' as const,
          value: {},
          evidence_source_ids: [],
          version: 1,
          produced_by: 'collector',
        },
        {
          id: 'c1',
          statement: 'No-note strong final.',
          evidence_strength: 'strong' as const,
          value: { amount: 5 },
          evidence_source_ids: ['s1'],
          version: 2,
          produced_by: 'analyst',
        },
      ],
    }));

    renderPage();
    await screen.findByTestId('pass1-badge');
    expect(screen.queryByTestId('version-note')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Stop-gate regression: survey:/interview: locators in the SOURCE-ROW list must
// render a non-link badge, never a dead <a> (the EvidenceDrawer guard alone
// was not enough — this view is the primary evidence-verification surface).
// ---------------------------------------------------------------------------

describe('EvidenceAndQA non-web source locators', () => {
  it('renders a survey: source row as a non-link badge with NO anchor', async () => {
    vi.mocked(client.getReport).mockResolvedValue({
      sections: [
        {
          schema_field: 'user_sentiment',
          claims: [
            {
              id: 'c-sim',
              competitor: 'Acme',
              statement: '用户整体满意度较高。',
              evidence_strength: 'moderate',
              value: {},
              evidence_source_ids: ['s-sim'],
              version: 1,
            },
          ],
        },
      ],
      strength_tally: { strong: 0, moderate: 1, weak: 0 },
    });
    vi.mocked(client.getSource).mockResolvedValue({
      id: 's-sim',
      url: 'survey:SV-1/user_sentiment',
      source_mode: 'SIMULATED',
      source_type: 'survey',
      fetched_at: null,
      raw_text: 'Respondent: overall satisfied.',
      content_hash: 'simhash1',
    });

    renderPage();
    const row = await screen.findByTestId('source-row');
    expect(within(row).getByTestId('nonlink-source-badge')).toBeInTheDocument();
    expect(within(row).getByText(/问卷调研来源 · 站内定位符/)).toBeInTheDocument();
    expect(within(row).queryByRole('link')).not.toBeInTheDocument();
  });
});
