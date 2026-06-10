/** RecentRuns — domain badge on each recent-run row (per-run domain visibility). */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import * as client from '../api/client';
import type { RunSummary } from '../api/types';
import { RecentRuns } from './RecentRuns';

vi.mock('../api/client');

function run(over: Partial<RunSummary>): RunSummary {
  return {
    run_id: 'r1', category: 'CRM', competitors: ['Acme'], goal: 'g',
    status: 'complete', created_at: 1, passed_claims: 0, ...over,
  };
}

beforeEach(() => {
  vi.mocked(client.listRuns).mockResolvedValue({
    runs: [run({ run_id: 'r-ai', category: 'AI tools', domain: 'ai_agent' })],
  });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe('RecentRuns domain badge', () => {
  it('shows the run domain when set', async () => {
    render(<RecentRuns onLoadRun={() => {}} />);
    expect(await screen.findByTestId('run-domain-r-ai')).toHaveTextContent('ai_agent');
  });

  it('shows no domain badge when the run has no domain', async () => {
    vi.mocked(client.listRuns).mockResolvedValue({ runs: [run({ run_id: 'r-none', domain: null })] });
    render(<RecentRuns onLoadRun={() => {}} />);
    await screen.findByTestId('recent-run-r-none');
    expect(screen.queryByTestId('run-domain-r-none')).not.toBeInTheDocument();
  });
});

describe('RecentRuns example picker', () => {
  it('RC2: prefers a multi-competitor run over a higher-passed single-competitor run', async () => {
    // H0 gap fix: a single-competitor depth run (4 passed) must NOT win over a
    // genuine 2-competitor run (2 passed) because ComparisonMatrix returns null
    // when competitors.length < 2. The multi-comp run is the money-shot.
    vi.mocked(client.listRuns).mockResolvedValue({
      runs: [
        run({ run_id: 'single-high', competitors: ['Acme'], passed_claims: 4, created_at: 10 }),
        run({ run_id: 'multi-low',   competitors: ['Acme', 'Beta'], passed_claims: 2, created_at: 5 }),
      ],
    });
    const onLoadRun = vi.fn();
    render(<RecentRuns onLoadRun={onLoadRun} />);
    await screen.findByTestId('recent-run-single-high');
    fireEvent.click(screen.getByTestId('view-example-btn'));
    await waitFor(() => expect(onLoadRun).toHaveBeenCalledWith('multi-low'));
  });

  it('RC2: among multiple multi-competitor runs picks the one with highest passed_claims', async () => {
    vi.mocked(client.listRuns).mockResolvedValue({
      runs: [
        run({ run_id: 'multi-weak',   competitors: ['A', 'B'], passed_claims: 2, created_at: 9 }),
        run({ run_id: 'multi-strong', competitors: ['A', 'B'], passed_claims: 5, created_at: 3 }),
        run({ run_id: 'multi-mid',    competitors: ['A', 'B'], passed_claims: 3, created_at: 6 }),
      ],
    });
    const onLoadRun = vi.fn();
    render(<RecentRuns onLoadRun={onLoadRun} />);
    await screen.findByTestId('recent-run-multi-strong');
    fireEvent.click(screen.getByTestId('view-example-btn'));
    await waitFor(() => expect(onLoadRun).toHaveBeenCalledWith('multi-strong'));
  });

  it('RC2: tie-breaks among equal multi-competitor passed_claims by most recent created_at', async () => {
    vi.mocked(client.listRuns).mockResolvedValue({
      runs: [
        run({ run_id: 'multi-old',    competitors: ['A', 'B'], passed_claims: 3, created_at: 5 }),
        run({ run_id: 'multi-newer',  competitors: ['A', 'B'], passed_claims: 3, created_at: 9 }),
      ],
    });
    const onLoadRun = vi.fn();
    render(<RecentRuns onLoadRun={onLoadRun} />);
    await screen.findByTestId('recent-run-multi-old');
    fireEvent.click(screen.getByTestId('view-example-btn'));
    await waitFor(() => expect(onLoadRun).toHaveBeenCalledWith('multi-newer'));
  });

  it('RC2: falls back to highest-passed single-competitor run when no multi-comp run exists', async () => {
    // When only single-competitor runs exist the old behaviour is preserved: pick
    // the highest passed_claims (not just the latest). This covers users who have
    // not yet run a multi-competitor analysis.
    vi.mocked(client.listRuns).mockResolvedValue({
      runs: [
        run({ run_id: 'single-latest', competitors: ['Acme'], passed_claims: 1, created_at: 9 }),
        run({ run_id: 'single-strong', competitors: ['Acme'], passed_claims: 4, created_at: 5 }),
        run({ run_id: 'single-mid',    competitors: ['Acme'], passed_claims: 3, created_at: 3 }),
      ],
    });
    const onLoadRun = vi.fn();
    render(<RecentRuns onLoadRun={onLoadRun} />);
    await screen.findByTestId('recent-run-single-strong');
    fireEvent.click(screen.getByTestId('view-example-btn'));
    await waitFor(() => expect(onLoadRun).toHaveBeenCalledWith('single-strong'));
  });

  it('RC2: a multi-competitor run with 0 passed_claims does NOT beat a single-comp run with passed claims', async () => {
    // Multi-comp is only preferred when it has passed_claims > 0; a 0-claim
    // multi-comp run is useless as a demo (empty matrix) and must not win.
    vi.mocked(client.listRuns).mockResolvedValue({
      runs: [
        run({ run_id: 'multi-zero',  competitors: ['A', 'B'], passed_claims: 0, created_at: 9 }),
        run({ run_id: 'single-good', competitors: ['A'],      passed_claims: 3, created_at: 5 }),
      ],
    });
    const onLoadRun = vi.fn();
    render(<RecentRuns onLoadRun={onLoadRun} />);
    await screen.findByTestId('recent-run-multi-zero');
    fireEvent.click(screen.getByTestId('view-example-btn'));
    await waitFor(() => expect(onLoadRun).toHaveBeenCalledWith('single-good'));
  });

  it('loads the run with the MOST passed claims when all are single-competitor, not merely the latest', async () => {
    // Updated from the original test: the fix preserves the "pick highest
    // passed_claims" rule for the single-competitor fallback tier. All three
    // runs here have competitors.length === 1, so multi-comp priority does not
    // apply; the old pure-passed_claims order still holds.
    vi.mocked(client.listRuns).mockResolvedValue({
      runs: [
        run({ run_id: 'latest-weak', competitors: ['Acme'], created_at: 9, passed_claims: 1 }),
        run({ run_id: 'older-strong', competitors: ['Acme'], created_at: 5, passed_claims: 4 }),
        run({ run_id: 'older-mid',   competitors: ['Acme'], created_at: 3, passed_claims: 3 }),
      ],
    });
    const onLoadRun = vi.fn();
    render(<RecentRuns onLoadRun={onLoadRun} />);
    await screen.findByTestId('recent-run-older-strong');
    fireEvent.click(screen.getByTestId('view-example-btn'));
    await waitFor(() => expect(onLoadRun).toHaveBeenCalledWith('older-strong'));
  });

  it('falls back to the most recent run when none have passed claims', async () => {
    vi.mocked(client.listRuns).mockResolvedValue({
      runs: [
        run({ run_id: 'latest', created_at: 9, passed_claims: 0 }),
        run({ run_id: 'older', created_at: 5, passed_claims: 0 }),
      ],
    });
    const onLoadRun = vi.fn();
    render(<RecentRuns onLoadRun={onLoadRun} />);
    await screen.findByTestId('recent-run-latest');
    fireEvent.click(screen.getByTestId('view-example-btn'));
    await waitFor(() => expect(onLoadRun).toHaveBeenCalledWith('latest'));
  });

  it('GA5: does NOT pick a STALE running run as the hero, even with the most passed claims', async () => {
    const nowS = Date.now() / 1000;
    vi.mocked(client.listRuns).mockResolvedValue({
      runs: [
        // Stale running (started >1h ago) but high passed_claims — must be skipped.
        run({ run_id: 'stale-hung', status: 'running', created_at: nowS - 7200, passed_claims: 9 }),
        // Finished run with fewer claims — the legitimate hero.
        run({ run_id: 'finished', status: 'complete', created_at: nowS - 60, passed_claims: 4 }),
      ],
    });
    const onLoadRun = vi.fn();
    render(<RecentRuns onLoadRun={onLoadRun} />);
    await screen.findByTestId('recent-run-finished');
    fireEvent.click(screen.getByTestId('view-example-btn'));
    await waitFor(() => expect(onLoadRun).toHaveBeenCalledWith('finished'));
  });

  it('GA5 + RC2: stale run excluded even when it would qualify as multi-competitor', async () => {
    const nowS = Date.now() / 1000;
    vi.mocked(client.listRuns).mockResolvedValue({
      runs: [
        // Stale multi-comp with high claims — must be excluded by stale check first.
        run({ run_id: 'stale-multi', status: 'running', competitors: ['A', 'B'], created_at: nowS - 7200, passed_claims: 10 }),
        // Fresh single-comp with modest claims — the safe fallback hero.
        run({ run_id: 'fresh-single', status: 'complete', competitors: ['A'], created_at: nowS - 60, passed_claims: 3 }),
      ],
    });
    const onLoadRun = vi.fn();
    render(<RecentRuns onLoadRun={onLoadRun} />);
    await screen.findByTestId('recent-run-fresh-single');
    fireEvent.click(screen.getByTestId('view-example-btn'));
    await waitFor(() => expect(onLoadRun).toHaveBeenCalledWith('fresh-single'));
  });
});

describe('RecentRuns repair showcase (J2)', () => {
  it('pins the 深度修复案例 button for the run with the largest tier-upgrade repair_delta', async () => {
    vi.mocked(client.listRuns).mockResolvedValue({
      runs: [
        run({ run_id: 'flagship', competitors: ['A', 'B'], passed_claims: 7, status: 'partial' }),
        run({ run_id: 'repair-hero', competitors: ['A'], passed_claims: 4, status: 'partial' }),
      ],
    });
    vi.mocked(client.getCredibility).mockImplementation(async (id: string) => ({
      avg_groundedness: 0.8,
      claim_admission_rate: 0.5,
      coverage: 0.9,
      rounds: 2,
      repair_delta: id === 'repair-hero' ? 0.38 : 0.008,
      is_tier_upgrade: true,
    }));
    const onLoadRun = vi.fn();
    render(<RecentRuns onLoadRun={onLoadRun} />);
    const btn = await screen.findByTestId('showcase-repair-btn');
    expect(btn).toHaveTextContent('+38%');
    fireEvent.click(btn);
    expect(onLoadRun).toHaveBeenCalledWith('repair-hero');
  });

  it('ranks showcase candidates by passed_claims FIRST, then delta (substance over raw delta)', async () => {
    // A thin run with a huge delta (3 passed, +61%) must NOT beat the deeper
    // canonical repair run (4 passed, +38%) — judges land on a real report.
    vi.mocked(client.listRuns).mockResolvedValue({
      runs: [
        run({ run_id: 'flagship', competitors: ['A', 'B'], passed_claims: 7, status: 'partial' }),
        run({ run_id: 'thin-big-delta', passed_claims: 3, status: 'partial' }),
        run({ run_id: 'deep-canonical', passed_claims: 4, status: 'partial' }),
      ],
    });
    vi.mocked(client.getCredibility).mockImplementation(async (id: string) => ({
      avg_groundedness: 0.8,
      claim_admission_rate: 0.5,
      coverage: 0.9,
      rounds: 4,
      repair_delta: id === 'thin-big-delta' ? 0.61 : id === 'deep-canonical' ? 0.38 : 0.008,
      is_tier_upgrade: true,
    }));
    const onLoadRun = vi.fn();
    render(<RecentRuns onLoadRun={onLoadRun} />);
    const btn = await screen.findByTestId('showcase-repair-btn');
    expect(btn).toHaveTextContent('+38%');
    fireEvent.click(btn);
    expect(onLoadRun).toHaveBeenCalledWith('deep-canonical');
  });

  it('shows NO showcase button when no run has a tier-upgrade delta >= 0.05', async () => {
    vi.mocked(client.listRuns).mockResolvedValue({
      runs: [run({ run_id: 'small-delta', status: 'partial', passed_claims: 7 })],
    });
    vi.mocked(client.getCredibility).mockResolvedValue({
      avg_groundedness: 0.8,
      claim_admission_rate: 0.5,
      coverage: 0.9,
      rounds: 2,
      repair_delta: 0.008,
      is_tier_upgrade: true,
    });
    render(<RecentRuns onLoadRun={() => {}} />);
    await screen.findByTestId('recent-run-small-delta');
    expect(screen.queryByTestId('showcase-repair-btn')).not.toBeInTheDocument();
  });

  it('hides the showcase button when the repair hero IS already the example run (no duplicate entry)', async () => {
    // Single multi-competitor run that is both pickExample's choice and the
    // largest tier-upgrade delta — pinning it twice would be noise.
    vi.mocked(client.listRuns).mockResolvedValue({
      runs: [run({ run_id: 'both', competitors: ['A', 'B'], passed_claims: 7, status: 'partial' })],
    });
    vi.mocked(client.getCredibility).mockResolvedValue({
      avg_groundedness: 0.8,
      claim_admission_rate: 0.5,
      coverage: 0.9,
      rounds: 2,
      repair_delta: 0.38,
      is_tier_upgrade: true,
    });
    render(<RecentRuns onLoadRun={() => {}} />);
    await screen.findByTestId('recent-run-both');
    expect(screen.queryByTestId('showcase-repair-btn')).not.toBeInTheDocument();
  });
});

describe('RecentRuns status label (J4)', () => {
  it('renders partial as 部分准入 with an explanatory tooltip, not the raw word', async () => {
    vi.mocked(client.listRuns).mockResolvedValue({
      runs: [run({ run_id: 'p1', status: 'partial' })],
    });
    render(<RecentRuns onLoadRun={() => {}} />);
    const row = await screen.findByTestId('recent-run-p1');
    expect(row).toHaveTextContent('部分准入');
    expect(row).not.toHaveTextContent(/partial/);
  });
});

describe('RecentRuns stale-running label', () => {
  it('GA5: labels a >1h-old running run as 可能已超时 (not just "running")', async () => {
    const nowS = Date.now() / 1000;
    vi.mocked(client.listRuns).mockResolvedValue({
      runs: [run({ run_id: 'hung', status: 'running', created_at: nowS - 7200 })],
    });
    render(<RecentRuns onLoadRun={() => {}} />);
    const tag = await screen.findByTestId('run-stale-hung');
    expect(tag).toHaveTextContent('可能已超时');
  });

  it('GA5: a fresh running run is NOT labeled stale (shows its status)', async () => {
    const nowS = Date.now() / 1000;
    vi.mocked(client.listRuns).mockResolvedValue({
      runs: [run({ run_id: 'live', status: 'running', created_at: nowS - 30 })],
    });
    render(<RecentRuns onLoadRun={() => {}} />);
    await screen.findByTestId('recent-run-live');
    expect(screen.queryByTestId('run-stale-live')).not.toBeInTheDocument();
  });

  it('GA5: a running run with no created_at is NOT labeled stale (cannot judge age)', async () => {
    vi.mocked(client.listRuns).mockResolvedValue({
      runs: [run({ run_id: 'unknown-age', status: 'running', created_at: null })],
    });
    render(<RecentRuns onLoadRun={() => {}} />);
    await screen.findByTestId('recent-run-unknown-age');
    expect(screen.queryByTestId('run-stale-unknown-age')).not.toBeInTheDocument();
  });
});

describe('RecentRuns subtitle (M3)', () => {
  it('disambiguates same-named runs with a competitors + start-time subtitle', async () => {
    vi.mocked(client.listRuns).mockResolvedValue({
      runs: [
        run({
          run_id: 'r-sub',
          category: 'AI 产品竞品分析',
          competitors: ['Notion', 'Linear'],
          created_at: 1781000000,
        }),
      ],
    });
    render(<RecentRuns onLoadRun={() => {}} />);
    const sub = await screen.findByTestId('run-subtitle-r-sub');
    expect(sub.textContent).toContain('Notion vs Linear');
    // Local-time MM-DD HH:mm stamp (timezone-agnostic format assertion).
    expect(sub.textContent).toMatch(/\d{2}-\d{2} \d{2}:\d{2}/);
  });

  it('omits the time segment when created_at is absent', async () => {
    vi.mocked(client.listRuns).mockResolvedValue({
      runs: [run({ run_id: 'r-notime', competitors: ['Acme'], created_at: null })],
    });
    render(<RecentRuns onLoadRun={() => {}} />);
    const sub = await screen.findByTestId('run-subtitle-r-notime');
    expect(sub.textContent).toBe('Acme');
  });
});
