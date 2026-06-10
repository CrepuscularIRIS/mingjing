/**
 * ExecutionTrace tests.
 *
 * Covers:
 *  1. Unit tests for deriveNodeStatus (pure helper — no DOM needed)
 *  2. Component tests (via vi.mock('../api/client')):
 *     - DAG renders with node labels (via accessible node-button list)
 *     - clicking a node shows the detail panel with mocked LLM call data
 *     - no-runId: static DAG renders (all pending), no-run banner shown,
 *       getTrace not called
 */

import {
  act,
  render,
  screen,
  waitFor,
  fireEvent,
  cleanup,
} from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import * as client from '../api/client';
import type { LlmCallsResponse, TraceEvent, TraceResponse } from '../api/types';
import {
  deriveNodeStatus,
  type NodeStatus,
} from '../lib/executionTraceLogic';
import { ExecutionTrace } from './ExecutionTrace';

vi.mock('../api/client');

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

/** collect_start only → collect running */
const TRACE_COLLECT_RUNNING: TraceResponse = {
  events: [
    {
      id: 1,
      run_id: 'run-1',
      agent: 'collector',
      node: 'collect_node',
      event_type: 'collect_start',
      payload_json: '{}',
      created_at: 1748000000,
    },
  ],
  max_seq: 1,
};

/** collect_start + collect_done → collect done; qa_fail → qa flagged */
const TRACE_COLLECT_DONE_QA_FLAGGED: TraceResponse = {
  events: [
    {
      id: 1,
      run_id: 'run-1',
      agent: 'collector',
      node: 'collect_node',
      event_type: 'collect_start',
      payload_json: '{}',
      created_at: 1748000000,
    },
    {
      id: 2,
      run_id: 'run-1',
      agent: 'collector',
      node: 'collect_node',
      event_type: 'collect_done',
      payload_json: '{}',
      created_at: 1748000001,
    },
    {
      id: 3,
      run_id: 'run-1',
      agent: 'qa',
      node: 'qa_node',
      event_type: 'qa_fail',
      payload_json: '{}',
      created_at: 1748000002,
    },
  ],
  max_seq: 3,
};

const MOCK_LLM_CALLS: LlmCallsResponse = {
  calls: [
    {
      id: 1,
      agent: 'collector',
      model: 'minimax-text-01',
      prompt_json: JSON.stringify([
        { role: 'system', content: 'You are a collector.' },
        { role: 'user', content: 'Collect pricing data.' },
      ]),
      output_text: 'Collected 5 sources.',
      prompt_tokens: 25,
      completion_tokens: 12,
      total_tokens: 37,
      created_at: 1748000003,
    },
  ],
};

const EMPTY_LLM_CALLS: LlmCallsResponse = { calls: [] };
const EMPTY_TRACE: TraceResponse = { events: [], max_seq: 0 };

// ---------------------------------------------------------------------------
// M3 (judge P2): settled-run demotion — a finished run may not show a
// perpetual "running" node (waypoints only ever get node_enter).
// ---------------------------------------------------------------------------

type TE = TraceResponse['events'][number];
const ev = (id: number, event_type: string, node = '', agent = 'system'): TE => ({
  id,
  run_id: 'run-1',
  agent,
  node,
  event_type,
  payload_json: '{}',
  created_at: 1748000000 + id,
});

