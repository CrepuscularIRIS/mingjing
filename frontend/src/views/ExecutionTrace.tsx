/**
 * ExecutionTrace — 执行轨迹 tab view.
 *
 * Renders the LangGraph topology as a reactflow DAG: the 9 graph nodes plus an
 * optional `discover` pre-step (lit only for Discovery-Mode runs).
 * Nodes are colored by agent role and lit by live status derived from
 * trace events (pending / running / done / empty / flagged). Clicking a node
 * opens a right-panel showing that node's LLM call detail.
 *
 * An "Open in LangSmith" external link sits in the top-right corner.
 *
 * DAG topology (manual positions — no dagre):
 *   intake(300,0) → plan(300,100) → collect(300,200) → analyze(300,300)
 *   → qa(300,400) → route(300,500)
 *   route → write(500,600)       ← success exit
 *   route → revise(100,400)      ← revision loop
 *   revise → collect              ← back-edge
 *   write → synthesis(500,700)   ← post-write synthesis pass
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ReactFlow, Background, MarkerType, type Node, type Edge } from 'reactflow';
import 'reactflow/dist/style.css';

import { getLlmCalls, getTrace } from '../api/client';
import type { LlmCall, LlmCallsResponse, TraceEvent, TraceResponse } from '../api/types';
import { usePolling } from '../hooks/usePolling';
import {
  ALL_NODE_IDS,
  deriveNodeStatus,
  type NodeId,
  type NodeStatus,
} from '../lib/executionTraceLogic';
import { mergeTraceEvents } from '../lib/trace';

// ---------------------------------------------------------------------------
// Node color palette (agent role → inline style colors)
// ---------------------------------------------------------------------------

interface RoleColors {
  bg: string;
  border: string;
  text: string;
}

// Agent-role colors, mapped to the project design tokens (hex copied verbatim
// from tailwind.config.js) so the DAG reads on-brand AND aligns with the
// strength color ramp used across the app — no indigo/sky AI-slop.
// Dark-intelligence DAG nodes: deep-tint surface + bright border + light text, so
// nodes read as lit panels on the near-black canvas (not light boxes). Aligned to the
// dark ink/mirror/strength tokens (docs/DESIGN.md).
const ROLE_COLORS: Record<string, RoleColors> = {
  system: { bg: '#11171a', border: '#2a343b', text: '#c5cfd4' }, // ink dark
  collector: { bg: '#0f2422', border: '#449a96', text: '#71bbb6' }, // mirror dark
  analyst: { bg: '#16182e', border: '#6060b8', text: '#9aa0ee' }, // moderate dark
  qa: { bg: '#11271b', border: '#2e9e5a', text: '#5fd08a' }, // strong dark
  writer: { bg: '#241f10', border: '#b89830', text: '#d9c06a' }, // weak dark
};

/** Map a logical node to its agent role for coloring. */
const NODE_ROLE: Record<NodeId, string> = {
  discover: 'collector',
  intake: 'system',
  plan: 'system',
  collect: 'collector',
  analyze: 'analyst',
  qa: 'qa',
  route: 'system',
  revise: 'analyst',
  write: 'writer',
  synthesis: 'system',
};

/** Map a logical node to the agent string used in LlmCall.agent. */
const NODE_AGENT: Record<NodeId, string | null> = {
  discover: null, // discovery is a bounded pre-step; it makes no LLM calls
  intake: null,
  plan: null,
  collect: 'collector',
  analyze: 'analyst',
  qa: 'qa',
  route: null,
  revise: 'analyst',
  write: 'writer',
  synthesis: 'synthesis',
};

/** Human-readable labels for each node. */
const NODE_LABELS: Record<NodeId, string> = {
  discover: 'discover',
  intake: 'intake',
  plan: 'plan',
  collect: 'collect',
  analyze: 'analyze',
  qa: 'qa',
  route: 'route',
  revise: 'revise',
  write: 'write',
  synthesis: 'synthesis',
};

/** Plain-language Chinese description of what each node (Agent step) does. */
const NODE_DESC: Record<NodeId, string> = {
  discover: '竞品发现预筛：选出进入分析的竞品',
  intake: '解析输入、建立本次运行',
  plan: '规划要采集的字段与竞品',
  collect: '联网检索 + robots 校验 + 抓取证据',
  analyze: '调用 LLM，把证据归纳成结论（每字段一次）',
  qa: '确定性质检（7 类代码规则，无 LLM、不裁定真值）',
  route: '路由决策：证据足→撰写；不足→打回重做',
  revise: '按质检意见重新采集 / 重新分析（弱→强）',
  write: '把通过质检的结论投影成报告',
  synthesis: '综合全部已验证结论，生成竞品简报',
};

