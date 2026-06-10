/**
 * BlufHero — the full-width BLUF (Bottom Line Up Front) lead of the CI brief.
 *
 * This is the FIRST thing a reader sees: the single most decision-relevant
 * synthesis sentence, in the largest projector-legible type, with inline
 * citation chips linking to the underlying verified claims.
 *
 * The "~N analyst-hours replaced" KPI deliberately does NOT live here — it is
 * demoted to the KpiBar so the hero leads with the INTELLIGENCE, not a vanity
 * metric. When no BLUF sentence is available, a calm "本节数据不足" placeholder
 * is shown rather than a blank hero.
 */

import type { SynthesisSentence } from '../api/types';
import { CitedSentence } from './CitedSentence';

export interface BlufHeroProps {
  bluf?: SynthesisSentence;
  onCite: (claimId: string) => void;
  canCite?: (claimId: string) => boolean;
}

export function BlufHero({ bluf, onCite, canCite }: BlufHeroProps): React.ReactElement {
  return (
    <section
      data-testid="bluf-hero"
      className="rounded-2xl border border-border bg-gradient-to-br from-card to-mirror-50/40 p-8 shadow-card"
    >
      <p className="text-sm font-semibold uppercase tracking-wide text-mirror-600 mb-3">
        BLUF · 核心结论
      </p>
      {bluf ? (
        <CitedSentence
          sentence={bluf}
          onCite={onCite}
          canCite={canCite}
          className="block font-serif text-2xl md:text-3xl font-semibold text-ink-900 leading-snug"
        />
      ) : (
        <p className="text-xl text-muted-foreground" data-testid="bluf-empty">
          本节数据不足
        </p>
      )}
    </section>
  );
}

export default BlufHero;
