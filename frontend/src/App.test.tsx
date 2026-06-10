/**
 * App shell integration tests.
 *
 * Covers:
 *  - All 6 nav items are present in the left nav.
 *  - Clicking a nav item switches the active view.
 *  - 分析报告 is the default active tab.
 *  - Clicking 执行轨迹 shows the ExecutionTrace empty-state; 可观测 shows Observability.
 *  - Clicking Schema 矩阵 shows the SchemaMatrix no-run state (not the old placeholder).
 *  - Clicking 证据&溯源 shows the EvidenceAndQA no-run message.
 */

import { act, render, screen, fireEvent, cleanup } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import * as client from './api/client';
import type {
  DomainSchemaResponse,
  MetricsResponse,
  RunListResponse,
  SchemasListResponse,
  TraceResponse,
} from './api/types';
import App from './App';

vi.mock('./api/client');

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

/**
 * Drain all pending promise-driven state updates (the mount-time getSchemas +
 * RecentRuns listRuns fetches and any follow-on setState) INSIDE act, so their
 * resolved-promise setState never lands outside act → no act() warning. A
 * macrotask boundary flushes every queued microtask layer; the resolved mocks
 * settle in one pass. Used by the synchronous-render tests that assert against
 * the initial render and would otherwise leave a fetch in flight at teardown.
 */
