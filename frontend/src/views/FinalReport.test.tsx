/**
 * FinalReport integration tests — core render / ledger / citation / drawer.
 *
 * The API client is fully mocked — no real backend is hit. These tests assert
 * the load-bearing demo behaviors:
 *   - the BLUF brief leads (hero before the ledger), driven by getSynthesis;
 *   - the analyst-hours KPI is NOT in the hero (demoted to KpiBar);
 *   - sentence citation chips open the in-place EvidenceDrawer (no tab switch);
 *   - the deterministic claim ledger is EXPANDED by default (全部已验证结论 (N));
 *   - the StrengthTally counts render and FILTER the claims list,
 *   - claims are grouped by schema_field,
 *   - clicking a claim calls getSource and opens the drawer with the
 *     LIVE/CACHED provenance tag and the highlighted cited chunk.
 *   - CorrectionControls: 采纳 triggers refetch (getReport called again).
 *   - Version selector: shows versions when history returns >1, switching
 *     displays chosen version's statement + produced_by tag.
 *
 * The brief-structure / states / run-switch / copy-as-Markdown groups live in
 * FinalReport.export.test.tsx. Shared fixtures + render helpers live in
 * FinalReport.testkit.tsx.
 */

import { screen, waitFor, within, cleanup, fireEvent } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import * as client from '../api/client';
import type { ReportResponse, SourceProvenance } from '../api/types';
import {
  MOCK_CORRECTION_RESPONSE,
  MOCK_HISTORY_MULTI,
  MOCK_HISTORY_SINGLE,
  MOCK_REPORT,
  MOCK_SOURCE,
  MOCK_SYNTHESIS,
  ev,
  renderReport,
  renderWithEvents,
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
  it('renders the BLUF hero as the lead of the brief', async () => {
    renderReport();
    const hero = await screen.findByTestId('bluf-hero');
    expect(within(hero).getByText(/Acme leads on price/i)).toBeInTheDocument();
  });

  it('does NOT render the analyst-hours KPI in the BLUF hero (demoted to KpiBar)', async () => {
    renderReport();
    const hero = await screen.findByTestId('bluf-hero');
    // The "~N analyst-hours replaced" vanity metric must not lead the brief.
    expect(within(hero).queryByText(/analyst-hours replaced/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/analyst-hours replaced/i)).not.toBeInTheDocument();
  });

  it('renders the StrengthTally counts (in the claim ledger)', async () => {
    renderReport();
    await screen.findByTestId('bluf-hero');
    expect(screen.getByRole('button', { name: /1 strong/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /1 moderate/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /1 weak/i })).toBeInTheDocument();
  });

  it('groups claims by schema_field (in the claim ledger)', async () => {
    renderReport();
    await screen.findByTestId('bluf-hero');
    // Scope to the ledger: the ComparisonMatrix also renders field names as column
    // headers, so query within the claim-ledger to assert the ledger's grouping.
    const ledger = within(screen.getByTestId('claim-ledger'));
    expect(ledger.getByText('pricing')).toBeInTheDocument();
    expect(ledger.getByText('support')).toBeInTheDocument();
    expect(screen.getAllByText('Beta lacks a free tier.').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Acme offers email support only.').length).toBeGreaterThanOrEqual(1);
  });

  it('filters the claims list when a tier chip is clicked', async () => {
    renderReport();
    await screen.findByTestId('bluf-hero');

    // Click the "weak" filter chip → only the weak ClaimRow remains in the list.
    fireEvent.click(screen.getByRole('button', { name: /1 weak/i }));

    // The weak claim's ClaimRow button is still present.
    expect(screen.getByRole('button', { name: /Beta lacks a free tier/i })).toBeInTheDocument();

    // The moderate claim's ClaimRow button is filtered out.
    expect(
      screen.queryByRole('button', { name: /Acme offers email support only/i }),
    ).not.toBeInTheDocument();

    // The strong claim's ClaimRow is also filtered out (NOT as a ClaimRow button).
    expect(
      screen.queryByRole('button', { name: /Acme starter plan costs/i }),
    ).not.toBeInTheDocument();
  });

  it('clicking a claim calls getSource and opens the drawer with provenance + highlight', async () => {
    renderReport();
    const claimRow = await screen.findByRole('button', {
      name: /Beta lacks a free tier/i,
    });

    fireEvent.click(claimRow);

    await waitFor(() => {
      expect(client.getSource).toHaveBeenCalled();
    });

    const drawer = await screen.findByLabelText('Evidence drawer');
    // LIVE/CACHED provenance tag is present.
    expect(within(drawer).getByText('LIVE')).toBeInTheDocument();
    // The URL is shown.
    expect(within(drawer).getByText('https://acme.example/pricing')).toBeInTheDocument();
  });

  it('highlights the cited chunk in the source raw text', async () => {
    // Source whose raw_text contains the clicked claim's statement.
    vi.mocked(client.getSource).mockResolvedValue({
      ...MOCK_SOURCE,
      id: 's3',
      raw_text: 'Beta lacks a free tier according to their site.',
    });
    renderReport();
    const claimRow = await screen.findByRole('button', {
      name: /Beta lacks a free tier/i,
    });
    fireEvent.click(claimRow);

    const mark = await screen.findByTestId('evidence-highlight');
    expect(mark.textContent?.toLowerCase()).toContain('beta lacks a free tier');
  });

  it('source-picker opens the source that actually contains the claim text, not the common-prefix source', async () => {
    // c3 statement: "Acme offers email support only."
    // s4_a: common prefix "Acme offers" but NO full match for the claim
    // s4_b: contains the full statement text — should be chosen
    const sourceA: SourceProvenance = {
      id: 's4_a',
      url: 'https://acme.example/overview',
      source_mode: 'LIVE',
      source_type: 'web',
      fetched_at: 1780524000,
      raw_text: 'Acme offers many services including cloud and analytics.',
      content_hash: 'aaa',
    };
    const sourceB: SourceProvenance = {
      id: 's4_b',
      url: 'https://acme.example/support',
      source_mode: 'LIVE',
      source_type: 'web',
      fetched_at: 1780524000,
      raw_text: 'Acme offers email support only. Phone support is not available.',
      content_hash: 'bbb',
    };

    // The claim "Acme offers email support only." cites [s4_a, s4_b].
    const reportWithTwoSources: ReportResponse = {
      sections: [
        {
          schema_field: 'support',
          claims: [
            {
              id: 'c3',
              competitor: 'Acme',
              statement: 'Acme offers email support only.',
              evidence_strength: 'moderate',
              value: {},
              evidence_source_ids: ['s4_a', 's4_b'],
              version: 1,
            },
          ],
        },
      ],
      strength_tally: { strong: 0, moderate: 1, weak: 0 },
    };

    vi.mocked(client.getReport).mockResolvedValue(reportWithTwoSources);
    vi.mocked(client.getSource).mockImplementation(async (id: string) => {
      if (id === 's4_a') return sourceA;
      if (id === 's4_b') return sourceB;
      throw new Error(`unexpected source id: ${id}`);
    });

    renderReport();
    const claimRow = await screen.findByRole('button', {
      name: /Acme offers email support only/i,
    });
    fireEvent.click(claimRow);

    // The drawer should DISPLAY source B (full match) — asserted via the
    // external link, since M1 also lists every citation (URL appears twice).
    const drawer = await screen.findByLabelText('Evidence drawer');
    await waitFor(() => {
      expect(
        within(drawer).getByRole('link', { name: 'https://acme.example/support' }),
      ).toBeInTheDocument();
    });
    // M1 (judge P1): BOTH cited sources are listed — nothing silently hidden.
    expect(within(drawer).getByTestId('drawer-source-list')).toBeInTheDocument();
    expect(within(drawer).getByTestId('drawer-source-item-s4_a')).toBeInTheDocument();
    expect(within(drawer).getByTestId('drawer-source-item-s4_b')).toBeInTheDocument();
  });

  it('M1: lists all citations real-first, and clicking a simulated entry shows its non-link badge', async () => {
    // Chinese statement → matchScore 0 against BOTH English raw_texts. The old
    // "best match" logic fell back to evidence_source_ids[0] (the simulated
    // survey row, a dead survey: link) and hid the real source entirely.
    const simulated: SourceProvenance = {
      id: 's_sim',
      url: 'survey:SV-2026-NOTION-01/q1',
      source_mode: 'SIMULATED',
      source_type: 'survey',
      fetched_at: null,
      raw_text: 'Respondent: pricing feels fair for small teams.',
      content_hash: 'sim1',
    };
    const real: SourceProvenance = {
      id: 's_real',
      url: 'https://www.notion.com/pricing',
      source_mode: 'CACHED',
      source_type: 'official',
      fetched_at: 1780524000,
      raw_text: 'Notion pricing: Free, Plus, Business, Enterprise tiers.',
      content_hash: 'real1',
    };
    const reportZh: ReportResponse = {
      sections: [
        {
          schema_field: 'pricing_model',
          claims: [
            {
              id: 'c_zh',
              competitor: 'Notion',
              statement: 'Notion 提供免费与多档付费订阅。',
              evidence_strength: 'moderate',
              value: {},
              evidence_source_ids: ['s_sim', 's_real'],
              version: 1,
            },
          ],
        },
      ],
      strength_tally: { strong: 0, moderate: 1, weak: 0 },
    };
    vi.mocked(client.getReport).mockResolvedValue(reportZh);
    vi.mocked(client.getSource).mockImplementation(async (id: string) => {
      if (id === 's_sim') return simulated;
      if (id === 's_real') return real;
      throw new Error(`unexpected source id: ${id}`);
    });

    renderReport();
    fireEvent.click(await screen.findByRole('button', { name: /Notion 提供免费与多档付费订阅/i }));

    const drawer = await screen.findByLabelText('Evidence drawer');
    // Real web source is displayed FIRST (link visible), simulated is listed
    // but not auto-selected despite being evidence_source_ids[0].
    await waitFor(() => {
      expect(
        within(drawer).getByRole('link', { name: 'https://www.notion.com/pricing' }),
      ).toBeInTheDocument();
    });
    const list = within(drawer).getByTestId('drawer-source-list');
    const items = within(list).getAllByRole('button');
    expect(items[0]).toHaveAttribute('data-testid', 'drawer-source-item-s_real');
    expect(items[1]).toHaveAttribute('data-testid', 'drawer-source-item-s_sim');
    expect(within(list).getByText('模拟 · 不参与分档')).toBeInTheDocument();

    // Clicking the simulated citation switches the panel: survey: locator is a
    // NON-LINK badge (no dead <a>), raw text still fully shown.
    fireEvent.click(within(drawer).getByTestId('drawer-source-item-s_sim'));
    await waitFor(() => {
      expect(within(drawer).getByTestId('nonlink-source-badge')).toBeInTheDocument();
    });
    expect(within(drawer).queryByRole('link')).not.toBeInTheDocument();
    expect(
      within(drawer).getByText(/Respondent: pricing feels fair for small teams\./),
    ).toBeInTheDocument();
  });

  it('shows the empty "Waiting for Collector" state when the report is not yet loaded and there are no events', async () => {
    // Report never resolves (genuinely not-yet-loaded) and no events → the
    // bare waiting/agent-status branch is the only thing that should show.
    vi.mocked(client.getReport).mockImplementation(() => new Promise(() => {}));
    renderReport();
    expect(await screen.findByTestId('empty-status')).toHaveTextContent(
      /Waiting for Collector/i,
    );
  });

  // -------------------------------------------------------------------------
  // GA5: terminal-state correctness (revising cleared + run-error banner)
  // -------------------------------------------------------------------------

  it('shows the revising indicator while a claim is mid-revision (revise_start, no terminal event)', async () => {
    renderWithEvents([ev('revise_start', { claim_id: 'c1' }, 1)]);
    await screen.findByTestId('bluf-hero');
    expect(screen.getByTestId('revising-indicator')).toBeInTheDocument();
  });

  it('GA5: clears the revising indicator when a terminal event arrives before revise_done', async () => {
    // revise_start opened c1 but its revise_done never came — a terminal
    // run_complete must clear the stuck "Revising…" state.
    renderWithEvents([
      ev('revise_start', { claim_id: 'c1' }, 1),
      ev('run_complete', {}, 2),
    ]);
    await screen.findByTestId('bluf-hero');
    expect(screen.queryByTestId('revising-indicator')).not.toBeInTheDocument();
  });

  it('GA5: clears revising on a terminal run_error too', async () => {
    renderWithEvents([
      ev('revise_start', { claim_id: 'c1' }, 1),
      ev('run_error', {}, 2),
    ]);
    await screen.findByTestId('bluf-hero');
    expect(screen.queryByTestId('revising-indicator')).not.toBeInTheDocument();
  });

  it('GA5: renders the honest run-error banner on a terminal run_error event', async () => {
    renderWithEvents([ev('run_error', {}, 1)]);
    const banner = await screen.findByTestId('run-error-banner');
    expect(banner).toHaveTextContent('本次运行出错');
  });

  it('GA5: run-error banner does NOT hide partial results (ledger still renders)', async () => {
    renderWithEvents([ev('run_error', {}, 1)]);
    // Banner present AND the partial brief/ledger below still rendered.
    expect(await screen.findByTestId('run-error-banner')).toBeInTheDocument();
    await screen.findByTestId('bluf-hero');
    expect(screen.getByTestId('claim-ledger')).toBeInTheDocument();
  });

  it('GA5: no run-error banner on a clean run (no run_error event)', async () => {
    renderWithEvents([ev('run_complete', {}, 1)]);
    await screen.findByTestId('bluf-hero');
    expect(screen.queryByTestId('run-error-banner')).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // NEW: CorrectionControls + refetch
  // -------------------------------------------------------------------------

  it('after selecting a claim and clicking 采纳, getReport is called again (refetch)', async () => {
    renderReport();

    // Wait for report to load and click a claim row
    const claimRow = await screen.findByRole('button', {
      name: /Beta lacks a free tier/i,
    });
    fireEvent.click(claimRow);

    // CorrectionControls should appear; click 采纳
    const acceptBtn = await screen.findByRole('button', { name: '采纳' });
    const callsBefore = vi.mocked(client.getReport).mock.calls.length;
    fireEvent.click(acceptBtn);

    // After accept, getReport should be called at least one more time (refetch)
    await waitFor(() => {
      expect(vi.mocked(client.getReport).mock.calls.length).toBeGreaterThan(callsBefore);
    });
  });

  // -------------------------------------------------------------------------
  // NEW: Version selector
  // -------------------------------------------------------------------------

  it('shows version selector pills when claim history returns >1 version', async () => {
    vi.mocked(client.getClaimHistory).mockResolvedValue(MOCK_HISTORY_MULTI);

    renderReport();
    const claimRow = await screen.findByRole('button', {
      name: /Acme starter plan costs/i,
    });
    fireEvent.click(claimRow);

    // Version selector should appear
    const versionSelector = await screen.findByTestId('version-selector');
    expect(versionSelector).toBeInTheDocument();
    // Should have v1 and v2 pills
    expect(within(versionSelector).getByRole('button', { name: /v1/i })).toBeInTheDocument();
    expect(within(versionSelector).getByRole('button', { name: /v2/i })).toBeInTheDocument();
  });

  it('switching to v1 shows v1 statement and produced_by tag', async () => {
    vi.mocked(client.getClaimHistory).mockResolvedValue(MOCK_HISTORY_MULTI);

    renderReport();
    const claimRow = await screen.findByRole('button', {
      name: /Acme starter plan costs/i,
    });
    fireEvent.click(claimRow);

    const versionSelector = await screen.findByTestId('version-selector');

    // Default is latest (v2, human:correction)
    const producedByTag = await screen.findByTestId('produced-by-tag');
    expect(producedByTag).toHaveTextContent('human:correction');

    // Switch to v1
    fireEvent.click(within(versionSelector).getByRole('button', { name: /v1/i }));

    // v1's produced_by tag
    await waitFor(() => {
      expect(screen.getByTestId('produced-by-tag')).toHaveTextContent('collector');
    });

    // v1's statement is shown somewhere in the document (version panel or ClaimRow)
    expect(screen.getAllByText('Acme starter plan costs $10/mo.').length).toBeGreaterThanOrEqual(1);
  });

  it('does not show version selector when claim history has only 1 version', async () => {
    // MOCK_HISTORY_SINGLE is the default mock
    renderReport();
    const claimRow = await screen.findByRole('button', {
      name: /Beta lacks a free tier/i,
    });
    fireEvent.click(claimRow);

    // Wait for the drawer to appear
    await screen.findByLabelText('Evidence drawer');

    // No version selector
    expect(screen.queryByTestId('version-selector')).not.toBeInTheDocument();
  });
});