describe('deriveNodeStatus settled-run demotion (M3)', () => {
  it('demotes running waypoints to done after a clean settle (synthesis_done)', () => {
    const status = deriveNodeStatus([
      ev(1, 'node_enter', 'intake_node'),
      ev(2, 'node_enter', 'plan_node'),
      ev(3, 'collect_start', 'collect_node', 'collector'),
      ev(4, 'collect_done', 'collect_node', 'collector'),
      ev(5, 'node_enter', 'route_node'),
      ev(6, 'run_partial', 'write_node', 'writer'),
      ev(7, 'synthesis_start', 'synthesis_node', 'writer'),
      ev(8, 'synthesis_done', 'synthesis_node', 'writer'),
    ]);
    expect(status.intake).toBe<NodeStatus>('done');
    expect(status.plan).toBe<NodeStatus>('done');
    expect(status.route).toBe<NodeStatus>('done');
    expect(status.synthesis).toBe<NodeStatus>('done');
  });

  it('run_partial alone does NOT settle the DAG (synthesis may still be running)', () => {
    const status = deriveNodeStatus([
      ev(1, 'node_enter', 'intake_node'),
      ev(2, 'run_partial', 'write_node', 'writer'),
      ev(3, 'synthesis_start', 'synthesis_node', 'writer'),
    ]);
    expect(status.synthesis).toBe<NodeStatus>('running');
    expect(status.intake).toBe<NodeStatus>('running');
  });

  it('a hard run_error settles the DAG: running nodes demote to empty (no proven payload)', () => {
    const status = deriveNodeStatus([
      ev(1, 'collect_start', 'collect_node', 'collector'),
      ev(2, 'run_error', ''),
    ]);
    expect(status.collect).toBe<NodeStatus>('empty');
  });

  it('mid-run without any settle event keeps running nodes running', () => {
    const status = deriveNodeStatus([
      ev(1, 'node_enter', 'intake_node'),
      ev(2, 'collect_start', 'collect_node', 'collector'),
    ]);
    expect(status.intake).toBe<NodeStatus>('running');
    expect(status.collect).toBe<NodeStatus>('running');
  });
});

// ---------------------------------------------------------------------------
// 1. Unit tests for deriveNodeStatus
// ---------------------------------------------------------------------------

