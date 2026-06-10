/**
 * ContradictionCard — Surfaces an evidence conflict between two sources.
 *
 * DESIGN RATIONALE: When two sources disagree, hiding the conflict would be
 * dishonest. This card makes it explicit:
 *   1. A "证据冲突" header so the reader knows this is a flagged disagreement.
 *   2. The TWO conflicting source chips side by side (each with an optional
 *      Admiralty grade so the reader can weigh reliability).
 *   3. An explicit confidence delta — "置信度由 {from} 降至 {to}" — making clear
 *      that the conflict DEMOTED our confidence (never a silent number change).
 */

import { admiraltyGloss } from './admiralty';

export interface ConflictSource {
  /** Display label (e.g. domain or source name). */
  label: string;
  /** Optional canonical URL for the source. */
  url?: string;
  /** Optional Admiralty grade (e.g. "B2"). */
  grade?: string;
}

export interface ContradictionCardProps {
  sourceA: ConflictSource;
  sourceB: ConflictSource;
  /** Likelihood word BEFORE the conflict was accounted for. */
  from: string;
  /** Likelihood word AFTER demotion. */
  to: string;
}

function SourceChip({ source }: { source: ConflictSource }): React.ReactElement {
  const body = (
    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium bg-cached-bg text-cached-text border border-ink-300">
      <span>{source.label}</span>
      {source.grade !== undefined && (
        <span
          className="font-mono text-[10px] px-1 rounded bg-ink-100 border border-ink-300 text-moderate-text"
          title={admiraltyGloss(source.grade)}
        >
          {source.grade}
        </span>
      )}
    </span>
  );

  if (source.url !== undefined) {
    return (
      <a href={source.url} target="_blank" rel="noreferrer" className="no-underline">
        {body}
      </a>
    );
  }
  return body;
}

export function ContradictionCard({
  sourceA,
  sourceB,
  from,
  to,
}: ContradictionCardProps): React.ReactElement {
  return (
    <div
      className="rounded border border-[#b89830] bg-[#f5f0e0] px-3 py-2 text-sm"
      data-testid="contradiction-card"
    >
      <div className="font-semibold text-[#6b5c1e] mb-1.5">⚠ 证据冲突</div>
      <div className="flex items-center gap-2 flex-wrap mb-1.5">
        <SourceChip source={sourceA} />
        <span className="text-[#6b5c1e] font-semibold">↔</span>
        <SourceChip source={sourceB} />
      </div>
      <div className="text-xs text-[#6b5c1e]">
        置信度由 <span className="font-semibold">{from}</span> 降至{' '}
        <span className="font-semibold">{to}</span>
      </div>
    </div>
  );
}

export default ContradictionCard;