// ---------------------------------------------------------------------------
// Status visual modifiers
// ---------------------------------------------------------------------------

type StatusStyle = {
  opacity: number;
  outline?: string;
  outlineWidth?: number;
  outlineOffset?: number;
};

function statusStyle(status: NodeStatus): StatusStyle {
  switch (status) {
    case 'pending':
      return { opacity: 0.45 };
    case 'running':
      return { opacity: 1, outline: '2px solid #449a96', outlineOffset: 2 }; // mirror-400
    case 'done':
      return { opacity: 1 };
    case 'empty':
      return { opacity: 1, outline: '2px dashed #959ea0', outlineOffset: 2 }; // neutral/ink-400
    case 'flagged':
      return { opacity: 1, outline: '2px solid #b3261e', outlineOffset: 2 }; // destructive
  }
}

function statusCaption(status: NodeStatus): string {
  switch (status) {
    case 'pending':
      return '○ waiting';
    case 'running':
      return '◎ running';
    case 'done':
      return '✓ done';
    case 'empty':
      return '○ 无可综合内容';
    case 'flagged':
      return '✗ flagged';
  }
}

function statusCaptionColor(status: NodeStatus): string {
  switch (status) {
    case 'pending':
      return '#959ea0'; // ink-400
    case 'running':
      return '#71bbb6'; // mirror-300 (dark)
    case 'done':
      return '#5fd08a'; // strong (dark)
    case 'empty':
      return '#959ea0'; // ink-400 (neutral — ran, but no brief)
    case 'flagged':
      return '#e06a60'; // destructive (dark)
  }
}

// ---------------------------------------------------------------------------
// Build reactflow nodes + edges
// ---------------------------------------------------------------------------

interface NodePosition {
  x: number;
  y: number;
}

const NODE_POSITIONS: Record<NodeId, NodePosition> = {
  discover: { x: 300, y: -100 },
  intake: { x: 300, y: 0 },
  plan: { x: 300, y: 100 },
  collect: { x: 300, y: 200 },
  analyze: { x: 300, y: 300 },
  qa: { x: 300, y: 400 },
  route: { x: 300, y: 500 },
  revise: { x: 100, y: 400 },
  write: { x: 500, y: 600 },
  synthesis: { x: 500, y: 700 },
};

/** Per-node aggregate LLM metrics (call count + total tokens), derived from the
 *  run's llm_calls grouped by agent. Latency is intentionally omitted — the
 *  data model has no per-call duration column, so showing one would be fabricated. */
type NodeMetric = { calls: number; tokens: number };

function buildNodes(
  statuses: Record<NodeId, NodeStatus>,
  selectedId: NodeId | null,
  metrics: Record<NodeId, NodeMetric>,
  nodeIds: NodeId[],
): Node[] {
  return nodeIds.map((id) => {
    const role = NODE_ROLE[id];
    const colors = ROLE_COLORS[role];
    const status = statuses[id];
    const ss = statusStyle(status);
    const isSelected = id === selectedId;
    const metric = metrics[id];

    return {
      id,
      type: 'default',
      position: NODE_POSITIONS[id],
      draggable: false,
      selectable: true,
      data: {
        label: (
          <div style={{ textAlign: 'center', minWidth: 70 }}>
            <div
              style={{
                fontWeight: 600,
                fontSize: 12,
                color: colors.text,
              }}
            >
              {NODE_LABELS[id]}
            </div>
            <div
              style={{
                fontSize: 9,
                marginTop: 2,
                color: statusCaptionColor(status),
              }}
              data-testid={`node-status-${id}`}
            >
              {statusCaption(status)}
            </div>
            {metric && metric.calls > 0 && (
              <div
                style={{ fontSize: 9, marginTop: 2, color: '#8b9aa1' }}
                data-testid={`node-metric-${id}`}
                title={`${NODE_AGENT[id]} 智能体共 ${metric.calls} 次 LLM 调用 · ${metric.tokens} tokens`}
              >
                {metric.calls} 次 · {metric.tokens} tok
              </div>
            )}
          </div>
        ),
      },
      style: {
        background: colors.bg,
        border: `2px solid ${isSelected ? '#236a67' : colors.border}`,
        borderRadius: 10,
        padding: '8px 12px',
        opacity: ss.opacity,
        outline: isSelected ? '3px solid #449a96' : (ss.outline ?? 'none'),
        outlineOffset: ss.outlineOffset ?? 0,
        cursor: 'pointer',
      },
    };
  });
}

