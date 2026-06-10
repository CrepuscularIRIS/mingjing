/**
 * WithheldDisclosure — the self-explaining empty/partial run panel.
 *
 * When a run gathers sources but admits few or zero claims, this turns a blank
 * page into an honest account of WHY: how many sources were collected, how many
 * thin SPA shells were dropped, how many fields produced no claim, and how many
 * claims the deterministic QA gate withheld (with the issue codes). This is the
 * moat made visible — the system refusing to fabricate, shown rather than hidden.
 *
 * Renders nothing on a clean run (no skips, no withholds) so a healthy report is
 * never cluttered.
 */

import type { TraceEvent, WithheldItem } from '../api/types';
import { issueLabel, summarizeWithheld } from '../lib/withheld';

export interface WithheldDisclosureProps {
  events: TraceEvent[];
  withheld: WithheldItem[];
}

export function WithheldDisclosure({
  events,
  withheld,
}: WithheldDisclosureProps): React.ReactElement | null {
  const s = summarizeWithheld(events, withheld);

  const hasSomethingToExplain =
    s.sourcesSkipped > 0 || s.claimsSkipped > 0 || s.claimsWithheld > 0;
  if (!hasSomethingToExplain) return null;

  const issueEntries = Object.entries(s.issueTally).sort((a, b) => b[1] - a[1]);

  return (
    <div
      className="rounded-lg border border-ink-200 bg-ink-100 px-4 py-3 text-sm text-ink-700 space-y-2"
      data-testid="withheld-disclosure"
    >
      <p className="font-medium text-ink-800">为什么这里结论不多？（证据门禁如实披露）</p>
      <p>
        {(s.sourcesCollected > 0 || s.sourcesSkipped > 0) && (
          <>
            本次运行采集 <strong>{s.sourcesCollected}</strong> 个来源
            {s.sourcesSkipped > 0 && (
              <>
                （其中 <strong>{s.sourcesSkipped}</strong> 个因内容过薄被跳过）
              </>
            )}
            。
          </>
        )}
        {s.claimsSkipped > 0 && (
          <>
            有 <strong>{s.claimsSkipped}</strong> 个字段未能生成可用结论。
          </>
        )}
        {s.claimsWithheld > 0 && (
          <>
            <strong>{s.claimsWithheld}</strong> 条结论未通过证据门禁，已如实保留为草稿而非写入报告。
          </>
        )}
      </p>
      {issueEntries.length > 0 && (
        <ul className="space-y-1">
          {issueEntries.map(([code, count]) => (
            <li key={code} className="flex items-baseline gap-2">
              <span className="inline-block rounded bg-ink-200 px-1.5 py-0.5 text-xs font-mono text-ink-600">
                ×{count}
              </span>
              <span>{issueLabel(code)}</span>
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-ink-500">确定性 QA 门禁 · 无证据不准入 · LLM 不裁定真值</p>
    </div>
  );
}
