/**
 * SourceTypeBreakdown — the per-cell source-TYPE axis for the Schema matrix.
 *
 * Renders an advisory tally of WHICH source types back a claim (e.g. 🏛官方·2
 * 📰新闻·1), authoritative types first. This is the matrix's third axis alongside
 * the strength Badge and the source count — it shows the *kind* of evidence, not
 * just how much.
 *
 * PURE display. The counts come from the report's read-side `source_types` tally
 * and never influence scoring/QA. Renders nothing for an empty/absent tally.
 */
import type { ReactElement } from 'react';

import { orderSourceTypes, sourceTypeMeta } from './sourceTypeMeta';

interface Props {
  /** {source_type: count} for a claim's cited sources. */
  counts?: Record<string, number>;
  competitor?: string;
  field?: string;
}

export function SourceTypeBreakdown({ counts, competitor, field }: Props): ReactElement | null {
  if (!counts || Object.keys(counts).length === 0) return null;
  const types = orderSourceTypes(Object.keys(counts));
  const testid =
    competitor && field ? `cell-srctypes-${competitor}-${field}` : 'cell-srctypes';
  return (
    <div data-testid={testid} className="mt-1 flex flex-wrap items-center gap-1">
      {types.map((t) => {
        const meta = sourceTypeMeta(t);
        return (
          <span
            key={t}
            data-testid={`srctype-${t}`}
            title={`${meta.label}来源 ${counts[t]} 条${meta.authoritative ? '（权威类型）' : '（参考类型，非权威）'}`}
            className={[
              'inline-flex items-center gap-0.5 px-1 py-0.5 rounded text-[9px] font-medium border',
              meta.className,
            ].join(' ')}
          >
            {meta.emoji} {meta.label}·{counts[t]}
          </span>
        );
      })}
    </div>
  );
}

export default SourceTypeBreakdown;
