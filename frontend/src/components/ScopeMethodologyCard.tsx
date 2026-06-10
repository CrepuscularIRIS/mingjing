/**
 * ScopeMethodologyCard — the report's "范围与方法 (Scope & Methodology)" section.
 *
 * Professional CI reports disclose WHAT was analyzed, from WHICH sources, what
 * was EXCLUDED (and why), and HOW conclusions were gated — that transparency is
 * the credibility foundation (ICD-203 / professional-CI practice). The data is
 * a pure deterministic backend projection (`scope.py`, no LLM); this card only
 * renders it. Hidden entirely when the field is absent (older API).
 */

import type { ScopeMethodology } from '../api/types';
import { getSchemaFieldLabel } from '../lib/schemaFieldMeta';

const MODE_LABEL: Record<ScopeMethodology['mode'], string> = {
  directed: '指定竞品模式',
  discovery: '自动发现模式',
};

/** Stable display order for source_mode counts (real provenance first). */
const SOURCE_MODE_ORDER = ['LIVE', 'CACHED', 'INGESTED', 'SNIPPET', 'SIMULATED'];

const SOURCE_MODE_CN: Record<string, string> = {
  LIVE: '实时',
  CACHED: '缓存',
  INGESTED: '真实导入',
  SNIPPET: '快照',
  SIMULATED: '模拟',
};

interface ScopeMethodologyCardProps {
  scope: ScopeMethodology | null | undefined;
}

export function ScopeMethodologyCard({
  scope,
}: ScopeMethodologyCardProps): React.ReactElement | null {
  if (!scope) return null;

  // Known modes in canonical order, then any UNKNOWN modes appended verbatim —
  // a future source_mode must never be silently dropped from the disclosure.
  const knownModes = SOURCE_MODE_ORDER.filter((m) => scope.source_stats.by_source_mode[m]);
  const extraModes = Object.keys(scope.source_stats.by_source_mode).filter(
    (m) => !SOURCE_MODE_ORDER.includes(m) && scope.source_stats.by_source_mode[m],
  );
  const modeEntries = [...knownModes, ...extraModes]
    .map((m) => `${SOURCE_MODE_CN[m] ?? m} ${scope.source_stats.by_source_mode[m]}`)
    .join(' · ');

  return (
    <section
      data-testid="scope-methodology"
      className="rounded-lg border border-ink-200 bg-card shadow-card p-4 space-y-3"
    >
      <header className="flex items-baseline justify-between gap-2 flex-wrap">
        <h3 className="text-sm font-semibold text-ink-900">
          范围与方法 <span className="text-ink-400 font-normal">Scope &amp; Methodology</span>
        </h3>
        <span
          className="text-[11px] text-ink-500"
          title="本节由后端对已持久化数据做确定性投影生成（scope.py），无 LLM 参与。"
        >
          确定性生成 · 非 LLM 文案
        </span>
      </header>

      {/* 纳入范围 */}
      <div className="text-xs text-ink-700 leading-relaxed">
        <span className="font-semibold text-ink-800">纳入范围：</span>
        <span className="mr-1 inline-block rounded bg-mirror-50 text-mirror-700 px-1.5 py-0.5 text-[10px] font-medium align-baseline">
          {MODE_LABEL[scope.mode]}
        </span>
        {scope.competitors.map((c) => (
          <span
            key={c.name}
            className="mr-1 inline-block rounded border border-ink-200 bg-ink-50 px-1.5 py-0.5 text-[11px]"
            title={c.reason}
          >
            {c.name}
            <span className="text-ink-400"> · {c.reason}</span>
          </span>
        ))}
      </div>

      {/* 数据源构成 */}
      <div className="text-xs text-ink-700 leading-relaxed" data-testid="scope-source-stats">
        <span className="font-semibold text-ink-800">数据源：</span>
        共 {scope.source_stats.total} 个来源（{modeEntries}）·{' '}
        <span title="按独立可注册域名去重，且模拟数据不计入（与 3 档打分器同口径）。">
          独立信源域 {scope.source_stats.independent_domains} 个
        </span>{' '}
        · 提议 {scope.admission.proposed_claims} 条 → 准入 {scope.admission.admitted_claims} 条
      </div>

      {/* 未纳入项及原因 — the honesty half of the section. */}
      {(scope.excluded.withheld_count > 0 ||
        scope.excluded.uncovered_fields.length > 0 ||
        scope.excluded.disclosures.length > 0) && (
        <div className="text-xs text-ink-700 leading-relaxed" data-testid="scope-excluded">
          <span className="font-semibold text-ink-800">未纳入项及原因：</span>
          {scope.excluded.withheld_count > 0 && (
            <span>
              {scope.excluded.withheld_count} 条结论被确定性 QA 留存（
              {scope.excluded.issue_codes.map((code) => (
                <span
                  key={code}
                  className="mx-0.5 inline-block rounded bg-weak-bg text-weak-text border border-weak-border px-1 text-[10px] font-mono"
                >
                  {code}
                </span>
              ))}
              ）；
            </span>
          )}
          {scope.excluded.uncovered_fields.length > 0 && (
            <span>
              未覆盖字段：
              {scope.excluded.uncovered_fields.map((f) => getSchemaFieldLabel(f)).join('、')}
              （证据不足，诚实留空）。
            </span>
          )}
          {scope.excluded.disclosures.map((d) => (
            <span key={d} className="block text-ink-500 mt-0.5">
              ◦ {d}
            </span>
          ))}
        </div>
      )}

      {/* 方法 */}
      <ul className="text-[11px] text-ink-500 leading-relaxed list-disc pl-4 space-y-0.5">
        {scope.method.statements.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ul>
    </section>
  );
}

export default ScopeMethodologyCard;
