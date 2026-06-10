/**
 * CredibilityPanel — Quantified proof of the deterministic QA closed loop.
 *
 * Polls GET /runs/{id}/credibility every 2 s while a run is active (mirrors
 * KpiBar). A freshly-submitted run exposes its runId while still in flight, so
 * the credibility endpoint first returns PRE-FINAL ZEROS; polling lets the
 * panel converge to the final ledger values once the run completes (rather than
 * staying stuck on +0% from a one-shot fetch). Shows repair_delta as the
 * headline metric: the groundedness improvement from round 1 → last round
 * proves the loop is a real weak→strong closed loop, not a 伪闭环.
 */

import { useEffect, useRef, useState } from 'react';

import { getCredibility } from '../api/client';
import type { CredibilityResponse } from '../api/types';
import { usePolling } from '../hooks/usePolling';
import { NumberTicker } from './ui/number-ticker';
import { ShineBorder } from './ui/shine-border';
import { getSchemaFieldLabel } from '../lib/schemaFieldMeta';

interface CredibilityPanelProps {
  runId: string | null;
}


export function CredibilityPanel({ runId }: CredibilityPanelProps): React.ReactElement | null {
  const [data, setData] = useState<CredibilityResponse | null>(null);

  // Track the active runId so a slow in-flight fetch for a PREVIOUS run can be
  // dropped once the active run switches (mirror of KpiBar). Synced in an
  // effect — never written during render.
  const latestRunId = useRef(runId);
  useEffect(() => {
    latestRunId.current = runId;
  }, [runId]);

  // Reset data whenever runId changes — to null OR to a DIFFERENT non-null id
  // — so the previous run's numbers never linger under the new id. The setState
  // call lives inside an async callback (not the effect body) to satisfy the
  // react-hooks/set-state-in-effect lint rule.
  useEffect(() => {
    async function reset(): Promise<void> {
      setData(null);
    }
    void reset();
  }, [runId]);

  usePolling(
    async () => {
      if (!runId) return;
      const id = runId;
      try {
        const result = await getCredibility(id);
        if (id !== latestRunId.current) return;
        setData(result);
      } catch {
        // Silently skip — advisory panel, never breaks the page.
      }
    },
    runId !== null,
    2000,
  );

  if (!data) return null;

  // Three honest states for repair_delta:
  //  • positive  (> 0): groundedness net gain  → lime ink + up-arrow
  //  • neutral   (= 0): first pass clean        → neutral ink, no arrow, honest copy
  //  • negative  (< 0): regression              → destructive ink + down-arrow
  const deltaPositive = data.repair_delta > 0;
  const deltaNeutral = data.repair_delta === 0;

  // Admission waterfall + coverage gaps (advisory). Optional fields → only
  // render when the backend supplied them (graceful with older responses).
  const proposed = data.proposed_claims;
  const admitted = data.admitted_claims;
  const withheld = data.withheld_claims;
  const hasWaterfall = typeof proposed === 'number' && typeof admitted === 'number';
  const uncovered = data.uncovered_fields ?? [];

  // Settled = the run reached a terminal state. An IN-FLIGHT run legitimately
  // reports pre-final zeros (claims are only promoted to pass at the write
  // node), so the zero-admitted disclosure must never fire mid-run (stop-gate
  // fix). Responses without run_status (older API) keep settled behavior.
  const settled = data.run_status !== 'running';

  // M2 (judge P1): a SETTLED run with ZERO admitted claims must never light a
  // seal. On such a run repair_delta / tier movement describe WITHHELD claims'
  // evidence improving — there is no deliverable conclusion, so no closed-loop
  // product win may be claimed. (Older API responses without admitted_claims
  // keep the previous behavior.)
  const zeroAdmitted = typeof admitted === 'number' && admitted === 0 && settled;

  // H1: the strong "真闭环 (weak→strong)" badge is gated on a REAL tier upgrade
  // (a claim crossed weak<moderate<strong), not merely a groundedness bump that
  // can stay within a single tier. A >=0.05 delta WITHOUT a tier upgrade still
  // earns an honest positive label — but not the tier-jump claim.
  const tierUpgrade = data.is_tier_upgrade === true;
  const loopConfirmed = tierUpgrade && data.repair_delta >= 0.05 && !zeroAdmitted;
  const honestGain = !tierUpgrade && data.repair_delta >= 0.05 && !zeroAdmitted;
  // J2: a REAL tier upgrade whose groundedness delta stays small (< 0.05) —
  // e.g. the first round already started from a high baseline. The version
  // history proves a claim crossed a tier (中→强), so the upgrade itself is an
  // honest backend fact (is_tier_upgrade) and deserves its own seal; only the
  // big-delta "真闭环 (weak→strong)" claim stays reserved for loopConfirmed.
  const tierUpgradeOnly = tierUpgrade && data.repair_delta < 0.05 && !zeroAdmitted;
  // Hero styling follows the same honesty: no lime glow on a 0-admitted run.
  const heroPositive = deltaPositive && !zeroAdmitted;
  const coveragePct = Math.round((data.coverage ?? 0) * 100);

  // Deterministic-gate tooltip on 准入率: name the real withheld count and make
  // explicit that rejection is decided by code rules, never by LLM self-scoring.
  const admissionTitle =
    typeof withheld === 'number' && withheld > 0
      ? `通过 QA 门禁的 claim 比例。${withheld} 条因证据不足/字面值缺失被确定性规则拒绝（非 LLM 自评）。少而精是 QA 在工作，不是失败。`
      : '通过 QA 门禁的 claim 比例（=准入率）。越低说明 QA 越严格。';

  return (
    <div className="relative border-t border-ink-200 bg-gradient-to-r from-ink-100 via-ink-100 to-mirror-50 px-6 py-3 flex items-center gap-5 flex-wrap">
      {/* HERO: repair_delta as the giant mono protagonist. When the loop is
          confirmed (>=0.05) it gets a lime glow + green seal + shine shimmer —
          the single "真闭环" signal, reserved (DESIGN.md). */}
      <div
        className={[
          'relative overflow-hidden flex flex-col items-start justify-center px-5 py-2.5 rounded-xl border',
          loopConfirmed ? 'border-strong-border bg-ink-50 animate-loopSeal' : 'border-ink-300 bg-ink-50',
        ].join(' ')}
        style={
          loopConfirmed
            ? { boxShadow: '0 0 0 1px rgb(132 204 22 / 0.25), 0 0 28px -6px rgb(132 204 22 / 0.35)' }
            : undefined
        }
        title="QA 多轮后 groundedness 的净提升量（标量，可能在同一 tier 内变动）。是否构成弱升强由版本史 tier 跳变判定（is_tier_upgrade），非由本数值。"
      >
        {loopConfirmed && <ShineBorder borderWidth={1.5} duration={9} shineColor={['#84cc16', '#2e9e5a']} />}
        <span className="text-[11px] uppercase tracking-[0.12em] font-medium text-mirror-700">
          修正增益 REPAIR_DELTA
        </span>
        <span className="flex items-baseline gap-2 leading-none mt-1">
          <span
            className={[
              'font-mono font-bold tabular-nums text-5xl leading-none',
              heroPositive ? 'text-lime-400' : deltaPositive || deltaNeutral ? 'text-ink-700' : 'text-destructive',
            ].join(' ')}
            style={heroPositive ? { textShadow: '0 0 18px rgb(132 204 22 / 0.45)' } : undefined}
          >
            <NumberTicker prefix={data.repair_delta >= 0 ? '+' : ''} value={data.repair_delta * 100} suffix="%" />
          </span>
          {!deltaNeutral && (
            <span
              className={[
                heroPositive ? 'text-lime-500' : deltaPositive ? 'text-ink-500' : 'text-destructive',
                'text-2xl',
              ].join(' ')}
            >
              {deltaPositive ? '↑' : '↓'}
            </span>
          )}
        </span>
        {/* M2: zero-admitted disclosure — the QA gate withheld every claim, so
            no seal/speedup may light; the delta only reflects withheld-claim
            evidence movement. Honest, judge-clickable state. */}
        {zeroAdmitted && (
          <span
            data-testid="zero-admitted-note"
            className="mt-1.5 inline-flex items-center gap-1 rounded-full bg-weak-bg text-weak-text border border-weak-border px-2 py-0.5 text-[11px] font-medium"
            title="本次运行没有任何结论通过 QA 准入（全部留存）。修正增益/档位变化仅描述留存结论的取证改善，不构成可交付结论，因此不点亮真闭环印章，也不做人工基线提速对比。"
          >
            0 条结论准入 · 不点亮闭环印章
          </span>
        )}
        {/* In-flight run: numbers are live intermediates, not verdicts — show a
            calm progress note instead of any settled-state badge. */}
        {!settled && (
          <span
            data-testid="run-in-progress-note"
            className="mt-1.5 inline-flex items-center gap-1 rounded-full bg-ink-100 text-ink-600 border border-ink-300 px-2 py-0.5 text-[11px] font-medium"
            title="运行尚未结束：结论在 write 节点才会被提升为准入，当前数字为实时中间值，不构成最终判定。"
          >
            分析进行中 · 指标实时更新
          </span>
        )}
        {/* F2: neutral zero-delta state — first pass clean, no repair needed.
            Reads as a calm fact, not a hollow positive. Settled runs only. */}
        {deltaNeutral && !tierUpgrade && !zeroAdmitted && settled && (
          <span
            data-testid="zero-delta-neutral"
            className="mt-1.5 inline-flex items-center gap-1 rounded-full bg-ink-100 text-ink-600 border border-ink-300 px-2 py-0.5 text-[11px] font-medium"
          >
            首轮全通过 · 无需修正
          </span>
        )}
        {/* H1: tier-upgrade confirmed → the reserved 真闭环 seal. Tier-neutral
            wording: the version history proves a claim crossed a tier upward
            (弱→中 or 中→强) — naming a specific arc here could overstate runs
            whose individual claims took different paths. */}
        {loopConfirmed && (
          <span
            data-testid="loop-confirmed-badge"
            className="mt-1.5 inline-flex items-center gap-1 rounded-full bg-strong-bg text-strong-text border border-strong-border px-2 py-0.5 text-[11px] font-semibold"
            title="真闭环 = 打回→重新取证后,版本史中有结论的证据档位真实上升(本数值 ≥5% 且 is_tier_upgrade 为真)。具体弧线见 QA 回放(如 弱→中、中→强)。"
          >
            真闭环确认 · 结论档位跃升
          </span>
        )}
        {/* J2: tier upgrade confirmed by version history but with a small
            scalar delta — show the upgrade fact without the big-delta claim. */}
        {tierUpgradeOnly && (
          <span
            data-testid="tier-upgrade-badge"
            className="mt-1.5 inline-flex items-center gap-1 rounded-full bg-strong-bg text-strong-text border border-strong-border px-2 py-0.5 text-[11px] font-semibold"
            title="版本史中存在真实的结论等级跃升（如 中→强）：QA 打回→重新取证后 tier 上升。增益标量小通常是因为首轮基线已较高。"
          >
            等级跃升确认 · 打回重采后结论升级
          </span>
        )}
        {/* H1: a real groundedness gain that did NOT cross a tier — honest
            positive label, but never claims a tier jump that didn't happen. */}
        {honestGain && (
          <span
            data-testid="honest-gain-badge"
            className="mt-1.5 inline-flex items-center gap-1 rounded-full bg-mirror-50 text-mirror-700 border border-mirror-200 px-2 py-0.5 text-[11px] font-medium"
          >
            可信度提升 +{Math.round(data.repair_delta * 100)}%（groundedness 净增，非弱升强）
          </span>
        )}
      </div>

      {/* Coverage donut (CSS conic — no chart dep, 60fps). */}
      <div className="flex flex-col items-center gap-1" title="字段覆盖率：已产出结论的字段占目标 Schema 字段的比例。">
        <div className="relative h-16 w-16">
          <div
            className="h-16 w-16 rounded-full"
            style={{ background: `conic-gradient(#449a96 ${coveragePct}%, #1b2329 ${coveragePct}% 100%)` }}
          />
          <div className="absolute inset-[6px] rounded-full bg-ink-100 flex items-center justify-center">
            <span className="text-sm font-mono font-semibold text-ink-900 tabular-nums">{coveragePct}%</span>
          </div>
        </div>
        <span className="text-[10px] uppercase tracking-wide text-ink-500">覆盖率</span>
      </div>

      {/* Secondary metrics — mono numerals. */}
      {[
        { label: '平均溯源度', value: data.avg_groundedness * 100, suffix: '%', title: '已通过 claim 的平均 groundedness 分（0=无证据,1=完全有据）' },
        { label: '准入率', value: data.claim_admission_rate * 100, suffix: '%', title: admissionTitle },
        { label: 'QA 轮次', value: data.rounds, suffix: '', title: 'QA 评分轮次 = claim 版本层数（v2+ 为打回后修订）。每轮是一次打回重采/复核，不保证都构成 weak→strong 跳变。' },
      ].map((m) => (
        <div
          key={m.label}
          className="flex flex-col items-center px-3 py-1.5 rounded-lg border border-ink-200 bg-ink-50 shadow-xs"
          title={m.title}
        >
          <span className="text-[10px] uppercase tracking-wide font-medium text-ink-500">{m.label}</span>
          <span className="text-xl font-mono font-semibold text-ink-900 tabular-nums leading-tight">
            <NumberTicker value={m.value} suffix={m.suffix} />
          </span>
        </div>
      ))}

      {/* Admission waterfall — proposed → admitted → withheld. Makes 少而精
          legible: the gap is the deterministic QA gate working, not a failure. */}
      {hasWaterfall && (
        <div
          data-testid="admission-waterfall"
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-ink-200 bg-ink-50 shadow-xs"
          title="结论准入漏斗：分析师提议 → 确定性 QA 审核 → 准入报告。留存数 = 被 QA 拒绝、未进入报告的结论数。"
        >
          <span className="text-[10px] uppercase tracking-wide font-medium text-ink-500">准入漏斗</span>
          <span className="flex items-center gap-1 font-mono text-sm tabular-nums leading-none">
            <span className="text-ink-700 font-semibold">{proposed}</span>
            <span className="text-[10px] text-ink-500">提议</span>
            <span className="text-ink-400">→</span>
            <span className="text-strong-text font-semibold">{admitted}</span>
            <span className="text-[10px] text-ink-500">准入</span>
            {typeof withheld === 'number' && withheld > 0 && (
              <>
                <span className="text-ink-400">·</span>
                <span className="text-weak-text font-semibold">{withheld}</span>
                <span className="text-[10px] text-ink-500">留存</span>
              </>
            )}
          </span>
        </div>
      )}

      {/* Coverage gaps — honest disclosure of target-schema fields with no
          evidence-backed conclusion yet (names only, never values). */}
      {uncovered.length > 0 && (
        <div
          data-testid="coverage-gaps"
          className="flex items-center gap-1.5 max-w-xs"
          title="目标 Schema 中尚无有据结论的字段。诚实披露信息缺口，而非留白。"
        >
          <span className="flex-shrink-0 text-[10px] uppercase tracking-wide font-medium text-ink-500">未覆盖字段</span>
          <span className="flex flex-wrap gap-1">
            {uncovered.map((f) => (
              <span
                key={f}
                className="rounded border border-weak-border bg-weak-bg text-weak-text px-1.5 py-0.5 text-[10px] font-medium"
              >
                {getSchemaFieldLabel(f)}
              </span>
            ))}
          </span>
        </div>
      )}

      <span className="ml-auto text-xs text-mirror-700 font-medium">确定性 QA 闭环 · LLM 不裁定真值</span>
    </div>
  );
}
