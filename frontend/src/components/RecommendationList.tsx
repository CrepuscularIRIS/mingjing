/**
 * RecommendationList — the 建议 band of the CI brief.
 *
 * Renders the analyst's actionable recommendations as a distinct, prominent
 * band directly under the BLUF (recommendations are what a decision-maker acts
 * on). Each item is a cited sentence with inline citation chips. An empty list
 * shows the calm per-section "本节数据不足" placeholder.
 */

import type { SynthesisSentence } from '../api/types';
import { CitedSentence } from './CitedSentence';

export interface RecommendationListProps {
  recommendations?: SynthesisSentence[];
  onCite: (claimId: string) => void;
  canCite?: (claimId: string) => boolean;
}

export function RecommendationList({
  recommendations,
  onCite,
  canCite,
}: RecommendationListProps): React.ReactElement {
  const items = recommendations ?? [];
  return (
    <section
      data-testid="recommendation-band"
      className="rounded-xl border border-mirror-200 bg-mirror-50/60 p-5 shadow-card"
    >
      <h2 className="text-sm font-semibold uppercase tracking-wide text-mirror-700 mb-3">
        建议
      </h2>
      {items.length > 0 ? (
        <ol className="space-y-2 list-decimal list-inside">
          {items.map((rec, idx) => (
            <li key={`rec-${idx}`} className="text-base text-ink-800 leading-relaxed">
              <CitedSentence sentence={rec} onCite={onCite} canCite={canCite} />
            </li>
          ))}
        </ol>
      ) : (
        <p className="text-sm text-muted-foreground" data-testid="recommendation-empty">
          本节数据不足
        </p>
      )}
    </section>
  );
}

export default RecommendationList;
