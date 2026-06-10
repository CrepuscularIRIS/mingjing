/**
 * StrengthTally — Clickable filter chips showing claim counts by evidence tier.
 * Example: "12 strong · 5 moderate · 3 weak"
 */

import type { EvidenceStrength, StrengthTally as StrengthTallyData } from '../api/types';

export interface StrengthTallyProps {
  tally: StrengthTallyData;
  /** Currently active filter; null means all tiers shown */
  activeFilter: EvidenceStrength | null;
  onFilterChange: (tier: EvidenceStrength | null) => void;
}

const CHIPS: { tier: EvidenceStrength; label: string; chipClass: string; activeClass: string }[] = [
  {
    tier: 'strong',
    label: 'strong',
    chipClass: 'border-strong-border text-strong-text hover:bg-strong-bg',
    activeClass: 'bg-strong-bg font-semibold',
  },
  {
    tier: 'moderate',
    label: 'moderate',
    chipClass: 'border-moderate-border text-moderate-text hover:bg-moderate-bg',
    activeClass: 'bg-moderate-bg font-semibold',
  },
  {
    tier: 'weak',
    label: 'weak',
    chipClass: 'border-weak-border text-weak-text hover:bg-weak-bg',
    activeClass: 'bg-weak-bg font-semibold',
  },
];

export function StrengthTally({
  tally,
  activeFilter,
  onFilterChange,
}: StrengthTallyProps): React.ReactElement {
  return (
    <div className="flex items-center gap-2 flex-wrap" role="group" aria-label="Filter by evidence strength">
      {CHIPS.map(({ tier, label, chipClass, activeClass }, idx) => (
        <span key={tier} className="flex items-center gap-1">
          <button
            type="button"
            className={[
              'px-3 py-1 rounded-full border text-sm cursor-pointer transition-colors',
              chipClass,
              activeFilter === tier ? activeClass : 'bg-card',
            ].join(' ')}
            aria-pressed={activeFilter === tier}
            onClick={() => onFilterChange(activeFilter === tier ? null : tier)}
          >
            {tally[tier]} {label}
          </button>
          {idx < CHIPS.length - 1 && (
            <span className="text-muted-foreground text-xs" aria-hidden="true">·</span>
          )}
        </span>
      ))}
    </div>
  );
}

export default StrengthTally;
