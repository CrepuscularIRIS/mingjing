/**
 * Badge — Evidence-strength indicator.
 *
 * DESIGN RATIONALE: Redundant encoding is mandatory here.
 * Each evidence tier is communicated through THREE independent channels:
 *   1. LABEL  — explicit text ("Strong", "Moderate", "Weak")
 *   2. SHAPE / ICON — filled circle (Strong), half circle (Moderate), outline
 *      circle (Weak). This lets color-blind users distinguish tiers by shape alone.
 *   3. COLOR — calm, accessible palette on a neutral background.
 *      Critically, red is NOT used for "weak" evidence. Weak evidence is honest
 *      and expected in research — red would wrongly signal "broken" or "error".
 *      Instead: green (strong), indigo (moderate), amber (weak).
 *
 * The aria-label on the icon SVG makes the shape meaningful to screen readers,
 * satisfying WCAG 1.4.1 (Use of Color) at level A.
 *
 * SHAPE IMPLEMENTATION NOTES:
 *   Strong   → single <path> filled circle (one element).
 *   Moderate → TWO <path> elements: left semicircle filled + right semicircle
 *              stroke-only (no fill). This gives a visually half-filled circle
 *              that is distinct from both a fully-filled and a fully-outline
 *              circle, ensuring color-blind users can tell tiers apart by shape.
 *   Weak     → single <path> stroke-only outline circle (one element, no fill).
 */

import type { EvidenceStrength } from '../api/types';
import { admiraltyGloss } from './admiralty';

export interface BadgeProps {
  strength: EvidenceStrength;
  /** Optional source count to display inside the badge, e.g. "(3 sources)". */
  sourceCount?: number;
  /**
   * Optional shallow Admiralty grade (e.g. "B2"). When present, a SECONDARY
   * monospace tag is rendered after the primary content, with a tooltip gloss.
   * The primary text/shape/color are unchanged — this is purely additive and
   * back-compatible (no `admiralty` → identical to the original Badge).
   */
  admiralty?: string;
}

interface TierBase {
  label: string;
  /** Accessible description of the shape for screen readers. */
  shapeLabel: string;
  containerClass: string;
}

interface SinglePathTier extends TierBase {
  type: 'single';
  /** SVG path d attribute for the shape icon. */
  shapePath: string;
  iconClass: string;
}

interface HalfFilledTier extends TierBase {
  type: 'half';
  /** Filled left-semicircle path. */
  filledPath: string;
  filledClass: string;
  /** Stroked right-semicircle path (no fill). */
  outlinePath: string;
  outlineClass: string;
}

type Tier = SinglePathTier | HalfFilledTier;

// All paths use a 16×16 viewport with a circle of radius 6 centred at (8,8).
//
// Strong  → filled circle (single path).
// Moderate → TWO paths:
//   Left semicircle  (filled):  arc from top (8,2) down to bottom (8,14) going
//                               left (large-arc=1, sweep=0), closed back to start.
//   Right semicircle (outline): arc from top (8,2) down to bottom (8,14) going
//                               right (large-arc=1, sweep=1), closed back to start,
//                               rendered with stroke only (fill-none).
// Weak    → outline circle only (single path, stroke, fill-none).
const TIER_MAP: Record<EvidenceStrength, Tier> = {
  strong: {
    type: 'single',
    label: 'Strong',
    shapeLabel: 'filled circle — strong evidence',
    shapePath: 'M8 2a6 6 0 1 1 0 12A6 6 0 0 1 8 2z',
    containerClass:
      'inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold' +
      ' bg-strong-bg text-strong-text border border-strong-border',
    iconClass: 'fill-[#2e9e5a]',
  },
  moderate: {
    type: 'half',
    label: 'Moderate',
    shapeLabel: 'half circle — moderate evidence',
    // Left semicircle: start at top of circle (8,2), arc left-ward to bottom (8,14),
    // then close straight back to (8,2). large-arc=1 sweep=0 → left half.
    filledPath: 'M8 2 A6 6 0 1 0 8 14 Z',
    filledClass: 'fill-[#6060b8]',
    // Right semicircle: start at top of circle (8,2), arc right-ward to bottom (8,14),
    // then close straight back to (8,2). large-arc=1 sweep=1 → right half.
    outlinePath: 'M8 2 A6 6 0 1 1 8 14 Z',
    outlineClass: 'fill-none stroke-[#6060b8] stroke-[1.5]',
    containerClass:
      'inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold' +
      ' bg-moderate-bg text-moderate-text border border-moderate-border',
  },
  weak: {
    type: 'single',
    label: 'Weak',
    shapeLabel: 'outline circle — weak evidence',
    shapePath: 'M8 2a6 6 0 1 1 0 12A6 6 0 0 1 8 2z',
    containerClass:
      'inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold' +
      ' bg-weak-bg text-weak-text border border-weak-border',
    iconClass: 'fill-none stroke-[#b89830] stroke-2',
  },
};

export function Badge({ strength, sourceCount, admiralty }: BadgeProps): React.ReactElement {
  const tier = TIER_MAP[strength];

  return (
    <span className={tier.containerClass} data-strength={strength}>
      {/* Shape icon — provides a non-color redundant cue */}
      <svg
        width="12"
        height="12"
        viewBox="0 0 16 16"
        aria-label={tier.shapeLabel}
        role="img"
        aria-hidden="false"
        focusable="false"
      >
        {tier.type === 'half' ? (
          <>
            {/* Filled left semicircle */}
            <path d={tier.filledPath} className={tier.filledClass} />
            {/* Stroke-only right semicircle — no fill, making the half distinct */}
            <path d={tier.outlinePath} className={tier.outlineClass} />
          </>
        ) : (
          <path d={tier.shapePath} className={tier.iconClass} />
        )}
      </svg>
      {/* Text label — always explicit, never rely on color alone */}
      <span>{tier.label}</span>
      {sourceCount !== undefined && (
        <span className="opacity-70">({sourceCount})</span>
      )}
      {/* Secondary Admiralty grade — additive, monospace, with tooltip gloss. */}
      {admiralty !== undefined && (
        <span
          className="font-mono text-[10px] px-1 rounded bg-ink-200/60 border border-current opacity-80"
          title={admiraltyGloss(admiralty)}
        >
          {admiralty}
        </span>
      )}
    </span>
  );
}

export default Badge;
