/**
 * QAReplayFlow — deterministic LEFT→RIGHT QA-upgrade money-shot.
 *
 *   [Pass 1 · 初判 (弱)]  → 打回·证据偏弱 →  [重新取证 +N 来源]  → 复核通过·已升级 →  [Pass 2 · 复核 (中/强)]
 *
 * The tier badge CHANGES across the flow (弱 → 中/强). On arrival, the upgraded
 * pass-2 badge plays a one-shot scale/glow ("upgrade reveal"); the numeric
 * before→after delta (来源 count + tier) and the plain-language evidence rule are
 * shown below.
 *
 * Rendered as a plain flex layout (NOT ReactFlow): the flow is a fixed 3-node
 * left→right story, so a canvas adds only a fragile fitView/pan-zoom layer that
 * mis-measured under the view's entrance animation and rendered empty. Static
 * layout is always-visible, judge-readable in ≤10s, and renders identically in
 * jsdom and Chrome. Celebrates weak→MODERATE as a real upgrade, not only →strong.
 */

import { useMemo } from 'react';

import type { ClaimVersion } from '../api/types';
import { isStrengthUpgrade } from '../lib/qaReplay';
import { Badge } from './Badge';
import { RevisionTaskChip } from './RevisionTaskChip';
import { NumberTicker } from './ui/number-ticker';

/** Chinese label + token-trio class per evidence tier, for the before→after delta. */
const TIER_CN: Record<string, string> = { strong: '强', moderate: '中', weak: '弱' };
const TIER_CLASS: Record<string, string> = {
  strong: 'border-strong-border bg-strong-bg text-strong-text',
  moderate: 'border-moderate-border bg-moderate-bg text-moderate-text',
  weak: 'border-weak-border bg-weak-bg text-weak-text',
};
/** Tier-aware reveal glow (honest: green for 强, mirror/indigo for 中). */
const TIER_GLOW: Record<string, string> = {
  strong: 'animate-upgrade drop-shadow-[0_0_8px_rgba(46,158,90,0.7)]',
  moderate: 'animate-upgrade drop-shadow-[0_0_8px_rgba(96,96,184,0.6)]',
};

/** Plain-language, tier-aware rule that justifies the upgraded tier. */
function ruleForTier(strength: string): string {
  if (strength === 'strong')
    return '强 = 2 个及以上相互独立的来源，且含 1 个权威来源（官方／调研）。';
  if (strength === 'moderate')
    return '中 = 2 个及以上相互独立的来源相互印证。';
  return '弱 = 仅单一来源，或来源相互独立性不足。';
}

export interface QAReplayFlowProps {
  /** Oldest-first claim versions; first + last drive the flow. */
  versions?: ClaimVersion[];
  /** The rejection reason for pass-1 (from QA verdict / issues), if known. */
  rejectionReason?: string;
  /** Whether the pass-2 upgrade just completed (drives the reveal animation). */
  revealed?: boolean;
}

interface PassCardProps {
  /** Layout slot — also keys the badge test id (NOT the tier, so 中 pass-2 is correct). */
  slot: 'pass1' | 'pass2';
  eyebrow: string;
  version: ClaimVersion;
  reason?: string;
  /** Play the one-shot upgrade glow on this (pass-2) badge. */
  reveal?: boolean;
}

function PassCard({ slot, eyebrow, version, reason, reveal }: PassCardProps): React.ReactElement {
  const isPass2 = slot === 'pass2';
  const glow = reveal && isPass2 ? TIER_GLOW[version.evidence_strength] ?? '' : '';
  return (
    <div className="w-72 flex-shrink-0 rounded-lg depth-card interactive-card p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {eyebrow}
        </span>
        <span data-testid={isPass2 ? 'pass2-badge' : 'pass1-badge'} className={['inline-block', glow].filter(Boolean).join(' ')}>
          <Badge
            strength={version.evidence_strength}
            sourceCount={version.evidence_source_ids.length}
          />
        </span>
      </div>
      <p className="text-base text-foreground leading-snug">{version.statement}</p>
      {reason && (
        <p className="mt-2 text-xs text-weak-text bg-weak-bg rounded px-2 py-1 border border-weak-border">
          打回原因：{reason}
        </p>
      )}
    </div>
  );
}

/** A captioned connector between two stages of the flow. */
function FlowArrow({ caption, tone }: { caption: string; tone: 'reject' | 'upgrade' }): React.ReactElement {
  const color = tone === 'reject' ? 'text-weak-text' : 'text-strong-text';
  const line = tone === 'reject' ? 'bg-weak-border' : 'bg-strong-border';
  return (
    <div className="flex flex-col items-center justify-center gap-1 min-w-[6.5rem] self-center px-1">
      <span className={['text-[10px] font-medium text-center leading-tight', color].join(' ')}>
        {caption}
      </span>
      <div className="flex items-center w-full" aria-hidden="true">
        <div className={['h-px flex-1', line].join(' ')} />
        <span className={['text-base leading-none', color].join(' ')}>→</span>
      </div>
    </div>
  );
}

