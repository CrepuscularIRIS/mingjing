/**
 * Observability — Hero View 3.
 *
 * "Show your work" surface: lists the agents/nodes derived from trace events
 * and LLM calls. Clicking an agent opens a detail panel with:
 *   1. Its trace events (from /trace, filtered to that agent/node), rendered
 *      as human-readable lines via the trace.ts helpers.
 *   2. Its LLM call(s) (from /llm_calls): collapsible prompt/messages, the
 *      model output, and the token usage.
 *   3. A per-agent token bar chart (recharts BarChart) showing prompt vs
 *      completion tokens side-by-side for each agent.
 *
 * Polls /trace and /llm_calls every 2s via usePolling so it fills live.
 * Degrades gracefully when a run has trace events but zero LLM calls (the
 * offline injected smoke runs). Secrets are shown with a redaction note.
 */

import { useMemo, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { getLlmCalls, getTrace } from '../api/client';
import type { LlmCall, LlmCallsResponse, TraceEvent, TraceResponse } from '../api/types';
import { usePolling } from '../hooks/usePolling';
import {
  describeEvent,
  humanizeEventType,
  mergeTraceEvents,
  roleStyle,
} from '../lib/trace';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AgentStats {
  /** Agent or node name (used as the display label). */
  name: string;
  /** Trace events attributed to this agent. */
  events: TraceEvent[];
  /** LLM calls attributed to this agent. */
  calls: LlmCall[];
}

interface TokenChartDatum {
  agent: string;
  prompt: number;
  completion: number;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Parse the raw prompt_json string defensively. */
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

/** Derive the ordered unique agent/node keys from trace events + llm calls. */
function deriveAgents(
  events: TraceEvent[],
  calls: LlmCall[],
): AgentStats[] {
  const order: string[] = [];
  const map = new Map<string, AgentStats>();

  function ensureAgent(name: string): AgentStats {
    if (!map.has(name)) {
      order.push(name);
      map.set(name, { name, events: [], calls: [] });
    }
    return map.get(name)!;
  }

  for (const ev of events) {
    const key = ev.agent ?? ev.node ?? 'system';
    ensureAgent(key).events.push(ev);
  }
  for (const call of calls) {
    const key = call.agent ?? 'system';
    ensureAgent(key).calls.push(call);
  }

  return order.map((k) => map.get(k)!);
}

/** Build recharts data: sum tokens per agent. */
function buildChartData(agents: AgentStats[]): TokenChartDatum[] {
  return agents
    .filter((a) => a.calls.length > 0)
    .map((a) => ({
      agent: a.name,
      prompt: a.calls.reduce((s, c) => s + (c.prompt_tokens ?? 0), 0),
      completion: a.calls.reduce((s, c) => s + (c.completion_tokens ?? 0), 0),
    }));
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface CollapsibleProps {
  label: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}

function Collapsible({ label, children, defaultOpen = false }: CollapsibleProps): React.ReactElement {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border border-ink-200 rounded">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full text-left px-3 py-2 text-xs font-semibold text-ink-600 flex items-center justify-between hover:bg-ink-50"
        aria-expanded={open}
      >
        <span>{label}</span>
        <span className="text-ink-400">{open ? '▲' : '▼'}</span>
      </button>
      {open && <div className="px-3 pb-3">{children}</div>}
    </div>
  );
}

interface LlmCallCardProps {
  call: LlmCall;
  index: number;
}

function LlmCallCard({ call, index }: LlmCallCardProps): React.ReactElement {
  const messages = useMemo(() => parseMessages(call.prompt_json), [call.prompt_json]);

  return (
    <div
      className="depth-card rounded-lg p-3 space-y-2"
      data-testid={`llm-call-card-${index}`}
    >
      <div className="flex items-center gap-2 text-xs text-ink-500">
        <span className="font-mono font-semibold text-ink-700">
          {call.model ?? '(unknown model)'}
        </span>
        {call.total_tokens !== null && call.total_tokens !== undefined && (
          <span
            className="ml-auto font-mono"
            data-testid="token-total"
          >
            {call.total_tokens} tokens
          </span>
        )}
      </div>

      {/* Token usage row */}
      {(call.prompt_tokens !== null || call.completion_tokens !== null) && (
        <div className="flex gap-4 text-xs text-ink-500" data-testid="token-usage">
          <span>
            Prompt: <strong>{call.prompt_tokens ?? '—'}</strong>
          </span>
          <span>
            Completion: <strong>{call.completion_tokens ?? '—'}</strong>
          </span>
        </div>
      )}

      {/* Collapsible prompt/messages */}
      <Collapsible label={`Prompt (${messages.length} messages)`}>
        <div className="space-y-2 mt-2">
          {messages.length === 0 ? (
            <p className="text-xs text-ink-400 font-mono">{call.prompt_json}</p>
          ) : (
            messages.map((msg, i) => (
              <div key={i} className="text-xs">
                <span className="font-semibold text-mirror-600 uppercase text-[10px]">
                  {msg.role}
                </span>
                <pre className="whitespace-pre-wrap font-mono text-ink-700 mt-0.5 bg-ink-50 rounded p-2 overflow-x-auto max-h-40">
                  {typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content, null, 2)}
                </pre>
              </div>
            ))
          )}
        </div>
      </Collapsible>

      {/* Output text */}
      {call.output_text !== null && call.output_text !== undefined && (
        <Collapsible label="Output" defaultOpen>
          <pre
            className="whitespace-pre-wrap font-mono text-xs text-ink-700 mt-2 bg-ink-50 rounded p-2 overflow-x-auto max-h-40"
            data-testid="llm-output"
          >
            {call.output_text}
          </pre>
        </Collapsible>
      )}
    </div>
  );
}

interface AgentDetailProps {
  agent: AgentStats;
}

/**
 * Agents that are deterministic by design and NEVER call the LLM. Showing
 * "0 LLM calls" for these is correct, not a failure — only `analyst` and
 * `synthesis` invoke the model. A deterministic gate/collector/router is exactly
 * what keeps hallucination out of the trust path.
 */
const DETERMINISTIC_ROLE: Record<string, string> = {
  intake: '解析输入、建立任务',
  plan: '规划采集计划',
  collector: '联网检索与抓取',
  qa: '确定性证据质检',
  route: '路由决策（通过 / 打回）',
  // 补证调度是审计链最关键的一环——缺了这条,revise 节点会落入"尚未执行"
  // 的兜底文案,与 trace 里真实存在的 revise_start/done 自相矛盾。
  revise: '补证调度（把被打回的结论派回采集 / 分析重做）',
  writer: '把通过质检的结论投影成报告',
  discover: '竞品发现预筛',
};

function AgentDetail({ agent }: AgentDetailProps): React.ReactElement {
  return (
    <div className="space-y-4" data-testid={`agent-detail-${agent.name}`}>
      {/* Trace events */}
      <section>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-400 mb-2">
          Trace Events ({agent.events.length})
        </h3>
        {agent.events.length === 0 ? (
          <p className="text-xs text-ink-400">No trace events for this agent.</p>
        ) : (
          <ol className="space-y-1">
            {agent.events.map((ev) => {
              const style = roleStyle(ev.agent);
              return (
                <li
                  key={ev.id}
                  className="flex items-start gap-2 text-xs"
                  data-testid={`trace-event-${ev.id}`}
                >
                  <span
                    className={[
                      'inline-block w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0',
                      style.dot,
                    ].join(' ')}
                    aria-hidden="true"
                  />
                  <span className="text-ink-700">
                    {humanizeEventType(ev.event_type)}
                  </span>
                  <span className="ml-auto text-ink-400 font-mono">
                    {describeEvent(ev)}
                  </span>
                </li>
              );
            })}
          </ol>
        )}
      </section>

      {/* LLM calls */}
      <section>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-400 mb-2">
          LLM Calls ({agent.calls.length})
        </h3>
        <p className="text-[10px] text-ink-400 mb-2">
          Prompts 写入前会将已配置的 API key 原值替换为占位符（针对当前 env 中的密钥值，非通用模式匹配）。
        </p>
        {agent.calls.length === 0 ? (
          DETERMINISTIC_ROLE[agent.name] !== undefined ? (
            <p className="text-xs text-ink-500" data-testid="no-llm-calls">
              该 Agent 是<span className="font-medium text-ink-700">确定性流程</span>，按设计<span className="font-medium text-ink-700">不调用 LLM</span>——
              它负责{DETERMINISTIC_ROLE[agent.name]}，因此 0 次调用是正常的（这正是把幻觉挡在信任链之外的关键）。
            </p>
          ) : (
            <p className="text-xs text-ink-400" data-testid="no-llm-calls">
              暂无 LLM 调用（该 Agent 尚未在本次运行中执行）。
            </p>
          )
        ) : (
          <div className="space-y-2">
            {agent.calls.map((call, i) => (
              <LlmCallCard key={call.id} call={call} index={i} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Token chart
// ---------------------------------------------------------------------------

interface TokenChartProps {
  data: TokenChartDatum[];
}

function TokenChart({ data }: TokenChartProps): React.ReactElement | null {
  if (data.length === 0) return null;
  return (
    <div data-testid="token-chart">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-400 mb-2">
        Token Usage by Agent
      </h3>
      <ResponsiveContainer width="100%" height={160}>
        <BarChart data={data} margin={{ top: 4, right: 8, left: -20, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#dce0e1" />
          <XAxis dataKey="agent" tick={{ fontSize: 10 }} />
          <YAxis tick={{ fontSize: 10 }} />
          <Tooltip />
          <Legend iconSize={10} wrapperStyle={{ fontSize: 10 }} />
          <Bar dataKey="prompt" name="Prompt" fill="#236a67" />
          <Bar dataKey="completion" name="Completion" fill="#2e9e5a" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main view
// ---------------------------------------------------------------------------

export interface ObservabilityProps {
  runId: string | null;
}

export function Observability({ runId }: ObservabilityProps): React.ReactElement {
  const [traceEvents, setTraceEvents] = useState<TraceEvent[]>([]);
  const [sinceSeq, setSinceSeq] = useState(0);
  const [llmCalls, setLlmCalls] = useState<LlmCall[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [pollingError, setPollingError] = useState(false);

  // Poll trace events every 2s (incremental).
  usePolling(
    async () => {
      if (!runId) return;
      const res: TraceResponse = await getTrace(runId, sinceSeq);
      if (res.events.length > 0) {
        // Dedup by id (mergeTraceEvents) — StrictMode double-invokes the polling
        // effect on mount and overlapping polls can re-deliver an event, so a raw
        // append produced duplicate ev.id → duplicate React keys in the per-agent
        // trace-event list. Mirrors how App.tsx merges trace events.
        setTraceEvents((prev) => mergeTraceEvents(prev, res.events));
        setSinceSeq(res.max_seq);
      }
      setPollingError(false);
    },
    runId !== null,
    2000,
    () => setPollingError(true),
  );

  // Poll LLM calls every 2s (full refresh — the list only grows).
  usePolling(
    async () => {
      if (!runId) return;
      const res: LlmCallsResponse = await getLlmCalls(runId);
      setLlmCalls(res.calls);
      setPollingError(false);
    },
    runId !== null,
    2000,
    () => setPollingError(true),
  );

  const agents = useMemo(
    () => deriveAgents(traceEvents, llmCalls),
    [traceEvents, llmCalls],
  );

  const chartData = useMemo(() => buildChartData(agents), [agents]);

  const activeAgent = useMemo(
    () => agents.find((a) => a.name === selectedAgent) ?? null,
    [agents, selectedAgent],
  );

  // ---- Empty state: no run -----------------------------------------------
  if (!runId) {
    return (
      <div className="text-ink-400 text-lg py-20 text-center">
        Start a run to observe its internals.
      </div>
    );
  }

  return (
    <div className="flex gap-4 h-full">
      {/* ---- Left: agent list + token chart ---- */}
      <div className="w-64 flex-shrink-0 space-y-4 overflow-y-auto">
        {pollingError && (
          <div className="rounded bg-amber-50 border border-amber-200 px-3 py-1.5 text-xs text-amber-700">
            Connection error, retrying…
          </div>
        )}

        <div>
          <h2 className="text-xs font-semibold uppercase tracking-wide text-ink-400 mb-2">
            Agents / Nodes
          </h2>
          {agents.length === 0 ? (
            <p className="text-sm text-ink-400 py-4 text-center" data-testid="no-agents">
              No activity yet — waiting for the run to start.
            </p>
          ) : (
            <ul className="space-y-1" data-testid="agent-list">
              {agents.map((a) => {
                const style = roleStyle(a.name);
                const isActive = a.name === selectedAgent;
                return (
                  <li key={a.name}>
                    <button
                      type="button"
                      data-testid={`agent-btn-${a.name}`}
                      onClick={() =>
                        setSelectedAgent(isActive ? null : a.name)
                      }
                      className={[
                        'w-full text-left px-3 py-2 rounded text-sm font-medium transition-colors flex items-center gap-2',
                        isActive
                          ? 'bg-mirror-50 text-mirror-800 border border-mirror-200'
                          : 'text-ink-700 hover:bg-ink-100',
                      ].join(' ')}
                    >
                      <span
                        className={[
                          'inline-block w-2 h-2 rounded-full flex-shrink-0',
                          style.dot,
                        ].join(' ')}
                        aria-hidden="true"
                      />
                      <span className="truncate">{a.name}</span>
                      <span className="ml-auto text-xs text-ink-400 font-mono">
                        {a.calls.length > 0 ? `${a.calls.length} call${a.calls.length > 1 ? 's' : ''}` : ''}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* Token chart — only when there are LLM calls */}
        <TokenChart data={chartData} />
      </div>

      {/* ---- Right: agent detail panel ---- */}
      <div className="flex-1 overflow-y-auto">
        {activeAgent === null ? (
          <div
            className="text-ink-400 text-sm py-20 text-center"
            data-testid="select-agent-prompt"
          >
            Click an agent on the left to inspect its prompts, outputs, and trace events.
          </div>
        ) : (
          <AgentDetail agent={activeAgent} />
        )}
      </div>
    </div>
  );
}

export default Observability;
