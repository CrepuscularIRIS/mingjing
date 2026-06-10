/**
 * ClaimRow — One claim line with its evidence-strength badge.
 *
 * Beyond the statement + Badge, this row carries two demo-critical affordances:
 *   - A pulsing "Revising…" indicator when a newer version is being produced
 *     (mid-revision state) so a claim visibly "works" while QA upgrades it.
 *   - A "View QA history" link for claims that were revised (version > 1),
 *     wiring navigation into the QA Replay hero view.
 */

import type { Claim } from '../api/types';
import { Badge } from './Badge';

export interface ClaimRowProps {
  claim: Claim;
  /** Highlighted when this row's claim is the one open in the drawer. */
  selected?: boolean;
  /** Show a pulsing "Revising…" indicator (a newer version is in flight). */
  revising?: boolean;
  /** Called when the row is clicked — used to open the EvidenceDrawer. */
  onSelect?: (claim: Claim) => void;
  /** Called when "View QA history" is clicked — routes to QA Replay. */
  onViewHistory?: (claim: Claim) => void;
}

export function ClaimRow({
  claim,
  selected = false,
  revising = false,
  onSelect,
  onViewHistory,
}: ClaimRowProps): React.ReactElement {
  const wasRevised = (claim.version ?? 1) > 1;

  return (
    <div
      className={[
        'flex items-start gap-3 py-3 px-3 rounded cursor-pointer border-b border-border last:border-b-0 transition-colors',
        selected ? 'bg-mirror-50' : 'hover:bg-ink-50',
      ].join(' ')}
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      onClick={() => onSelect?.(claim)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') onSelect?.(claim);
      }}
      aria-label={`Claim: ${claim.statement}`}
    >
      <div className="pt-0.5 shrink-0">
        <Badge
          strength={claim.evidence_strength}
          sourceCount={claim.evidence_source_ids.length}
        />
      </div>
      <div className="flex-1 min-w-0">
        {/* Projector-legible claim text: 24px (text-2xl) */}
        <p className="text-2xl text-ink-900 leading-snug">{claim.statement}</p>
        <div className="mt-1 flex items-center gap-3">
          {/* Explicit affirmative verdict stamp — every ledger claim IS
              QA-admitted (writer projection invariant), but until now that was
              only implicit ("it wasn't rejected"). Judges asked: "show me one
              claim's affirmative verdict." This makes admission a visible,
              per-claim fact with the round count. */}
          <span
            data-testid="qa-verdict-stamp"
            className="inline-flex items-center gap-1 text-[11px] font-semibold text-strong-text bg-strong-bg border border-strong-border rounded-full px-1.5 py-0.5"
            title={`确定性 QA 门禁判决：准入（第 ${claim.version ?? 1} 版${(claim.version ?? 1) > 1 ? '，经打回重审' : '，首轮通过'}）。判决由代码规则计算，非 LLM 自评。`}
          >
            QA✓ 准入 · v{claim.version ?? 1}
          </span>
          {revising && (
            <span
              className="inline-flex items-center gap-1.5 text-sm font-medium text-mirror-600 animate-pulse"
              data-testid="revising-indicator"
            >
              <span className="inline-block w-2 h-2 rounded-full bg-mirror-500" />
              Revising…
            </span>
          )}
          {wasRevised && onViewHistory && (
            <button
              type="button"
              className="text-sm font-medium text-mirror-600 hover:underline"
              onClick={(e) => {
                e.stopPropagation();
                onViewHistory(claim);
              }}
            >
              View QA history →
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default ClaimRow;