const STATIC_EDGES: Edge[] = [
  // Discovery pre-step (only lit for Discovery-Mode runs) → intake
  {
    id: 'e-discover-intake',
    source: 'discover',
    target: 'intake',
    type: 'smoothstep',
    label: 'discover',
  },
  // Spine
  { id: 'e-intake-plan', source: 'intake', target: 'plan', type: 'smoothstep' },
  { id: 'e-plan-collect', source: 'plan', target: 'collect', type: 'smoothstep' },
  { id: 'e-collect-analyze', source: 'collect', target: 'analyze', type: 'smoothstep' },
  { id: 'e-analyze-qa', source: 'analyze', target: 'qa', type: 'smoothstep' },
  { id: 'e-qa-route', source: 'qa', target: 'route', type: 'smoothstep' },
  // Success exit
  {
    id: 'e-route-write',
    source: 'route',
    target: 'write',
    type: 'smoothstep',
    label: '✓ pass',
  },
  // Revision fork
  {
    id: 'e-route-revise',
    source: 'route',
    target: 'revise',
    type: 'smoothstep',
    label: '✗ fail',
  },
  // Back-edge: revise → collect (the revision loop)
  {
    id: 'e-revise-collect',
    source: 'revise',
    target: 'collect',
    type: 'smoothstep',
    animated: true,
    label: '↺ revise',
    style: {
      stroke: '#ef4444',
      strokeDasharray: '5 3',
    },
    markerEnd: { type: MarkerType.ArrowClosed, color: '#ef4444' },
    labelStyle: { fill: '#ef4444', fontSize: 10 },
  },
  // Post-write synthesis pass
  { id: 'e-write-synthesis', source: 'write', target: 'synthesis', type: 'smoothstep' },
];

// ---------------------------------------------------------------------------
// LLM call detail panel sub-components
// ---------------------------------------------------------------------------

function parseMessages(promptJson: string): Array<{ role: string; content: string }> {
  try {
    const parsed: unknown = JSON.parse(promptJson);
    if (Array.isArray(parsed)) {
      return parsed as Array<{ role: string; content: string }>;
    }
  } catch {
    // Malformed — fall through.
  }
  return [];
}

interface LlmCallMiniCardProps {
  call: LlmCall;
  index: number;
}

