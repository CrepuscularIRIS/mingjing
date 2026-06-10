/**
 * SwotGrid — the SWOT analysis as a 2x2 grid.
 *
 *   优势 (strengths)      | 劣势 (weaknesses)
 *   机会 (opportunities)  | 威胁 (threats)
 *
 * Each quadrant lists its cited sentences (with citation chips). An empty
 * quadrant shows the calm per-section "本节数据不足" placeholder rather than a
 * blank box, so the grid always reads as deliberate.
 */

import type { SynthesisSentence } from '../api/types';
import { CitedSentence } from './CitedSentence';

export interface SwotGridProps {
  swot?: {
    strengths: SynthesisSentence[];
    weaknesses: SynthesisSentence[];
    opportunities: SynthesisSentence[];
    threats: SynthesisSentence[];
  };
  onCite: (claimId: string) => void;
  canCite?: (claimId: string) => boolean;
}

interface QuadrantProps {
  testId: string;
  title: string;
  accent: string;
  items: SynthesisSentence[];
  onCite: (claimId: string) => void;
  canCite?: (claimId: string) => boolean;
}

function Quadrant({ testId, title, accent, items, onCite, canCite }: QuadrantProps): React.ReactElement {
  return (
    <div
      data-testid={testId}
      className="rounded-lg border border-border bg-card p-4 flex flex-col shadow-card"
    >
      <h3 className={`text-xs font-semibold uppercase tracking-wide mb-2 ${accent}`}>
        {title}
      </h3>
      {items.length > 0 ? (
        <ul className="space-y-1.5">
          {items.map((s, idx) => (
            <li key={`${testId}-${idx}`} className="text-sm text-ink-700 leading-relaxed">
              <CitedSentence sentence={s} onCite={onCite} canCite={canCite} />
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">本节数据不足</p>
      )}
    </div>
  );
}

export function SwotGrid({ swot, onCite, canCite }: SwotGridProps): React.ReactElement {
  const s = swot ?? { strengths: [], weaknesses: [], opportunities: [], threats: [] };
  return (
    <section data-testid="swot-grid">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2">
        SWOT
      </h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Quadrant testId="swot-strengths" title="优势" accent="text-strong-text" items={s.strengths} onCite={onCite} canCite={canCite} />
        <Quadrant testId="swot-weaknesses" title="劣势" accent="text-rose-400" items={s.weaknesses} onCite={onCite} canCite={canCite} />
        <Quadrant testId="swot-opportunities" title="机会" accent="text-mirror-600" items={s.opportunities} onCite={onCite} canCite={canCite} />
        <Quadrant testId="swot-threats" title="威胁" accent="text-weak-text" items={s.threats} onCite={onCite} canCite={canCite} />
      </div>
    </section>
  );
}

export default SwotGrid;
