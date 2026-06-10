/**
 * QAReplay — Hero View 2.
 *
 * Shows the LEFT→RIGHT QA-upgrade flow for a single revised claim (reached by
 * clicking "View QA history" on the Final Report), with:
 *   - the QAReplayFlow (Pass-1 WEAK → revision → Pass-2 STRONG),
 *   - a ~1s upgrade-reveal animation on the strong badge,
 *   - the plain-language evidence-strength rule,
 *   - the live ActivityFeed mounted alongside.
 */

import { useEffect, useMemo, useState } from 'react';

import { getClaimHistory } from '../api/client';
import type { ClaimVersion, TraceEvent } from '../api/types';
import { ActivityFeed } from '../components/ActivityFeed';
import { QAReplayFlow } from '../components/QAReplayFlow';
import { isStrengthUpgrade, replayClaimSummaries } from '../lib/qaReplay';
import { parseEventPayload } from '../lib/trace';

export interface QAReplayProps {
  runId: string | null;
  /** The claim selected on the Final Report (carried via navigation). */
  claimId: string | null;
  events: TraceEvent[];
  /** Whether the trace poll is live (drives the feed heartbeat). */
  live?: boolean;
}

/** Pull a rejection reason for a claim out of the trace, if QA recorded one. */
function rejectionReasonFor(events: TraceEvent[], claimId: string | null): string | undefined {
  if (!claimId) return undefined;
  for (let i = events.length - 1; i >= 0; i--) {
    const ev = events[i];
    if (ev.event_type !== 'qa_fail' && ev.event_type !== 'qa_verdict') continue;
    const payload = parseEventPayload(ev);
    if (payload['claim_id'] !== claimId) continue;
    const reason =
      (payload['reason'] as string | undefined) ??
      (payload['issue'] as string | undefined) ??
      (payload['verdict'] as string | undefined);
    if (reason) return reason;
  }
  return undefined;
}

