/**
 * KpiBar unit tests.
 *
 * Covers:
 *  - Placeholder "—" values render when runId is null.
 *  - Metric tiles render formatted values after fetch resolves.
 *  - Accuracy caveat is surfaced on the strong_rate tile's title attribute.
 */

import { act, render, screen, waitFor, cleanup } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import * as client from '../api/client';
import type { CredibilityResponse, MetricsResponse, ReportResponse } from '../api/types';
import { KpiBar } from './KpiBar';

vi.mock('../api/client');

// ---------------------------------------------------------------------------
// Fixture
// ---------------------------------------------------------------------------

const MOCK_METRICS: MetricsResponse = {
  coverage: 0.9,
  citation_rate: 0.75,
  strong_rate: 0.6,
  human_correction_rate: 0.05,
  efficiency: {
    elapsed_s: 42,
    source_count: 10,
    llm_calls: 8,
    total_tokens: 1200,
    human_baseline_hours_low: 16,
    human_baseline_hours_high: 40,
    // round(16*3600/42)=1371, round(40*3600/42)=3429
    speedup_low: 1371,
    speedup_high: 3429,
  },
  accuracy_caveat: 'Strong evidence is a proxy, not ground truth.',
};

// Moderate-heavy verified run (mirrors the canonical demo): strong_rate would be
// 0%, but the composition tile must show the honest 强/中/弱 breakdown instead.
const MOCK_REPORT = {
  sections: [],
  strength_tally: { strong: 0, moderate: 4, weak: 0 },
} as unknown as ReportResponse;

const MOCK_CREDIBILITY: CredibilityResponse = {
  avg_groundedness: 0.8,
  claim_admission_rate: 0.8,
  coverage: 0.8,
  repair_delta: 0.43,
  rounds: 4,
};

