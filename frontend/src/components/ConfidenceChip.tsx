/**
 * ConfidenceChip — Dual-axis confidence indicator.
 *
 * DESIGN RATIONALE: Confidence is communicated as TWO distinct segments, never
 * a single opaque number:
 *   1. LIKELIHOOD WORD — a calibrated natural-language term (e.g. "很可能" /
 *      "Likely"). This is what a human analyst actually reasons about.
 *   2. BAND INDICATOR — a coarse dot/pill colored by band (high/moderate/low).
 *
 * BANDS ONLY: we deliberately never render a decimal/percentage. A fabricated
 * "0.87" score implies a precision the pipeline does not have; the coarse band
 * is the honest signal. The band also provides a non-text (color + shape) cue.
 */

import type { ConfidenceBand } from '../api/types';

export interface ConfidenceChipProps {
  /** The likelihood word, e.g. "很可能" / "Likely". */
  likelihood: string;
  /** Coarse confidence band — drives the dot color. Never a decimal. */
  band: ConfidenceBand;
}

interface BandStyle {
  /** Accessible description of the band for screen readers. */
  label: string;
  /** Class for the band dot — distinct color per band. */
  dotClass: string;
  containerClass: string;
}

const BAND_MAP: Record<ConfidenceBand, BandStyle> = {
  high: {
    label: '高置信',
    dotClass: 'w-2 h-2 rounded-full bg-[#2e9e5a]',
    containerClass: 'bg-strong-bg text-strong-text border border-strong-border',
  },
  moderate: {
    label: '中置信',
    dotClass: 'w-2 h-2 rounded-full bg-[#6060b8]',
    containerClass: 'bg-moderate-bg text-moderate-text border border-moderate-border',
  },
  low: {
    label: '低置信',
    dotClass: 'w-2 h-2 rounded-full bg-[#b89830]',
    containerClass: 'bg-weak-bg text-weak-text border border-weak-border',
  },
};

export function ConfidenceChip({ likelihood, band }: ConfidenceChipProps): React.ReactElement {
  const style = BAND_MAP[band];

  return (
    <span
      className={
        'inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-semibold ' +
        style.containerClass
      }
      data-confidence-band={band}
    >
      {/* Band indicator — colored dot, a non-text cue distinct per band. */}
      <span
        className={style.dotClass}
        data-band={band}
        role="img"
        aria-label={style.label}
      />
      {/* Likelihood word — the calibrated natural-language term. */}
      <span>{likelihood}</span>
    </span>
  );
}

export default ConfidenceChip;
