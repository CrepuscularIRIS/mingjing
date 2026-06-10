/**
 * CitedSentence — one factual synthesis sentence with inline citation chips.
 *
 * Each `claim_ids` entry renders as a clickable [c1]-style chip. Clicking a chip
 * opens the in-place EvidenceDrawer for that claim (NO tab switch) via `onCite`.
 * If a chip references a claim that is not in the report ledger (defensive), it
 * still renders but is non-interactive.
 *
 * An optional dual-axis ConfidenceChip is shown when the sentence carries a
 * likelihood word + band (the honest, never-a-decimal confidence cue).
 */

import type { SynthesisSentence } from '../api/types';
import { ConfidenceChip } from './ConfidenceChip';

export interface CitedSentenceProps {
  sentence: SynthesisSentence;
  /** Open the EvidenceDrawer for the given claim id (in-place, no tab switch). */
  onCite: (claimId: string) => void;
  /** Whether a claim id is resolvable to a real claim in the ledger. */
  canCite?: (claimId: string) => boolean;
  className?: string;
}

export function CitedSentence({
  sentence,
  onCite,
  canCite,
  className,
}: CitedSentenceProps): React.ReactElement {
  const { text, likelihood, confidence_band } = sentence;
  // Defensive: scaffold sentences (gap/assumptions) may omit claim_ids.
  const claim_ids = Array.isArray(sentence.claim_ids) ? sentence.claim_ids : [];
  return (
    <span className={className}>
      <span>{text}</span>
      {claim_ids.length > 0 && (
        <span className="inline-flex items-center gap-1 ml-1 align-baseline">
          {claim_ids.map((cid) => {
            const enabled = canCite ? canCite(cid) : true;
            // Elegant short label: real claim ids are UUIDs — show a 4-char ref so
            // the chip stays compact; the full id lives in the tooltip + aria-label,
            // and onCite/testid still use the full id (so behavior/tests are unchanged).
            const shortRef = cid.length > 8 ? cid.slice(0, 4) : cid;
            return (
              <button
                key={cid}
                type="button"
                disabled={!enabled}
                onClick={() => onCite(cid)}
                data-testid={`citation-chip-${cid}`}
                title={`结论 ${cid}`}
                aria-label={`查看结论 ${cid} 的证据`}
                className={[
                  'inline-flex items-center rounded-md border px-1.5 py-0.5 text-[0.7rem] font-mono font-semibold leading-none align-baseline transition-all',
                  enabled
                    ? 'border-mirror-200 bg-mirror-50 text-mirror-700 shadow-xs hover:bg-mirror-100 hover:border-mirror-300 hover:shadow-sm cursor-pointer'
                    : 'border-ink-200 bg-ink-50 text-ink-400 cursor-default',
                ].join(' ')}
              >
                [{shortRef}]
              </button>
            );
          })}
        </span>
      )}
      {likelihood && confidence_band && (
        <span className="ml-1.5 align-baseline">
          <ConfidenceChip likelihood={likelihood} band={confidence_band} />
        </span>
      )}
    </span>
  );
}

export default CitedSentence;
