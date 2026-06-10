/**
 * Observability view integration tests.
 *
 * The API client is mocked — no real backend is hit. Covers:
 *  - agent list renders from trace events and llm_calls
 *  - clicking an agent shows its llm call prompt / output / tokens
 *  - token chart renders when llm calls are present
 *  - empty state: "no LLM calls yet" for agents with only trace events
 *  - graceful empty state: no run, no agents
 */

import { render, screen, waitFor, fireEvent, cleanup, act } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import * as client from '../api/client';
import type { LlmCallsResponse, TraceResponse } from '../api/types';
import { Observability } from './Observability';

vi.mock('../api/client');

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const MOCK_TRACE: TraceResponse = {
  events: [
    {
      id: 1,
      run_id: 'run-1',
      agent: 'collector',
      node: 'collect_node',
      event_type: 'node_enter',
      payload_json: '{}',
      created_at: 1748000000,
    },
    {
      id: 2,
      run_id: 'run-1',
      agent: 'analyst',
      node: 'analyze_node',
      event_type: 'analyze_done',
      payload_json: '{}',
      created_at: 1748000001,
    },
  ],
  max_seq: 2,
};

const MOCK_LLM_CALLS: LlmCallsResponse = {
  calls: [
    {
      id: 1,
      agent: 'analyst',
      model: 'minimax-text-01',
      prompt_json: JSON.stringify([
        { role: 'system', content: 'You are an analyst.' },
        { role: 'user', content: 'Summarise pricing data.' },
      ]),
      output_text: 'Acme charges $10/mo for starter.',
      prompt_tokens: 20,
      completion_tokens: 10,
      total_tokens: 30,
      created_at: 1748000002,
    },
  ],
};

const EMPTY_LLM_CALLS: LlmCallsResponse = { calls: [] };

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.mocked(client.getTrace).mockResolvedValue(MOCK_TRACE);
  vi.mocked(client.getLlmCalls).mockResolvedValue(MOCK_LLM_CALLS);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Observability', () => {
  it('shows empty state when no run is provided', () => {
    render(<Observability runId={null} />);
    expect(screen.getByText(/Start a run/i)).toBeInTheDocument();
  });

  it('renders the agent list after polling', async () => {
    render(<Observability runId="run-1" />);
    // Both agents derived from trace events should appear.
    expect(await screen.findByTestId('agent-btn-collector')).toBeInTheDocument();
    expect(await screen.findByTestId('agent-btn-analyst')).toBeInTheDocument();
  });

  it('shows select-agent prompt before any agent is clicked', async () => {
    render(<Observability runId="run-1" />);
    await screen.findByTestId('agent-btn-analyst');
    expect(screen.getByTestId('select-agent-prompt')).toBeInTheDocument();
  });

  it('clicking an agent with an LLM call shows its output and tokens', async () => {
    render(<Observability runId="run-1" />);
    const analystBtn = await screen.findByTestId('agent-btn-analyst');
    fireEvent.click(analystBtn);

    // The agent detail panel should appear.
    await waitFor(() => {
      expect(screen.getByTestId('agent-detail-analyst')).toBeInTheDocument();
    });

    // Token usage is shown.
    const tokenUsage = screen.getByTestId('token-usage');
    expect(tokenUsage.textContent).toContain('20');
    expect(tokenUsage.textContent).toContain('10');

    // LLM call card is rendered.
    expect(screen.getByTestId('llm-call-card-0')).toBeInTheDocument();
  });

  it('clicking analyst agent shows its output text', async () => {
    render(<Observability runId="run-1" />);
    const analystBtn = await screen.findByTestId('agent-btn-analyst');
    fireEvent.click(analystBtn);

    await waitFor(() => {
      expect(screen.getByTestId('agent-detail-analyst')).toBeInTheDocument();
    });

    // Expand the output collapsible (it is defaultOpen=true).
    const output = screen.getByTestId('llm-output');
    expect(output.textContent).toContain('Acme charges $10/mo for starter.');
  });

  it('clicking an agent with no LLM calls shows the empty-calls message', async () => {
    render(<Observability runId="run-1" />);
    const collectorBtn = await screen.findByTestId('agent-btn-collector');
    fireEvent.click(collectorBtn);

    await waitFor(() => {
      expect(screen.getByTestId('agent-detail-collector')).toBeInTheDocument();
    });

    // Collector has no LLM calls in the mock — empty state shown.
    expect(screen.getByTestId('no-llm-calls')).toBeInTheDocument();
  });

  it('renders the token chart when LLM calls are present', async () => {
    render(<Observability runId="run-1" />);
    // Chart should appear after polling resolves.
    await waitFor(() => {
      expect(screen.getByTestId('token-chart')).toBeInTheDocument();
    });
  });

  it('does not render the token chart when there are no LLM calls', async () => {
    vi.mocked(client.getLlmCalls).mockResolvedValue(EMPTY_LLM_CALLS);
    render(<Observability runId="run-1" />);
    await screen.findByTestId('agent-btn-collector');
    // Chart must not appear when there are no LLM calls.
    expect(screen.queryByTestId('token-chart')).not.toBeInTheDocument();
  });

  it('degrades gracefully with trace events but zero LLM calls', async () => {
    vi.mocked(client.getLlmCalls).mockResolvedValue(EMPTY_LLM_CALLS);
    render(<Observability runId="run-1" />);

    // Agent list still renders.
    expect(await screen.findByTestId('agent-btn-collector')).toBeInTheDocument();

    // Clicking an agent still works and shows the empty-calls message.
    fireEvent.click(screen.getByTestId('agent-btn-collector'));
    await waitFor(() => {
      expect(screen.getByTestId('agent-detail-collector')).toBeInTheDocument();
    });
    expect(screen.getByTestId('no-llm-calls')).toBeInTheDocument();
  });

  it('shows the "no activity yet" prompt before agents are loaded', () => {
    // getTrace returns nothing immediately (never resolves during this check)
    vi.mocked(client.getTrace).mockReturnValue(new Promise(() => {}));
    vi.mocked(client.getLlmCalls).mockReturnValue(new Promise(() => {}));
    render(<Observability runId="run-1" />);
    // The agent list area shows the empty state message.
    expect(screen.getByTestId('no-agents')).toBeInTheDocument();
  });

  it('dedups trace events across polls — no duplicate React keys when a poll re-delivers events', async () => {
    // Regression: getTrace re-delivers the SAME events on a later tick (overlapping
    // poll / StrictMode double-invoke of the polling effect). A raw append produced
    // duplicate ev.id → duplicate keys in the per-agent trace-event list. The view
    // must dedup (mergeTraceEvents). With the bug, collector's event id 1 rendered
    // twice (length 2); the fix keeps it at 1.
    vi.useFakeTimers();
    try {
      vi.mocked(client.getTrace).mockResolvedValue(MOCK_TRACE); // same events every tick
      render(<Observability runId="run-1" />);
      await act(async () => { await vi.advanceTimersByTimeAsync(0); }); // immediate first tick
      await act(async () => { await vi.advanceTimersByTimeAsync(2100); }); // second poll re-delivers
      fireEvent.click(screen.getByTestId('agent-btn-collector'));
      expect(document.querySelectorAll('[data-testid="trace-event-1"]').length).toBe(1);
    } finally {
      vi.useRealTimers();
    }
  });
});