describe('deriveNodeStatus', () => {
  it('returns all pending for empty events', () => {
    const status = deriveNodeStatus([]);
    for (const [, v] of Object.entries(status)) {
      expect(v).toBe<NodeStatus>('pending');
    }
  });

  it('collect is running after collect_start', () => {
    const status = deriveNodeStatus(TRACE_COLLECT_RUNNING.events);
    expect(status.collect).toBe<NodeStatus>('running');
    expect(status.analyze).toBe<NodeStatus>('pending');
  });

  it('discover lights for a Discovery-Mode run (started → running → done)', () => {
    const started: TraceEvent[] = [
      { id: 1, run_id: 'r', agent: 'collector', node: 'discover', event_type: 'discovery_started', created_at: 0 },
    ];
    expect(deriveNodeStatus(started).discover).toBe<NodeStatus>('running');
    const done: TraceEvent[] = [
      ...started,
      { id: 2, run_id: 'r', agent: 'collector', node: 'discover', event_type: 'competitors_discovered', created_at: 0 },
    ];
    expect(deriveNodeStatus(done).discover).toBe<NodeStatus>('done');
  });

  it('discover stays pending for a Directed-Mode run (no discovery events)', () => {
    const status = deriveNodeStatus(TRACE_COLLECT_RUNNING.events);
    expect(status.discover).toBe<NodeStatus>('pending');
  });

  it('collect is done after collect_start + collect_done', () => {
    const events = TRACE_COLLECT_DONE_QA_FLAGGED.events.slice(0, 2);
    const status = deriveNodeStatus(events);
    expect(status.collect).toBe<NodeStatus>('done');
  });

  it('qa is flagged after qa_fail', () => {
    const status = deriveNodeStatus(TRACE_COLLECT_DONE_QA_FLAGGED.events);
    expect(status.qa).toBe<NodeStatus>('flagged');
  });

  it('collect is done AND qa is flagged in combined trace', () => {
    const status = deriveNodeStatus(TRACE_COLLECT_DONE_QA_FLAGGED.events);
    expect(status.collect).toBe<NodeStatus>('done');
    expect(status.qa).toBe<NodeStatus>('flagged');
  });

  it('qa is done after qa_pass (not flagged from an earlier qa_fail)', () => {
    const events = [
      {
        id: 1,
        run_id: 'run-1',
        agent: 'qa',
        node: 'qa_node',
        event_type: 'qa_fail',
        payload_json: '{}',
        created_at: 1748000001,
      },
      {
        id: 2,
        run_id: 'run-1',
        agent: 'qa',
        node: 'qa_node',
        event_type: 'qa_pass',
        payload_json: '{}',
        created_at: 1748000002,
      },
    ];
    const status = deriveNodeStatus(events);
    expect(status.qa).toBe<NodeStatus>('done');
  });

  it('write is done after run_complete', () => {
    const events = [
      {
        id: 1,
        run_id: 'run-1',
        agent: 'writer',
        node: 'write_node',
        event_type: 'run_complete',
        payload_json: '{}',
        created_at: 1748000010,
      },
    ];
    const status = deriveNodeStatus(events);
    expect(status.write).toBe<NodeStatus>('done');
  });

  it('synthesis is running after synthesis_start', () => {
    const events = [
      {
        id: 1,
        run_id: 'run-1',
        agent: null,
        node: 'synthesis',
        event_type: 'synthesis_start',
        payload_json: '{}',
        created_at: 1748000011,
      },
    ];
    const status = deriveNodeStatus(events);
    expect(status.synthesis).toBe<NodeStatus>('running');
    expect(status.write).toBe<NodeStatus>('pending');
  });

  it('synthesis is done after synthesis_start + synthesis_done', () => {
    const events = [
      {
        id: 1,
        run_id: 'run-1',
        agent: null,
        node: 'synthesis',
        event_type: 'synthesis_start',
        payload_json: '{}',
        created_at: 1748000011,
      },
      {
        id: 2,
        run_id: 'run-1',
        agent: null,
        node: 'synthesis',
        event_type: 'synthesis_done',
        payload_json: '{}',
        created_at: 1748000012,
      },
    ];
    const status = deriveNodeStatus(events);
    expect(status.synthesis).toBe<NodeStatus>('done');
  });

  it('synthesis is empty after synthesis_start + synthesis_empty (honest no-brief)', () => {
    const events = [
      {
        id: 1,
        run_id: 'run-1',
        agent: null,
        node: 'synthesis',
        event_type: 'synthesis_start',
        payload_json: '{}',
        created_at: 1748000011,
      },
      {
        id: 2,
        run_id: 'run-1',
        agent: null,
        node: 'synthesis',
        event_type: 'synthesis_empty',
        payload_json: '{"sentences":0}',
        created_at: 1748000012,
      },
    ];
    const status = deriveNodeStatus(events);
    // Must NOT misrepresent an empty synthesis as a completed (green) ``done``.
    expect(status.synthesis).toBe<NodeStatus>('empty');
    expect(status.synthesis).not.toBe<NodeStatus>('done');
  });

  it('synthesis pending when no synthesis events present', () => {
    const status = deriveNodeStatus(TRACE_COLLECT_DONE_QA_FLAGGED.events);
    expect(status.synthesis).toBe<NodeStatus>('pending');
  });
});