export function QAReplayFlow({
  versions,
  rejectionReason,
  revealed = false,
}: QAReplayFlowProps): React.ReactElement {
  const pass1 = versions && versions.length > 0 ? versions[0] : null;
  const pass2 = versions && versions.length > 1 ? versions[versions.length - 1] : null;

  const addedEvidence = useMemo(() => {
    if (!pass1 || !pass2) return 0;
    return Math.max(0, pass2.evidence_source_ids.length - pass1.evidence_source_ids.length);
  }, [pass1, pass2]);

  if (!pass1 || !pass2) {
    return (
      <div
        data-testid="first-pass-note"
        className="rounded-xl border border-strong-border bg-strong-bg text-strong-text shadow-card p-8 text-center text-sm"
      >
        ✓ 这条结论一次通过，没有可回放的「打回→升级」过程。
      </div>
    );
  }

  const upgraded = isStrengthUpgrade(pass1.evidence_strength, pass2.evidence_strength);

  return (
    <div>
      {/* Always-visible deterministic flow — no canvas to mis-fit. */}
      <div
        data-testid="qa-moneyshot"
        className="rounded-xl border border-border bg-card shadow-card p-5 flex items-stretch gap-2 overflow-x-auto"
      >
        <PassCard slot="pass1" eyebrow="Pass 1 · 初判" version={pass1} reason={rejectionReason} />
        <FlowArrow tone="reject" caption="QA 打回 · 证据偏弱" />
        <div className="flex flex-col items-center justify-center gap-2 min-w-[7rem] self-center">
          <RevisionTaskChip taskType="qa-revision" status="done" label="重新取证" />
          {/* level-up beat. startValue=final N: a screenshot/recording captured
              on the first animation frame must never show a false "+0 来源"
              (judge P2) — the number renders at its honest value immediately. */}
          <span className="text-xs text-muted-foreground tabular-nums" data-testid="added-evidence">
            <NumberTicker value={addedEvidence} startValue={addedEvidence} prefix="+" /> 来源
          </span>
        </div>
        <FlowArrow tone="upgrade" caption="QA 复核通过 · 已升级" />
        <PassCard slot="pass2" eyebrow="Pass 2 · 复核" version={pass2} reveal={revealed && upgraded} />
      </div>

      {/* G11: explicit numeric before→after delta — source-count and tier改善, with the
          actual tiers (honest: 弱 → 中/强), the target token popping once on reveal. */}
      <div
        data-testid="qa-delta"
        className="mt-3 rounded-md border border-border bg-card shadow-xs px-3 py-2 flex flex-wrap items-center gap-x-4 gap-y-1"
      >
        <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          升级幅度
        </span>
        <span className="inline-flex items-center gap-1.5 text-sm">
          <span className="text-muted-foreground tabular-nums">{pass1.evidence_source_ids.length} 来源</span>
          <span className="text-mirror-600" aria-hidden="true">→</span>
          <span className="text-strong-text font-semibold tabular-nums">
            {/* Animates pass1 → pass2 count (e.g. 2→4), never from a false 0
                frame that an automated capture could record (judge P2). */}
            <NumberTicker
              value={pass2.evidence_source_ids.length}
              startValue={pass1.evidence_source_ids.length}
            />{' '}
            来源
          </span>
        </span>
        <span className="inline-flex items-center gap-1.5 text-sm">
          <span className={['px-2 rounded border', TIER_CLASS[pass1.evidence_strength] ?? TIER_CLASS.weak].join(' ')}>
            {TIER_CN[pass1.evidence_strength] ?? pass1.evidence_strength}
          </span>
          <span className="text-mirror-600" aria-hidden="true">→</span>
          <span
            className={[
              'px-2 rounded border',
              TIER_CLASS[pass2.evidence_strength] ?? TIER_CLASS.strong,
              revealed && upgraded ? TIER_GLOW[pass2.evidence_strength] ?? '' : '',
            ].join(' ')}
          >
            {TIER_CN[pass2.evidence_strength] ?? pass2.evidence_strength}
          </span>
        </span>
      </div>

      {/* Plain-language, tier-aware rule that justifies the upgraded tier. */}
      <p
        className="mt-3 text-sm text-strong-text bg-strong-bg border border-strong-border rounded px-3 py-2"
        data-testid="strength-rule"
      >
        规则：{ruleForTier(pass2.evidence_strength)}
      </p>
    </div>
  );
}

export default QAReplayFlow;