async function settle(): Promise<void> {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

const EMPTY_TRACE: TraceResponse = { events: [], max_seq: 0 };

const EMPTY_METRICS: MetricsResponse = {
  coverage: 0,
  citation_rate: 0,
  strong_rate: 0,
  human_correction_rate: 0,
  efficiency: { elapsed_s: 0, source_count: 0, llm_calls: 0, total_tokens: 0 },
  accuracy_caveat: '',
};

const MOCK_SCHEMAS: SchemasListResponse = {
  domains: ['default'],
  active: 'default',
};

const MULTI_DOMAIN_SCHEMAS: SchemasListResponse = {
  domains: ['default', 'ai_agent', 'hr'],
  active: 'default',
};

const MOCK_DOMAIN: DomainSchemaResponse = {
  domain: 'default',
  fields: { pricing_model: { required: [], sub_fields: [] } },
};

const EMPTY_RUN_LIST: RunListResponse = { runs: [] };

beforeEach(() => {
  // Live-run submit shows a window.confirm guard; default it to "OK" so the
  // existing create-run tests proceed. Individual tests override as needed.
  vi.spyOn(window, 'confirm').mockReturnValue(true);
  vi.mocked(client.getTrace).mockResolvedValue(EMPTY_TRACE);
  vi.mocked(client.getMetrics).mockResolvedValue(EMPTY_METRICS);
  vi.mocked(client.getLlmCalls).mockResolvedValue({ calls: [] });
  vi.mocked(client.getReport).mockResolvedValue({ sections: [], strength_tally: { strong: 0, moderate: 0, weak: 0 } });
  vi.mocked(client.getSchemas).mockResolvedValue(MOCK_SCHEMAS);
  vi.mocked(client.getSchemaDomain).mockResolvedValue(MOCK_DOMAIN);
  vi.mocked(client.listRuns).mockResolvedValue(EMPTY_RUN_LIST);
  vi.mocked(client.getSynthesis).mockResolvedValue(null);
  vi.mocked(client.getSurveyDesign).mockResolvedValue({});
  vi.mocked(client.getCredibility).mockResolvedValue({
    avg_groundedness: 0,
    claim_admission_rate: 0,
    coverage: 0,
    repair_delta: 0,
    rounds: 0,
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('App nav', () => {
  it('renders all 6 nav items', async () => {
    render(<App />);
    expect(screen.getByTestId('nav-report')).toBeInTheDocument();
    expect(screen.getByTestId('nav-schema')).toBeInTheDocument();
    expect(screen.getByTestId('nav-evidence')).toBeInTheDocument();
    expect(screen.getByTestId('nav-qa-replay')).toBeInTheDocument();
    expect(screen.getByTestId('nav-trace')).toBeInTheDocument();
    expect(screen.getByTestId('nav-observability')).toBeInTheDocument();
    // Flush the mount-time fetches (getSchemas + RecentRuns listRuns) inside act
    // so their resolved-promise setState lands within act — no act() warning.
    await settle();
  });

  it('shows Chinese labels for all nav items', async () => {
    render(<App />);
    expect(screen.getByText('分析报告')).toBeInTheDocument();
    expect(screen.getByText('Schema 矩阵')).toBeInTheDocument();
    expect(screen.getByText('证据&溯源')).toBeInTheDocument();
    expect(screen.getByText('QA 回放')).toBeInTheDocument();
    expect(screen.getByText('执行轨迹')).toBeInTheDocument();
    expect(screen.getByText('可观测')).toBeInTheDocument();
    await settle();
  });

  it('clicking 执行轨迹 shows the ExecutionTrace empty-state', async () => {
    render(<App />);
    fireEvent.click(screen.getByTestId('nav-trace'));
    // ExecutionTrace is lazy-loaded — use findBy to wait for Suspense resolution.
    expect(await screen.findByText(/see the execution trace/i)).toBeInTheDocument();
    await settle();
  });

  it('clicking 可观测 shows the Observability empty-state', async () => {
    render(<App />);
    fireEvent.click(screen.getByTestId('nav-observability'));
    // Observability is lazy-loaded — use findBy to wait for Suspense resolution.
    expect(await screen.findByText(/observe its internals/i)).toBeInTheDocument();
    await settle();
  });

  it('clicking Schema 矩阵 shows the SchemaMatrix no-run state', async () => {
    render(<App />);
    fireEvent.click(screen.getByTestId('nav-schema'));
    // SchemaMatrix renders a "Start a run" message when no runId is set.
    // findBy flushes the component's getSchemas() promise (avoids act warnings).
    expect(await screen.findByTestId('no-run-message')).toBeInTheDocument();
    await settle();
  });

  it('clicking 证据&溯源 shows the EvidenceAndQA no-run message', async () => {
    render(<App />);
    fireEvent.click(screen.getByTestId('nav-evidence'));
    expect(screen.getByText(/发起一次运行后,可在此核验证据与 QA 判决/)).toBeInTheDocument();
    await settle();
  });

  it('default active tab is 分析报告 (FinalReport content visible)', async () => {
    render(<App />);
    // FinalReport renders its empty-state when no run is active;
    // the nav button for report should be highlighted (has the brand-accent class)
    const reportNav = screen.getByTestId('nav-report');
    expect(reportNav.className).toContain('mirror');
    await settle();
  });

  it('switching tabs changes the active nav highlight', async () => {
    render(<App />);
    fireEvent.click(screen.getByTestId('nav-trace'));
    const traceNav = screen.getByTestId('nav-trace');
    expect(traceNav.className).toContain('mirror');
    // report nav should no longer be highlighted
    const reportNav = screen.getByTestId('nav-report');
    expect(reportNav.className).not.toContain('mirror');
    await settle();
  });
});

describe('tab description bar', () => {
  it('renders the active tab description and changes on tab switch', async () => {
    render(<App />);
    const bar = screen.getByTestId('tab-description');
    // Default tab is 分析报告.
    expect(bar.textContent).toContain('结论先行(BLUF)');
    fireEvent.click(screen.getByTestId('nav-trace'));
    expect(screen.getByTestId('tab-description').textContent).toContain(
      '多 Agent 协作执行 DAG',
    );
    await settle();
  });
});

describe('查看示例分析 + 近期运行', () => {
  const RUNS: RunListResponse = {
    runs: [
      {
        run_id: 'run-newest-no-claims',
        category: 'Cloud',
        competitors: ['AWS'],
        goal: 'g',
        status: 'running',
        created_at: 3,
        passed_claims: 0,
      },
      {
        run_id: 'run-good-example',
        category: 'CRM',
        competitors: ['Acme'],
        goal: 'g',
        status: 'complete',
        created_at: 2,
        passed_claims: 5,
      },
    ],
  };

  it('clicking 查看示例分析 calls listRuns and loads the best run', async () => {
    vi.mocked(client.listRuns).mockResolvedValue(RUNS);
    render(<App />);
    fireEvent.click(screen.getByTestId('view-example-btn'));
    // Picks the most-recent run with passed_claims > 0.
    expect(await screen.findByText(/run-good-example/)).toBeInTheDocument();
    expect(client.listRuns).toHaveBeenCalled();
    await settle();
  });

  it('clicking a 近期运行 row loads that run id', async () => {
    vi.mocked(client.listRuns).mockResolvedValue(RUNS);
    render(<App />);
    const row = await screen.findByTestId('recent-run-run-newest-no-claims');
    fireEvent.click(row);
    expect(await screen.findByText(/run-newest-no-claims/)).toBeInTheDocument();
    await settle();
  });
});

describe('domain dropdown on the run form', () => {
  it('renders a domain select with an option per domain, defaulting to active', async () => {
    vi.mocked(client.getSchemas).mockResolvedValue(MULTI_DOMAIN_SCHEMAS);
    render(<App />);
    const select = (await screen.findByTestId('domain-select')) as HTMLSelectElement;
    expect(screen.getByRole('option', { name: 'default' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'ai_agent' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'hr' })).toBeInTheDocument();
    // Defaults to the active value.
    expect(select.value).toBe('default');
    await settle();
  });

  it('submitting with a selected domain calls createRun with that domain', async () => {
    vi.mocked(client.getSchemas).mockResolvedValue(MULTI_DOMAIN_SCHEMAS);
    vi.mocked(client.createRun).mockResolvedValue({ run_id: 'new-run-1' });
    render(<App />);

    const select = await screen.findByTestId('domain-select');
    fireEvent.change(select, { target: { value: 'ai_agent' } });

    fireEvent.change(screen.getByLabelText(/Category/i), {
      target: { value: 'Cloud Storage' },
    });
    fireEvent.change(screen.getByLabelText(/Competitors/i), {
      target: { value: 'AWS, Azure' },
    });
    fireEvent.change(screen.getByLabelText(/Research Goal/i), {
      target: { value: 'Compare pricing' },
    });

    fireEvent.click(screen.getByRole('button', { name: /开始实时分析/ }));

    await screen.findByText(/new-run-1/);
    expect(client.createRun).toHaveBeenCalledWith(
      expect.objectContaining({
        category: 'Cloud Storage',
        competitors: ['AWS', 'Azure'],
        goal: 'Compare pricing',
        domain: 'ai_agent',
      }),
    );
    await settle();
  });

  it('degrades gracefully when getSchemas fails: no select, no domain sent', async () => {
    vi.mocked(client.getSchemas).mockRejectedValue(new Error('boom'));
    vi.mocked(client.createRun).mockResolvedValue({ run_id: 'new-run-2' });
    render(<App />);
    // Form still works without the dropdown.
    fireEvent.change(screen.getByLabelText(/Category/i), { target: { value: 'CRM' } });
    fireEvent.change(screen.getByLabelText(/Competitors/i), { target: { value: 'Acme' } });
    fireEvent.change(screen.getByLabelText(/Research Goal/i), { target: { value: 'g' } });
    fireEvent.click(screen.getByRole('button', { name: /开始实时分析/ }));
    await screen.findByText(/new-run-2/);
    // No domain-select rendered, and the createRun payload carries NO domain key.
    expect(screen.queryByTestId('domain-select')).not.toBeInTheDocument();
    const arg = vi.mocked(client.createRun).mock.calls[0][0];
    expect('domain' in arg).toBe(false);
    await settle();
  });

  it('aborts the live run when the confirm guard is dismissed', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    vi.mocked(client.createRun).mockResolvedValue({ run_id: 'guarded-run' });
    render(<App />);

    fireEvent.change(screen.getByLabelText(/Category/i), { target: { value: 'CRM' } });
    fireEvent.change(screen.getByLabelText(/Competitors/i), { target: { value: 'Acme' } });
    fireEvent.change(screen.getByLabelText(/Research Goal/i), { target: { value: 'g' } });
    fireEvent.click(screen.getByRole('button', { name: /开始实时分析/ }));

    expect(window.confirm).toHaveBeenCalled();
    expect(client.createRun).not.toHaveBeenCalled();
    await settle();
  });

  it('proceeds with the live run when the confirm guard is accepted', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(client.createRun).mockResolvedValue({ run_id: 'confirmed-run' });
    render(<App />);

    fireEvent.change(screen.getByLabelText(/Category/i), { target: { value: 'CRM' } });
    fireEvent.change(screen.getByLabelText(/Competitors/i), { target: { value: 'Acme' } });
    fireEvent.change(screen.getByLabelText(/Research Goal/i), { target: { value: 'g' } });
    fireEvent.click(screen.getByRole('button', { name: /开始实时分析/ }));

    await screen.findByText(/confirmed-run/);
    expect(client.createRun).toHaveBeenCalledTimes(1);
    await settle();
  });
});

describe('App Discovery Mode', () => {
  it('submits with EMPTY competitors (Discovery Mode) and sends market_scope', async () => {
    vi.mocked(client.createRun).mockResolvedValue({ run_id: 'disc-run-1' });
    render(<App />);

    fireEvent.change(screen.getByLabelText(/Category/i), {
      target: { value: '通用 AI Agent' },
    });
    fireEvent.change(screen.getByLabelText(/Research Goal/i), {
      target: { value: '竞品分析' },
    });
    // Competitors left blank -> Discovery Mode badge + market-scope select show.
    expect(screen.getByTestId('discovery-mode-badge')).toBeInTheDocument();
    fireEvent.change(screen.getByTestId('market-scope-select'), {
      target: { value: 'china' },
    });

    fireEvent.click(screen.getByRole('button', { name: /开始实时分析/ }));

    await screen.findByText(/disc-run-1/);
    expect(client.createRun).toHaveBeenCalledWith(
      expect.objectContaining({
        category: '通用 AI Agent',
        competitors: [],
        goal: '竞品分析',
        market_scope: 'china',
      }),
    );
    await settle();
  });

  it('hides the market-scope select once competitors are typed (Directed Mode)', async () => {
    render(<App />);
    expect(screen.getByTestId('market-scope-select')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/Competitors/i), {
      target: { value: 'Notion, Coze' },
    });
    expect(screen.queryByTestId('market-scope-select')).not.toBeInTheDocument();
    expect(screen.queryByTestId('discovery-mode-badge')).not.toBeInTheDocument();
    await settle();
  });

  it('renders the discovered-competitors panel from a deep-linked run trace', async () => {
    const discoveredTrace: TraceResponse = {
      events: [
        {
          id: 1,
          run_id: 'disc-run-2',
          agent: 'collector',
          node: 'discover',
          event_type: 'discovery_started',
          payload_json: JSON.stringify({ category: '通用 AI Agent', market_scope: 'china' }),
          created_at: 1749340800,
        },
        {
          id: 2,
          run_id: 'disc-run-2',
          agent: 'collector',
          node: 'discover',
          event_type: 'competitors_discovered',
          payload_json: JSON.stringify({
            selected: ['Manus', 'Coze'],
            candidates: [
              { name: 'Manus', source_count: 3, has_official: true },
              { name: 'Coze', source_count: 2, has_official: true },
            ],
            queries: ['通用 AI Agent 竞品有哪些'],
          }),
          created_at: 1749340801,
        },
      ],
      max_seq: 2,
    };
    vi.mocked(client.getTrace).mockResolvedValue(discoveredTrace);
    window.history.pushState({}, '', '?run=disc-run-2');

    render(<App />);

    const panel = await screen.findByTestId('discovered-competitors');
    expect(panel).toBeInTheDocument();
    const chips = await screen.findAllByTestId('discovered-chip');
    expect(chips.map((c) => c.textContent)).toEqual(['Manus', 'Coze']);
    await settle();
    window.history.pushState({}, '', '/');
  });
});

describe('deep-link ?run=<id>', () => {
  afterEach(() => {
    window.history.pushState({}, '', '/');
  });

  it('loads an existing run id from the URL query param on mount', async () => {
    vi.mocked(client.getTrace).mockResolvedValue(EMPTY_TRACE);
    vi.mocked(client.getMetrics).mockResolvedValue(EMPTY_METRICS);
    vi.mocked(client.getSchemas).mockResolvedValue(MOCK_SCHEMAS);
    window.history.pushState({}, '', '?run=demo-run-123');
    render(<App />);
    // The active-run banner shows the loaded id (App renders "run: <id>").
    expect(screen.getByText(/demo-run-123/)).toBeInTheDocument();
    await settle();
  });
});