export function QAReplay({
  runId,
  claimId,
  events,
  live = false,
}: QAReplayProps): React.ReactElement {
  const [versions, setVersions] = useState<ClaimVersion[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [revealed, setRevealed] = useState(false);

  // All replayable claims (strongest weak→strong story first). The view offers a
  // selector across them instead of only the single best one. An explicit claim
  // from the Final Report wins on landing; otherwise the first self-demonstrates.
  const summaries = useMemo(() => replayClaimSummaries(events), [events]);
  // The user's explicit chip selection (an override on top of prop/default).
  const [override, setOverride] = useState<string | null>(null);
  // When the navigated claim (View QA history) changes, that explicit intent wins:
  // reset the chip override. Adjusting state during render on a prop change is the
  // React-recommended alternative to a set-state-in-effect.
  const [prevClaimId, setPrevClaimId] = useState<string | null>(claimId);
  if (claimId !== prevClaimId) {
    setPrevClaimId(claimId);
    setOverride(null);
  }
  // Effective claim: a still-valid chip override → the navigated claim → the first
  // (strongest) replayable claim, so the view self-demonstrates. Derived (no
  // effect) so live-poll updates never clobber a valid selection.
  const effectiveClaimId =
    override && summaries.some((s) => s.id === override)
      ? override
      : (claimId ?? summaries[0]?.id ?? null);

  useEffect(() => {
    let cancelled = false;
    // No reset needed for the missing run/claim case: `versions` is only
    // consumed via `displayedVersions`, which treats a missing run/claim as
    // empty. Wrapping the load in an async function keeps the resets out of
    // the synchronous effect body (they run as part of the load, not render).
    if (!runId || !effectiveClaimId) {
      return () => {
        cancelled = true;
      };
    }
    async function load(id: string, claim: string): Promise<void> {
      setLoading(true);
      setError(null);
      setRevealed(false);
      try {
        const res = await getClaimHistory(id, claim);
        if (!cancelled) setVersions(res.versions);
      } catch (err: unknown) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load claim history');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load(runId, effectiveClaimId);
    return () => {
      cancelled = true;
    };
  }, [runId, effectiveClaimId]);

  // Only treat loaded versions as present when a run + claim are selected;
  // otherwise the displayed history is empty (replaces the old synchronous reset).
  const displayedVersions = useMemo(
    () => (runId && effectiveClaimId ? versions : []),
    [runId, effectiveClaimId, versions],
  );

  // Fire the upgrade-reveal once an upgraded history has loaded — ANY tier rise
  // (weak→moderate as well as weak→strong); the canonical money-shot is weak→moderate.
  const hasUpgrade = useMemo(() => {
    if (displayedVersions.length < 2) return false;
    return isStrengthUpgrade(
      displayedVersions[0].evidence_strength,
      displayedVersions[displayedVersions.length - 1].evidence_strength,
    );
  }, [displayedVersions]);

  useEffect(() => {
    if (!hasUpgrade) return;
    const t = setTimeout(() => setRevealed(true), 150);
    return () => clearTimeout(t);
  }, [hasUpgrade]);

  const rejectionReason = useMemo(
    () => rejectionReasonFor(events, effectiveClaimId),
    [events, effectiveClaimId],
  );

  return (
    <div className="flex gap-6 h-full">
      <div className="flex-1 overflow-y-auto space-y-4">
        <h1 className="font-serif text-2xl font-semibold text-foreground">QA Replay</h1>

        {runId && summaries.length > 1 && (
          <div className="space-y-1.5" data-testid="qa-claim-selector">
            <p className="text-xs text-muted-foreground">
              本次运行有 <span className="font-medium text-foreground">{summaries.length}</span> 条结论经历了「质检打回 → 重新取证」，点击切换查看：
            </p>
            <div className="flex flex-wrap gap-2">
              {summaries.map((s, i) => {
                const active = s.id === effectiveClaimId;
                const reason = rejectionReasonFor(events, s.id);
                return (
                  <button
                    key={s.id}
                    type="button"
                    data-testid={`qa-claim-chip-${i}`}
                    onClick={() => setOverride(s.id)}
                    title={reason}
                    aria-pressed={active}
                    className={[
                      'inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors',
                      active
                        ? 'border-mirror-400 bg-mirror-600 text-white'
                        : 'border-border bg-card text-ink-600 hover:border-mirror-300',
                    ].join(' ')}
                  >
                    结论 {i + 1}
                    <span
                      className={[
                        'rounded-full px-1.5 py-0.5 text-[10px] font-semibold',
                        s.upgraded
                          ? active
                            ? 'bg-white/20 text-white'
                            : 'bg-strong-bg text-strong-text'
                          : active
                            ? 'bg-white/20 text-white'
                            : 'bg-weak-bg text-weak-text',
                      ].join(' ')}
                    >
                      {s.upgraded ? '已升级' : '待升级'}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {!runId || !effectiveClaimId ? (
          <p className="text-muted-foreground text-base py-12 text-center">
            还没有可回放的结论。等到某条结论被 QA 打回并重采后，这里会自动展示它的证据强度升级（弱→中／强）；
            也可在「分析报告」点「View QA history」指定一条。
          </p>
        ) : loading ? (
          /* Skeleton: mirrors FinalReport's animate-pulse pattern (synthesis-skeleton). */
          <div className="space-y-4" data-testid="qa-loading-skeleton">
            <div className="h-28 rounded-2xl bg-ink-100 animate-pulse" />
            <div className="flex gap-4">
              <div className="h-20 flex-1 rounded-xl bg-ink-100 animate-pulse" />
              <div className="h-20 w-28 rounded-xl bg-ink-100 animate-pulse" />
              <div className="h-20 flex-1 rounded-xl bg-ink-100 animate-pulse" />
            </div>
            <div className="h-10 rounded-lg bg-ink-100 animate-pulse" />
          </div>
        ) : error ? (
          <p className="text-weak-text text-sm py-12 text-center">{error}</p>
        ) : (
          <div className="animate-in fade-in slide-in-from-bottom-2 fill-mode-both duration-500">
            <QAReplayFlow
              versions={displayedVersions}
              rejectionReason={rejectionReason}
              revealed={revealed}
            />
          </div>
        )}
      </div>

      {/* Live activity feed alongside the flow. */}
      <aside className="w-80 flex-shrink-0 border-l border-border pl-4 overflow-y-auto">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-3">
          Activity Feed
        </h2>
        <ActivityFeed events={events} live={live} />
      </aside>
    </div>
  );
}

export default QAReplay;
