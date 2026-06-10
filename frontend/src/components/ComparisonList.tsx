/**
 * ComparisonList — the 对比 (head-to-head comparison) section of the CI brief.
 *
 * Renders the competitor comparison sentences, each with inline citation chips.
 * An empty list shows the calm per-section "本节数据不足" placeholder.
 */

import type { SynthesisSentence } from '../api/types';
import { CitedSentence } from './CitedSentence';

export interface ComparisonListProps {
  comparison?: SynthesisSentence[];
  onCite: (claimId: string) => void;
  canCite?: (claimId: string) => boolean;
}

export function ComparisonList({
  comparison,
  onCite,
  canCite,
}: ComparisonListProps): React.ReactElement {
  const items = comparison ?? [];
  return (
    <section data-testid="comparison-section">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2">
        对比
      </h2>
      <div className="rounded-lg border border-border bg-card p-4 shadow-card">
        {items.length > 0 ? (
          <ul className="space-y-1.5">
            {items.map((c, idx) => (
              <li key={`cmp-${idx}`} className="text-sm text-ink-700 leading-relaxed">
                <CitedSentence sentence={c} onCite={onCite} canCite={canCite} />
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground" data-testid="comparison-empty">
            本节数据不足
          </p>
        )}
      </div>
    </section>
  );
}

export default ComparisonList;
