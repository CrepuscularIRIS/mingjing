/**
 * DiscoveredCompetitors — the Discovery-Mode result panel.
 *
 * When a run was created WITHOUT competitors (Discovery Mode), the backend runs a
 * bounded discovery pre-step and emits `discovery_started` -> `competitors_discovered`
 * (or `discovery_empty`). This panel renders the outcome from the polled trace
 * stream so the judge SEES the system turning a category into a competitor set —
 * the "give me a category, I'll find the players" story made visible.
 *
 * PURE display: derives everything from the `events` prop (no extra fetch). It
 * renders nothing for a Directed-Mode run (no discovery events present).
 */
import type { ReactElement } from 'react';

import type { TraceEvent } from '../api/types';
import { parseEventPayload } from '../lib/trace';

interface Candidate {
  name: string;
  source_count?: number;
  has_official?: boolean;
}

interface Props {
  events: TraceEvent[];
}

function latestOfType(events: TraceEvent[], type: string): TraceEvent | undefined {
  // Events arrive oldest-first (ascending id); walk from the end for the latest.
  for (let i = events.length - 1; i >= 0; i -= 1) {
    if (events[i].event_type === type) return events[i];
  }
  return undefined;
}

export function DiscoveredCompetitors({ events }: Props): ReactElement | null {
  const started = latestOfType(events, 'discovery_started');
  const done = latestOfType(events, 'competitors_discovered');
  const empty = latestOfType(events, 'discovery_empty');

  // Directed Mode (no discovery at all) -> render nothing.
  if (!started && !done && !empty) return null;

  // In-progress: started but no terminal discovery event yet.
  if (started && !done && !empty) {
    const p = parseEventPayload(started);
    const category = (p['category'] as string | undefined) ?? '';
    return (
      <div
        data-testid="discovered-competitors"
        className="p-4 border-b border-ink-100 space-y-2"
      >
        <h2 className="text-sm font-semibold text-ink-700">自动发现竞品</h2>
        <p className="text-xs text-ink-500">
          正在从「{category || '该品类'}」发现候选竞品…
        </p>
      </div>
    );
  }

  if (empty && !done) {
    return (
      <div
        data-testid="discovered-competitors"
        className="p-4 border-b border-ink-100 space-y-2"
      >
        <h2 className="text-sm font-semibold text-ink-700">自动发现竞品</h2>
        <p className="text-xs text-ink-500">未发现可分析的竞品（已诚实终止）。</p>
      </div>
    );
  }

  const payload = done ? parseEventPayload(done) : {};
  const selected = Array.isArray(payload['selected'])
    ? (payload['selected'] as string[])
    : [];
  const candidates = Array.isArray(payload['candidates'])
    ? (payload['candidates'] as Candidate[])
    : [];
  const selectedSet = new Set(selected.map((s) => s.toLowerCase()));

  return (
    <div
      data-testid="discovered-competitors"
      className="p-4 border-b border-ink-100 space-y-2.5"
    >
      <h2 className="text-sm font-semibold text-ink-700">自动发现竞品</h2>
      <div className="flex flex-wrap gap-1.5">
        {selected.map((name) => (
          <span
            key={name}
            data-testid="discovered-chip"
            className="text-xs font-medium px-2 py-0.5 rounded-full bg-mirror-50 text-mirror-700 ring-1 ring-mirror-100"
          >
            {name}
          </span>
        ))}
      </div>
      {candidates.length > 0 && (
        <ul className="space-y-1 pt-0.5">
          {candidates.slice(0, 8).map((c) => {
            const chosen = selectedSet.has(c.name.toLowerCase());
            return (
              <li
                key={c.name}
                className={[
                  'flex items-center justify-between text-[11px]',
                  chosen ? 'text-ink-600' : 'text-ink-400',
                ].join(' ')}
              >
                <span className="inline-flex items-center gap-1">
                  {chosen ? '✓' : '·'} {c.name}
                  {c.has_official && (
                    <span className="text-mirror-500" title="发现官方页面">
                      ◆
                    </span>
                  )}
                </span>
                <span
                  className="tabular-nums"
                  title="发现阶段的提及/信号域名（用于排序候选竞品），非已通过 QA 采信的证据来源。"
                >
                  {c.source_count ?? 0} 来源
                </span>
              </li>
            );
          })}
        </ul>
      )}
      <p className="text-[11px] leading-snug text-ink-400">
        按「独立来源数 + 官方页面」排序选出；这些竞品进入标准证据闭环分析（无可采证据时如实留空）。
      </p>
    </div>
  );
}

export default DiscoveredCompetitors;
