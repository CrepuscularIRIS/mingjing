/**
 * IntelligenceGapPanel — the 情报缺口 + 关键假设 panel.
 *
 * DESIGN RATIONALE: this is a CALM panel, NOT an alarm. Honest CI work names
 * what it could NOT establish (gaps) and what it had to assume (assumptions);
 * surfacing these builds trust rather than signalling failure, so the styling
 * is neutral slate — never red/amber alarm colours.
 *
 * Doubles as the brief's EMPTY STATE: when there are no passing claims (or
 * synthesis is absent), the caller renders this panel in `emptyState` mode with
 * the "暂无达到可信门槛的结论；当前情报缺口：…" message, so the report is never
 * a blank screen.
 */

import type { SynthesisSentence } from '../api/types';
import { CitedSentence } from './CitedSentence';

export interface IntelligenceGapPanelProps {
  intelligenceGap?: SynthesisSentence[];
  keyAssumptions?: SynthesisSentence[];
  onCite: (claimId: string) => void;
  canCite?: (claimId: string) => boolean;
  /** Render as the brief's empty state (no synthesis brief available). */
  emptyState?: boolean;
  /**
   * Number of verified claims that DID reach the report ledger. Gates the
   * empty-state copy: with >0 verified claims the panel must NOT claim "no
   * credible conclusions" (that contradicts the ledger) — it points to the
   * ledger instead. Only a genuine zero-claim run shows the pessimistic copy.
   */
  admittedClaimCount?: number;
}

export function IntelligenceGapPanel({
  intelligenceGap,
  keyAssumptions,
  onCite,
  canCite,
  emptyState = false,
  admittedClaimCount = 0,
}: IntelligenceGapPanelProps): React.ReactElement {
  const gaps = intelligenceGap ?? [];
  const assumptions = keyAssumptions ?? [];

  return (
    <section
      data-testid={emptyState ? 'intelligence-gap-empty' : 'intelligence-gap-panel'}
      className="rounded-xl border border-border bg-ink-50 p-5 shadow-card"
    >
      <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-600 mb-3">
        情报缺口 / 关键假设
      </h2>

      {emptyState &&
        (admittedClaimCount > 0 ? (
          <p className="text-base text-ink-700 mb-3" data-testid="synthesis-absent-note">
            综合简报暂未生成，请查阅下方「全部已验证结论」账本（共 {admittedClaimCount} 条）；当前已识别的情报缺口：
          </p>
        ) : (
          <p className="text-base text-ink-700 mb-3" data-testid="no-passing-claims">
            暂无达到可信门槛的结论；当前情报缺口：
          </p>
        ))}

      <div className="space-y-4">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-500 mb-1">
            情报缺口
          </h3>
          {gaps.length > 0 ? (
            <ul className="space-y-1 list-disc list-inside">
              {gaps.map((g, idx) => (
                <li key={`gap-${idx}`} className="text-sm text-ink-700 leading-relaxed">
                  <CitedSentence sentence={g} onCite={onCite} canCite={canCite} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">本节数据不足</p>
          )}
        </div>

        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-500 mb-1">
            关键假设
          </h3>
          {assumptions.length > 0 ? (
            <ul className="space-y-1 list-disc list-inside">
              {assumptions.map((a, idx) => (
                <li key={`assume-${idx}`} className="text-sm text-ink-700 leading-relaxed">
                  <CitedSentence sentence={a} onCite={onCite} canCite={canCite} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">本节数据不足</p>
          )}
        </div>
      </div>
    </section>
  );
}

export default IntelligenceGapPanel;