// ---------------------------------------------------------------------------
// 2. Component tests
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.mocked(client.getTrace).mockResolvedValue(TRACE_COLLECT_DONE_QA_FLAGGED);
  vi.mocked(client.getLlmCalls).mockResolvedValue(MOCK_LLM_CALLS);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('ExecutionTrace component', () => {
  it('renders static DAG node buttons even with no runId', () => {
    vi.mocked(client.getTrace).mockResolvedValue(EMPTY_TRACE);
    render(<ExecutionTrace runId={null} />);

    // Directed-Mode topology: the 9 graph nodes, and NO discover pre-step node.
    const nodeIds = ['intake', 'plan', 'collect', 'analyze', 'qa', 'route', 'revise', 'write', 'synthesis'];
    for (const id of nodeIds) {
      expect(screen.getByTestId(`node-btn-${id}`)).toBeInTheDocument();
    }
    expect(screen.queryByTestId('node-btn-discover')).not.toBeInTheDocument();
  });

  it('shows the no-run banner and does NOT call getTrace when runId is null', () => {
    render(<ExecutionTrace runId={null} />);
    expect(screen.getByTestId('no-run-banner')).toBeInTheDocument();
    expect(client.getTrace).not.toHaveBeenCalled();
  });

  it('renders the 9 graph node buttons after polling a Directed-Mode run (no discover)', async () => {
    render(<ExecutionTrace runId="run-1" />);
    await waitFor(() => {
      expect(client.getTrace).toHaveBeenCalled();
    });
    const nodeIds = ['intake', 'plan', 'collect', 'analyze', 'qa', 'route', 'revise', 'write', 'synthesis'];
    for (const id of nodeIds) {
      expect(screen.getByTestId(`node-btn-${id}`)).toBeInTheDocument();
    }
    expect(screen.queryByTestId('node-btn-discover')).not.toBeInTheDocument();
  });

  it('renders the discover node only for a Discovery-Mode run (discovery events present)', async () => {
    const discTrace: TraceResponse = {
      events: [
        { id: 1, run_id: 'd', agent: 'collector', node: 'discover', event_type: 'discovery_started', created_at: 0 },
        { id: 2, run_id: 'd', agent: 'collector', node: 'discover', event_type: 'competitors_discovered', created_at: 0 },
      ],
      max_seq: 2,
    };
    vi.mocked(client.getTrace).mockResolvedValue(discTrace);
    render(<ExecutionTrace runId="disc-run" />);
    expect(await screen.findByTestId('node-btn-discover')).toBeInTheDocument();
    expect(await screen.findByTestId('node-status-discover')).toHaveTextContent('done');
  });

  it('shows the LangSmith fallback label when VITE_LANGSMITH_URL is not configured', () => {
    // In the test environment VITE_LANGSMITH_URL is not set, so the offline fallback renders.
    render(<ExecutionTrace runId={null} />);
    const el = screen.getByTestId('langsmith-link');
    expect(el).toBeInTheDocument();
    // Fallback is a <span>, not a live deep link — no href attribute.
    expect(el).not.toHaveAttribute('href');
    expect(el.textContent).toContain('LangSmith');
  });

  it('clicking a node button opens the detail panel', async () => {
    render(<ExecutionTrace runId="run-1" />);
    // Wait for data to load
    await waitFor(() => {
      expect(client.getLlmCalls).toHaveBeenCalled();
    });

    // Click 'collect' node button
    const collectBtn = screen.getByTestId('node-btn-collect');
    fireEvent.click(collectBtn);

    // Detail panel should appear
    await waitFor(() => {
      expect(screen.getByTestId('node-detail-panel')).toBeInTheDocument();
    });
  });

  it('detail panel shows LLM call model and tokens for collect node', async () => {
    render(<ExecutionTrace runId="run-1" />);
    await waitFor(() => {
      expect(client.getLlmCalls).toHaveBeenCalled();
    });

    fireEvent.click(screen.getByTestId('node-btn-collect'));

    await waitFor(() => {
      expect(screen.getByTestId('node-detail-panel')).toBeInTheDocument();
    });

    // The mock call has agent='collector' which maps to collect node
    expect(screen.getByTestId('et-llm-card-0')).toBeInTheDocument();
    expect(screen.getByTestId('et-token-total').textContent).toContain('37');
    expect(screen.getByTestId('et-token-usage').textContent).toContain('25');
    expect(screen.getByTestId('et-token-usage').textContent).toContain('12');
  });

  it('detail panel shows the LLM output for collect node', async () => {
    render(<ExecutionTrace runId="run-1" />);
    await waitFor(() => {
      expect(client.getLlmCalls).toHaveBeenCalled();
    });

    fireEvent.click(screen.getByTestId('node-btn-collect'));

    await waitFor(() => {
      expect(screen.getByTestId('node-detail-panel')).toBeInTheDocument();
    });

    // Output is shown (defaultOpen=true)
    expect(screen.getByTestId('et-llm-output').textContent).toContain('Collected 5 sources.');
  });

  it('system nodes (intake) show "此节点暂无 LLM 调用" with no llm calls', async () => {
    render(<ExecutionTrace runId="run-1" />);
    await waitFor(() => {
      expect(client.getLlmCalls).toHaveBeenCalled();
    });

    fireEvent.click(screen.getByTestId('node-btn-intake'));

    await waitFor(() => {
      expect(screen.getByTestId('node-detail-panel')).toBeInTheDocument();
    });

    expect(screen.getByTestId('et-no-llm-calls')).toBeInTheDocument();
  });

  it('clicking same node again closes the detail panel', async () => {
    render(<ExecutionTrace runId="run-1" />);
    await waitFor(() => {
      expect(client.getLlmCalls).toHaveBeenCalled();
    });

    const collectBtn = screen.getByTestId('node-btn-collect');
    fireEvent.click(collectBtn);
    await waitFor(() => {
      expect(screen.getByTestId('node-detail-panel')).toBeInTheDocument();
    });

    // Click again to close
    fireEvent.click(collectBtn);
    await waitFor(() => {
      expect(screen.queryByTestId('node-detail-panel')).not.toBeInTheDocument();
    });
  });

  it('qa node shows "flagged" status after qa_fail event', async () => {
    render(<ExecutionTrace runId="run-1" />);
    // Wait for trace data to load
    await waitFor(() => {
      expect(client.getTrace).toHaveBeenCalled();
    });
    // The qa button should reflect flagged status in its text
    const qaBtn = screen.getByTestId('node-btn-qa');
    expect(qaBtn.textContent).toContain('flagged');
  });

  it('collect node shows "done" status after collect_done event', async () => {
    render(<ExecutionTrace runId="run-1" />);
    await waitFor(() => {
      expect(client.getTrace).toHaveBeenCalled();
    });
    const collectBtn = screen.getByTestId('node-btn-collect');
    expect(collectBtn.textContent).toContain('done');
  });

  it('all nodes show pending status with empty trace', async () => {
    vi.mocked(client.getTrace).mockResolvedValue(EMPTY_TRACE);
    vi.mocked(client.getLlmCalls).mockResolvedValue(EMPTY_LLM_CALLS);
    render(<ExecutionTrace runId="run-1" />);
    await waitFor(() => {
      expect(client.getTrace).toHaveBeenCalled();
    });
    // All node buttons should show waiting (including synthesis)
    const nodeIds = ['intake', 'plan', 'collect', 'analyze', 'qa', 'route', 'revise', 'write', 'synthesis'];
    for (const id of nodeIds) {
      expect(screen.getByTestId(`node-btn-${id}`).textContent).toContain('waiting');
    }
  });

  // NODE_AGENT sanity: synthesis must map to 'synthesis' so its LLM calls surface
it('NODE_AGENT.synthesis maps to "synthesis" (unit assertion)', async () => {
    // Import the component module to inspect NODE_AGENT via side-effect:
    // The easiest route is to render a synthesis node and confirm a synthesis
    // llm_call IS shown (not hidden behind et-no-llm-calls).
    const SYNTHESIS_LLM_CALLS: LlmCallsResponse = {
      calls: [
        {
          id: 42,
          agent: 'synthesis',
          model: 'minimax-text-01',
          prompt_json: JSON.stringify([
            { role: 'system', content: 'Synthesise.' },
            { role: 'user', content: 'Write synthesis.' },
          ]),
          output_text: 'Synthesis complete.',
          prompt_tokens: 10,
          completion_tokens: 5,
          total_tokens: 15,
          created_at: 1748000020,
        },
      ],
    };
    vi.mocked(client.getLlmCalls).mockResolvedValue(SYNTHESIS_LLM_CALLS);
    vi.mocked(client.getTrace).mockResolvedValue(EMPTY_TRACE);

    render(<ExecutionTrace runId="run-1" />);
    await waitFor(() => {
      expect(client.getLlmCalls).toHaveBeenCalled();
    });

    fireEvent.click(screen.getByTestId('node-btn-synthesis'));

    await waitFor(() => {
      expect(screen.getByTestId('node-detail-panel')).toBeInTheDocument();
    });

    // With NODE_AGENT.synthesis === 'synthesis', the call is shown (not hidden)
    expect(screen.queryByTestId('et-no-llm-calls')).not.toBeInTheDocument();
    expect(screen.getByTestId('et-llm-card-0')).toBeInTheDocument();
    expect(screen.getByTestId('et-token-total').textContent).toContain('15');
    expect(screen.getByTestId('et-llm-output').textContent).toContain('Synthesis complete.');
  });

  it('synthesis node shows "done" status after synthesis_done event', async () => {
    const TRACE_SYNTHESIS_DONE: TraceResponse = {
      events: [
        {
          id: 1,
          run_id: 'run-1',
          agent: null,
          node: 'synthesis',
          event_type: 'synthesis_start',
          payload_json: '{}',
          created_at: 1748000011,
        },
        {
          id: 2,
          run_id: 'run-1',
          agent: null,
          node: 'synthesis',
          event_type: 'synthesis_done',
          payload_json: '{}',
          created_at: 1748000012,
        },
      ],
      max_seq: 2,
    };
    vi.mocked(client.getTrace).mockResolvedValue(TRACE_SYNTHESIS_DONE);
    vi.mocked(client.getLlmCalls).mockResolvedValue(EMPTY_LLM_CALLS);
    render(<ExecutionTrace runId="run-1" />);
    await waitFor(() => {
      expect(client.getTrace).toHaveBeenCalled();
    });
    expect(screen.getByTestId('node-btn-synthesis').textContent).toContain('done');
  });

  // ---- run-switch: clear the prior run's trace + sinceSeq under the new id --

  it('clears run A trace events when switching to a different run id B', async () => {
    vi.useFakeTimers();
    try {
      // Run A: collect done + qa flagged. Run B: empty trace (all pending).
      vi.mocked(client.getTrace).mockImplementation(async (id) =>
        id === 'B' ? EMPTY_TRACE : TRACE_COLLECT_DONE_QA_FLAGGED,
      );
      vi.mocked(client.getLlmCalls).mockResolvedValue(EMPTY_LLM_CALLS);

      const { rerender } = render(<ExecutionTrace runId="A" />);
      await act(async () => { await vi.advanceTimersByTimeAsync(0); });
      expect(screen.getByTestId('node-btn-qa').textContent).toContain('flagged');

      // Switch to a DIFFERENT run — reset effect clears A's events immediately.
      rerender(<ExecutionTrace runId="B" />);
      expect(screen.getByTestId('node-btn-qa').textContent).toContain('waiting');
      expect(screen.getByTestId('node-btn-collect').textContent).toContain('waiting');

      // sinceSeq resets so getTrace for B is requested from seq 0 on next tick.
      await act(async () => { await vi.advanceTimersByTimeAsync(2100); });
      expect(vi.mocked(client.getTrace)).toHaveBeenCalledWith('B', 0);
      expect(screen.getByTestId('node-btn-qa').textContent).toContain('waiting');
    } finally {
      vi.useRealTimers();
    }
  });

  it('stale: a run A trace resolving AFTER switching to B does not leak under B', async () => {
    vi.useFakeTimers();
    try {
      let resolveA: (r: TraceResponse) => void = () => {};
      vi.mocked(client.getTrace).mockImplementation((id) => {
        if (id === 'A') return new Promise<TraceResponse>((res) => { resolveA = res; });
        return Promise.resolve(EMPTY_TRACE);
      });
      vi.mocked(client.getLlmCalls).mockResolvedValue(EMPTY_LLM_CALLS);

      const { rerender } = render(<ExecutionTrace runId="A" />);
      // A in-flight; switch to B before A resolves.
      rerender(<ExecutionTrace runId="B" />);
      expect(screen.getByTestId('node-btn-qa').textContent).toContain('waiting');

      // Resolve A's stale trace (qa flagged) — must be dropped by the ref guard.
      await act(async () => {
        resolveA(TRACE_COLLECT_DONE_QA_FLAGGED);
        await Promise.resolve();
      });

      expect(screen.getByTestId('node-btn-qa').textContent).toContain('waiting');
    } finally {
      vi.useRealTimers();
    }
  });
});