function LlmCallMiniCard({ call, index }: LlmCallMiniCardProps): React.ReactElement {
  const [promptOpen, setPromptOpen] = useState(false);
  const [outputOpen, setOutputOpen] = useState(true);
  const messages = useMemo(() => parseMessages(call.prompt_json), [call.prompt_json]);

  return (
    <div
      className="depth-card rounded-lg p-3 space-y-2 text-xs"
      data-testid={`et-llm-card-${index}`}
    >
      {/* Header */}
      <div className="flex items-center gap-2 text-ink-600">
        <span className="font-mono font-semibold text-ink-800">
          {call.model ?? '(unknown model)'}
        </span>
        {call.total_tokens !== null && call.total_tokens !== undefined && (
          <span className="ml-auto font-mono" data-testid="et-token-total">
            {call.total_tokens} tokens
          </span>
        )}
      </div>

      {/* Token breakdown */}
      {(call.prompt_tokens !== null || call.completion_tokens !== null) && (
        <div className="flex gap-3 text-ink-500" data-testid="et-token-usage">
          <span>Prompt: <strong>{call.prompt_tokens ?? '—'}</strong></span>
          <span>Completion: <strong>{call.completion_tokens ?? '—'}</strong></span>
        </div>
      )}

      {/* Collapsible prompt */}
      <div className="border border-border rounded">
        <button
          type="button"
          onClick={() => setPromptOpen((v) => !v)}
          className="w-full text-left px-2 py-1 text-xs font-semibold text-ink-500 flex justify-between hover:bg-ink-50"
          aria-expanded={promptOpen}
        >
          <span>Prompt ({messages.length} msgs)</span>
          <span className="text-ink-500">{promptOpen ? '▲' : '▼'}</span>
        </button>
        {promptOpen && (
          <div className="px-2 pb-2 space-y-1 mt-1">
            {messages.length === 0 ? (
              <pre className="font-mono text-ink-400 whitespace-pre-wrap">{call.prompt_json}</pre>
            ) : (
              messages.map((msg, i) => (
                <div key={i}>
                  <span className="font-semibold text-mirror-600 uppercase text-[9px]">{msg.role}</span>
                  <pre className="whitespace-pre-wrap font-mono text-ink-700 bg-ink-50 rounded p-1 mt-0.5 overflow-x-auto max-h-32">
                    {typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content, null, 2)}
                  </pre>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* Collapsible output */}
      {call.output_text !== null && call.output_text !== undefined && (
        <div className="border border-border rounded">
          <button
            type="button"
            onClick={() => setOutputOpen((v) => !v)}
            className="w-full text-left px-2 py-1 text-xs font-semibold text-ink-500 flex justify-between hover:bg-ink-50"
            aria-expanded={outputOpen}
          >
            <span>Output</span>
            <span className="text-ink-500">{outputOpen ? '▲' : '▼'}</span>
          </button>
          {outputOpen && (
            <pre
              className="whitespace-pre-wrap font-mono text-ink-700 bg-ink-50 rounded p-2 mt-0 overflow-x-auto max-h-40 mx-2 mb-2"
              data-testid="et-llm-output"
            >
              {call.output_text}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Node detail panel
// ---------------------------------------------------------------------------

interface NodeDetailPanelProps {
  nodeId: NodeId;
  status: NodeStatus;
  llmCalls: LlmCall[];
  onClose: () => void;
}

function NodeDetailPanel({
  nodeId,
  status,
  llmCalls,
  onClose,
}: NodeDetailPanelProps): React.ReactElement {
  const role = NODE_ROLE[nodeId];
  const colors = ROLE_COLORS[role];
  const agentKey = NODE_AGENT[nodeId];

  const nodeCalls = agentKey
    ? llmCalls.filter((c) => c.agent === agentKey)
    : [];

  return (
    <div
      className="w-80 flex-shrink-0 border-l border-border bg-card flex flex-col overflow-hidden"
      data-testid="node-detail-panel"
    >
      {/* Panel header */}
      <div
        className="flex items-center justify-between px-4 py-3 border-b border-border"
        style={{ background: colors.bg }}
      >
        <div>
          <span
            className="text-sm font-bold"
            style={{ color: colors.text }}
          >
            {NODE_LABELS[nodeId]}
          </span>
          <span
            className="ml-2 text-xs"
            style={{ color: statusCaptionColor(status) }}
          >
            {statusCaption(status)}
          </span>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="text-ink-400 hover:text-ink-700 text-lg leading-none"
          aria-label="关闭详情面板"
        >
          ×
        </button>
      </div>

      {/* Agent label */}
      <div className="px-4 py-2 border-b border-border text-xs text-ink-500">
        Agent: <span className="font-semibold">{agentKey ?? 'system'}</span>
      </div>

      {/* LLM calls */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        <div className="text-xs font-semibold uppercase tracking-wide text-ink-400 mb-1">
          LLM Calls ({nodeCalls.length})
        </div>
        {nodeCalls.length === 0 ? (
          <p
            className="text-xs text-ink-400 py-4 text-center"
            data-testid="et-no-llm-calls"
          >
            此节点暂无 LLM 调用
          </p>
        ) : (
          nodeCalls.map((call, i) => (
            <LlmCallMiniCard key={call.id} call={call} index={i} />
          ))
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main view
// ---------------------------------------------------------------------------

export interface ExecutionTraceProps {
  runId: string | null;
}

export function ExecutionTrace({ runId }: ExecutionTraceProps): React.ReactElement {
  const [traceEvents, setTraceEvents] = useState<TraceEvent[]>([]);
  const [sinceSeq, setSinceSeq] = useState(0);
  const [llmCalls, setLlmCalls] = useState<LlmCall[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<NodeId | null>(null);

  // Track the active runId so a slow in-flight fetch for a PREVIOUS run can be
  // dropped once the active run switches (mirror of SchemaMatrix). Synced in an
  // effect — never written during render.
  const latestRunId = useRef(runId);
  useEffect(() => {
    latestRunId.current = runId;
  }, [runId]);

  // On runId change, RESET the incremental trace + sinceSeq cursor + LLM calls +
  // node selection so old events never leak and sinceSeq is correct for the new
  // run. The setState calls live inside an async callback (not the effect body)
  // to satisfy the react-hooks/set-state-in-effect lint rule.
  useEffect(() => {
    async function reset(): Promise<void> {
      setTraceEvents([]);
      setSinceSeq(0);
      setLlmCalls([]);
      setSelectedNodeId(null);
    }
    void reset();
  }, [runId]);

  // Poll trace (incremental)
  usePolling(
    async () => {
      if (!runId) return;
      const id = runId;
      try {
        const res: TraceResponse = await getTrace(id, sinceSeq);
        if (id !== latestRunId.current) return;
        if (res.events.length > 0) {
          // Dedup by id (mergeTraceEvents) — StrictMode double-invoke + overlapping
          // polls can re-deliver an event; a raw append duplicated events (harmless
          // for the fixed-id DAG nodes here, but kept consistent with Observability
          // and App, which render per-event keyed lists).
          setTraceEvents((prev) => mergeTraceEvents(prev, res.events));
          setSinceSeq(res.max_seq);
        }
      } catch {
        // Degrade silently — keep last good state
      }
    },
    runId !== null,
    2000,
  );

  // Poll LLM calls (full refresh)
  usePolling(
    async () => {
      if (!runId) return;
      const id = runId;
      try {
        const res: LlmCallsResponse = await getLlmCalls(id);
        if (id !== latestRunId.current) return;
        setLlmCalls(res.calls);
      } catch {
        // Degrade silently
      }
    },
    runId !== null,
    2000,
  );

  const statuses = useMemo(
    () => deriveNodeStatus(traceEvents),
    [traceEvents],
  );

  // The `discover` pre-step node is shown ONLY for Discovery-Mode runs (a trace
  // carrying a discovery event). A Directed-Mode run keeps the original 9-node
  // topology unchanged — no greyed-out discover node.
  const discoveryPresent = useMemo(
    () =>
      traceEvents.some(
        (e) =>
          e.event_type === 'discovery_started' ||
          e.event_type === 'competitors_discovered' ||
          e.event_type === 'discovery_empty',
      ),
    [traceEvents],
  );
  const renderedNodeIds = useMemo(
    () => (discoveryPresent ? ALL_NODE_IDS : ALL_NODE_IDS.filter((id) => id !== 'discover')),
    [discoveryPresent],
  );
  const edges = useMemo(
    () =>
      discoveryPresent ? STATIC_EDGES : STATIC_EDGES.filter((e) => e.id !== 'e-discover-intake'),
    [discoveryPresent],
  );

  // Per-agent aggregate LLM metrics (calls + tokens) from llm_calls. The trace
  // attributes calls to an AGENT, not to a graph node, and two nodes can share an
  // agent (analyze + revise → 'analyst'). To avoid double-presenting the same
  // agent total on multiple node faces (which would misread as per-node counts),
  // attribute each agent's total to ONLY its canonical (first-in-topology) node;
  // sibling nodes get no badge. Real data only — no latency (no per-call duration).
  const nodeMetrics = useMemo(() => {
    const m = {} as Record<NodeId, NodeMetric>;
    const agentClaimed = new Set<string>();
    for (const id of ALL_NODE_IDS) {
      const agentKey = NODE_AGENT[id];
      if (!agentKey || agentClaimed.has(agentKey)) {
        m[id] = { calls: 0, tokens: 0 };
        continue;
      }
      agentClaimed.add(agentKey);
      const calls = llmCalls.filter((c) => c.agent === agentKey);
      m[id] = {
        calls: calls.length,
        tokens: calls.reduce((s, c) => s + (c.total_tokens ?? 0), 0),
      };
    }
    return m;
  }, [llmCalls]);

  // Build nodes immutably on each status/selection/metrics change
  const nodes = useMemo(
    () => buildNodes(statuses, selectedNodeId, nodeMetrics, renderedNodeIds),
    [statuses, selectedNodeId, nodeMetrics, renderedNodeIds],
  );

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      setSelectedNodeId((prev) => (prev === node.id ? null : (node.id as NodeId)));
    },
    [],
  );

  const selectedStatus = selectedNodeId ? statuses[selectedNodeId] : 'pending';

  return (
    <div className="flex h-full" data-testid="execution-trace-root">
      {/* ---- Left: DAG + accessible node list ---- */}
      <div className="flex-1 flex flex-col min-w-0 relative">
        {/* No-run overlay */}
        {!runId && (
          <div
            className="absolute inset-x-0 top-0 z-10 text-center py-2 bg-amber-50 border-b border-amber-200 text-xs text-amber-700"
            data-testid="no-run-banner"
          >
            Start a run to see the execution trace.
          </div>
        )}

        {/* LangSmith link — top right (only shown when VITE_LANGSMITH_URL is configured) */}
        <div className="absolute top-2 right-2 z-10 flex items-center gap-1">
          {import.meta.env.VITE_LANGSMITH_URL ? (
            <a
              href={import.meta.env.VITE_LANGSMITH_URL as string}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-ink-400 hover:text-mirror-600 underline underline-offset-2"
              data-testid="langsmith-link"
            >
              在 LangSmith 中查看 ↗
            </a>
          ) : (
            <span
              className="text-xs text-ink-400"
              data-testid="langsmith-link"
              title="设置 VITE_LANGSMITH_URL 环境变量后可链接到对应项目"
            >
              可接入 LangSmith（离线 demo 未导出 trace）
            </span>
          )}
          <span className="text-[9px] text-ink-500">(外部 trace 控制台)</span>
        </div>

        {/* ReactFlow DAG */}
        <div
          className="flex-1"
          style={{ width: '100%', height: '100%', minHeight: 520 }}
          data-testid="dag-container"
        >
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodeClick={onNodeClick}
            fitView
            fitViewOptions={{ padding: 0.2 }}
            nodesDraggable={false}
            nodesConnectable={false}
            zoomOnScroll={true}
            panOnDrag={true}
          >
            <Background gap={20} color="#1b2329" />
          </ReactFlow>
        </div>

        {/* Plain-language legend — explains what the DAG shows so non-engineers aren't lost */}
        <div className="border-t border-border bg-card px-4 py-2 text-[11px] leading-relaxed text-ink-500" data-testid="trace-legend">
          <span className="font-medium text-ink-700">怎么看这张图：</span>
          每个节点是一个 Agent 步骤（点击查看其输入 / 输出）。主链路：
          <span className="text-ink-600"> 采集 → 分析 → 质检 → 路由 →（证据不足则打回重做）→ 撰写 → 综合</span>。
          <span className="ml-2">状态：<span style={{ color: '#71bbb6' }}>◎ 运行中</span> · <span style={{ color: '#5fd08a' }}>✓ 完成</span> · <span style={{ color: '#e06a60' }}>✗ 被质检打回</span> · ○ 待执行</span>。
          <span className="ml-2"><span style={{ color: '#e06a60' }}>红色虚线</span> = 质检打回后的「重做」回路（弱证据 → 重新取证 → 升级）。</span>
        </div>

        {/* Accessible node list (testable click handle + a11y) */}
        <div className="border-t border-border bg-card px-4 py-2 flex flex-wrap gap-2" data-testid="node-button-list">
          {renderedNodeIds.map((id) => {
            const role = NODE_ROLE[id];
            const colors = ROLE_COLORS[role];
            const status = statuses[id];
            const isSelected = selectedNodeId === id;
            return (
              <button
                key={id}
                type="button"
                data-testid={`node-btn-${id}`}
                onClick={() => setSelectedNodeId((prev) => (prev === id ? null : id))}
                title={NODE_DESC[id]}
                className="px-3 py-1 rounded text-xs font-medium border transition-colors"
                style={{
                  background: isSelected ? colors.border : colors.bg,
                  color: isSelected ? '#fff' : colors.text,
                  borderColor: colors.border,
                  opacity: status === 'pending' ? 0.6 : 1,
                }}
                aria-pressed={isSelected}
              >
                {NODE_LABELS[id]}
                <span
                  className="ml-1"
                  style={{ color: isSelected ? 'rgba(255,255,255,0.8)' : statusCaptionColor(status) }}
                >
                  {statusCaption(status)}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* ---- Right: node detail panel ---- */}
      {selectedNodeId !== null && (
        <NodeDetailPanel
          nodeId={selectedNodeId}
          status={selectedStatus}
          llmCalls={llmCalls}
          onClose={() => setSelectedNodeId(null)}
        />
      )}
    </div>
  );
}

export default ExecutionTrace;