beforeEach(() => {
  vi.mocked(client.getMetrics).mockResolvedValue(MOCK_METRICS);
  vi.mocked(client.getReport).mockResolvedValue(MOCK_REPORT);
  vi.mocked(client.getCredibility).mockResolvedValue(MOCK_CREDIBILITY);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('KpiBar', () => {
  it('renders placeholder dashes when runId is null', () => {
    render(<KpiBar runId={null} />);
    // All 5 tiles should show "—"
    const dashes = screen.getAllByText('—');
    expect(dashes.length).toBeGreaterThanOrEqual(4);
  });

  it('renders coverage as percentage after fetch', async () => {
    render(<KpiBar runId="run-1" />);
    await waitFor(() => {
      expect(screen.getByText('90%')).toBeInTheDocument();
    });
  });

  it('renders citation_rate as percentage', async () => {
    render(<KpiBar runId="run-1" />);
    await waitFor(() => {
      expect(screen.getByText('75%')).toBeInTheDocument();
    });
  });

  it('renders human_correction_rate as percentage', async () => {
    render(<KpiBar runId="run-1" />);
    await waitFor(() => {
      expect(screen.getByText('5%')).toBeInTheDocument();
    });
  });

  it('renders elapsed_s formatted with "s" suffix', async () => {
    render(<KpiBar runId="run-1" />);
    await waitFor(() => {
      expect(screen.getByText('42s')).toBeInTheDocument();
    });
  });

  it('renders repair_delta as +43% in the 修正增益 tile', async () => {
    render(<KpiBar runId="run-1" />);
    await waitFor(() => {
      expect(screen.getByText('修正增益')).toBeInTheDocument();
      expect(screen.getByText('+43%')).toBeInTheDocument();
    });
  });

  it('surfaces accuracy_caveat in the 证据强度构成 tile title', async () => {
    render(<KpiBar runId="run-1" />);
    await waitFor(() => {
      // The caveat stays reachable on hover, now embedded in the richer composition
      // tile title (which also carries the demoted strong_rate %), so match on substring.
      const tile = screen.getByTitle(/Strong evidence is a proxy, not ground truth\./);
      expect(tile).toBeInTheDocument();
      // The tile headlines the 强/中/弱 composition label, never a bare strong_rate %.
      expect(tile.textContent).toContain('证据强度构成');
    });
  });

  it('headlines the 强/中/弱 composition from strength_tally, never a bare strong_rate %', async () => {
    render(<KpiBar runId="run-1" />);
    // The composition tile reads from report.strength_tally (强0·中4·弱0 here)…
    const tile = await screen.findByTitle(/Strong evidence is a proxy, not ground truth\./);
    await waitFor(() => {
      expect(tile.textContent).toContain('强0·中4·弱0');
    });
    // …and the moderate-heavy run is NOT headlined as a bare "0%" anywhere in the bar.
    expect(screen.queryByText('0%')).not.toBeInTheDocument();
    // Verified-claims count still sums the tally honestly.
    expect(screen.getByText('4 条')).toBeInTheDocument();
  });

  // ---- honest measured-vs-estimate footer (axis-3) -----------------------

  it('renders the computed speedup footer from real elapsed + derived ratio', async () => {
    render(<KpiBar runId="run-1" />);
    await waitFor(() => {
      // Real elapsed (42s) + human estimate range + derived speedup range.
      expect(screen.getByText(/本次 42s/)).toBeInTheDocument();
      expect(screen.getByText(/人工约 16–40h（行业估算）/)).toBeInTheDocument();
      expect(screen.getByText(/约 1,371–3,429× 提速/)).toBeInTheDocument();
    });
  });

  it('labels the human baseline as an estimate (行业估算) in the footer tooltip', async () => {
    render(<KpiBar runId="run-1" />);
    await waitFor(() => {
      // Machine time framed as measured (实测), human time framed as estimate.
      const footer = screen.getByTitle(/实测墙钟/);
      expect(footer).toBeInTheDocument();
      expect(footer.getAttribute('title')).toMatch(/行业估算/);
    });
  });

  it('formats elapsed >= 60s as 分秒 in the footer', async () => {
    vi.mocked(client.getMetrics).mockResolvedValue({
      ...MOCK_METRICS,
      efficiency: {
        ...MOCK_METRICS.efficiency,
        elapsed_s: 95,
        speedup_low: 606,
        speedup_high: 1516,
      },
    });
    render(<KpiBar runId="run-1" />);
    await waitFor(() => {
      // 95s → 1分35秒
      expect(screen.getByText(/本次 1分35秒/)).toBeInTheDocument();
    });
  });

  it('falls back to the static caption when speedup fields are absent (older API)', async () => {
    vi.mocked(client.getMetrics).mockResolvedValue({
      ...MOCK_METRICS,
      efficiency: {
        elapsed_s: 42,
        source_count: 10,
        llm_calls: 8,
        total_tokens: 1200,
        // No human_baseline_* / speedup_* fields.
      },
    });
    render(<KpiBar runId="run-1" />);
    await waitFor(() => {
      expect(screen.getByText(/机器耗时 vs 人工基线 ≈ 16–40 小时（估算）/)).toBeInTheDocument();
    });
    expect(screen.queryByText(/× 提速/)).not.toBeInTheDocument();
  });

  it('falls back to the static caption when speedup is null but baseline is present (floor-suppressed sub-1s run)', async () => {
    // Mirrors backend test_speedup_suppressed_below_credible_floor: the API can
    // return human_baseline_hours_* WITH speedup_* === null for a sub-1s run.
    vi.mocked(client.getMetrics).mockResolvedValue({
      ...MOCK_METRICS,
      efficiency: {
        ...MOCK_METRICS.efficiency,
        elapsed_s: 0.4,
        human_baseline_hours_low: 16,
        human_baseline_hours_high: 40,
        speedup_low: null,
        speedup_high: null,
      },
    });
    render(<KpiBar runId="run-1" />);
    await waitFor(() => {
      expect(screen.getByText(/机器耗时 vs 人工基线 ≈ 16–40 小时（估算）/)).toBeInTheDocument();
    });
    expect(screen.queryByText(/× 提速/)).not.toBeInTheDocument();
  });

  it('calls getMetrics with the provided runId', async () => {
    render(<KpiBar runId="run-42" />);
    await waitFor(() => {
      expect(vi.mocked(client.getMetrics)).toHaveBeenCalledWith('run-42');
    });
  });

  it('does not call getMetrics when runId is null', () => {
    render(<KpiBar runId={null} />);
    expect(vi.mocked(client.getMetrics)).not.toHaveBeenCalled();
  });

  // ---- run-switch: clear the prior run's KPIs under the new id ------------

  it('clears run A KPIs when switching to a different run id B', async () => {
    vi.useFakeTimers();
    try {
      const METRICS_B: MetricsResponse = { ...MOCK_METRICS, coverage: 0.5 };
      vi.mocked(client.getMetrics).mockImplementation(async (id) =>
        id === 'B' ? METRICS_B : MOCK_METRICS,
      );

      const { rerender } = render(<KpiBar runId="A" />);
      await act(async () => { await vi.advanceTimersByTimeAsync(0); });
      expect(screen.getByText('90%')).toBeInTheDocument();

      // Switch to a DIFFERENT non-null run.
      rerender(<KpiBar runId="B" />);

      // A's 90% must be cleared immediately by the reset effect...
      expect(screen.queryByText('90%')).not.toBeInTheDocument();

      // ...and replaced by B's 50% on the next poll tick.
      await act(async () => { await vi.advanceTimersByTimeAsync(2100); });
      expect(screen.getByText('50%')).toBeInTheDocument();
      expect(screen.queryByText('90%')).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('stale: a run A fetch resolving AFTER switching to B does not overwrite B', async () => {
    vi.useFakeTimers();
    try {
      let resolveA: (m: MetricsResponse) => void = () => {};
      const METRICS_B: MetricsResponse = { ...MOCK_METRICS, coverage: 0.5 };
      vi.mocked(client.getMetrics).mockImplementation((id) => {
        if (id === 'A') return new Promise<MetricsResponse>((res) => { resolveA = res; });
        return Promise.resolve(METRICS_B);
      });

      const { rerender } = render(<KpiBar runId="A" />);
      // A's fetch is in-flight (unresolved). Switch to B before it resolves.
      rerender(<KpiBar runId="B" />);

      // Resolve A's stale fetch — it must be dropped by the ref guard (id !== B).
      await act(async () => {
        resolveA(MOCK_METRICS); // coverage 90%
        await Promise.resolve();
      });
      expect(screen.queryByText('90%')).not.toBeInTheDocument();

      // The next poll tick (now bound to B) fetches B's metrics.
      await act(async () => { await vi.advanceTimersByTimeAsync(2100); });
      expect(screen.getByText('50%')).toBeInTheDocument();
      expect(screen.queryByText('90%')).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});

// ---------------------------------------------------------------------------
// M2 (judge P1): a 0-admitted run must not display a "N× 提速" comparison.
// ---------------------------------------------------------------------------

describe('KpiBar zero-admitted speedup suppression (M2)', () => {
  it('replaces the speedup footer with an explicit 0-准入 disclosure', async () => {
    vi.mocked(client.getReport).mockResolvedValue({
      sections: [],
      strength_tally: { strong: 0, moderate: 0, weak: 0 },
    } as unknown as ReportResponse);
    render(<KpiBar runId="run-zero" />);
    await waitFor(() => {
      expect(screen.getByTestId('speedup-suppressed')).toBeInTheDocument();
    });
    expect(screen.getByText(/0 条结论准入 · 不作人工基线对比/)).toBeInTheDocument();
    expect(screen.queryByText(/× 提速/)).not.toBeInTheDocument();
  });

  it('keeps the speedup footer while the report is still loading (no false suppression)', async () => {
    vi.mocked(client.getReport).mockImplementation(() => new Promise(() => {}));
    render(<KpiBar runId="run-loading" />);
    await waitFor(() => {
      expect(screen.getByText(/约 1,371–3,429× 提速/)).toBeInTheDocument();
    });
    expect(screen.queryByTestId('speedup-suppressed')).not.toBeInTheDocument();
  });
});

describe('KpiBar in-flight run honesty (stop-gate)', () => {
  it('does NOT suppress the footer while the run is still running (pre-final zeros)', async () => {
    vi.mocked(client.getReport).mockResolvedValue({
      sections: [],
      strength_tally: { strong: 0, moderate: 0, weak: 0 },
    } as unknown as ReportResponse);
    vi.mocked(client.getCredibility).mockResolvedValue({
      ...MOCK_CREDIBILITY,
      run_status: 'running',
    });
    render(<KpiBar runId="run-live" />);
    await waitFor(() => {
      expect(screen.getByText(/约 1,371–3,429× 提速/)).toBeInTheDocument();
    });
    expect(screen.queryByTestId('speedup-suppressed')).not.toBeInTheDocument();
  });
});
