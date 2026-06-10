/**
 * SourceProvenanceTag — Renders LIVE/CACHED provenance with timestamp.
 *
 * This is the load-bearing "is this real?" signal.
 * LIVE sources (fetched in this run) use a vivid green indicator so analysts
 * immediately see fresh evidence. CACHED uses a calm neutral grey — accurate
 * and readable, but visually quieter to signal the distinction clearly.
 * Both are accessible: the mode is always written as text, never color-only.
 */

import type { SourceMode } from '../api/types';

export interface SourceProvenanceTagProps {
  mode: SourceMode;
  /** Epoch seconds (real API), an ISO string (legacy/tests), or null. */
  fetchedAt: number | string | null;
  sourceType?: string;
}

/** Human-readable mode label. LIVE/CACHED stay verbatim; INGESTED → 已接入
 *  (survey/interview evidence ingested via the questionnaire lane); SNIPPET →
 *  快照 (search-snippet only, no full-page fetch). */
function modeLabel(mode: SourceMode): string {
  if (mode === 'INGESTED') return '已接入';
  if (mode === 'SNIPPET') return '快照';
  if (mode === 'SIMULATED') return '模拟';
  return mode;
}

/** Format the fetch time. Real API sends epoch SECONDS (×1000 → ms); legacy/test
 *  callers may pass an ISO string; null/invalid → empty (no fake timestamp). */
function formatFetchedAt(v: number | string | null): string {
  if (v == null || v === '') return '';
  const d = typeof v === 'number' ? new Date(v * 1000) : new Date(v);
  return Number.isNaN(d.getTime()) ? String(v) : d.toLocaleString();
}

/** Survey/interview source-type chip, or null for ordinary web sources. */
function sourceTypeChip(sourceType: string | undefined): React.ReactElement | null {
  if (sourceType === 'official') {
    return (
      <span
        className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-strong-bg text-strong-text border border-strong-border"
        title="官方一手来源（定价页/官网/官方文档）——权威来源类型；与第二个独立来源结合方可达到 strong 强度（单一来源仍为 moderate）"
      >
        🏛 官方
      </span>
    );
  }
  if (sourceType === 'survey') {
    return (
      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-mirror-50 text-mirror-700 border border-mirror-200">
        📋 问卷
      </span>
    );
  }
  if (sourceType === 'interview') {
    return (
      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-purple-50 text-purple-700 border border-purple-200">
        🎤 访谈
      </span>
    );
  }
  // Non-authoritative advisory types — deliberately MUTED (ink) palette, NOT the
  // strong/accent palette, so the chip never visually implies authority. These do
  // not affect scoring (review/forum carry the same weight as a generic web page).
  if (sourceType === 'review') {
    return (
      <span
        className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-ink-50 text-ink-600 border border-ink-200"
        title="第三方点评聚合（参考来源，非权威）"
      >
        ⭐ 点评
      </span>
    );
  }
  if (sourceType === 'forum') {
    return (
      <span
        className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-ink-50 text-ink-600 border border-ink-200"
        title="论坛 / UGC 讨论（参考来源，非权威）"
      >
        💬 论坛
      </span>
    );
  }
  return null;
}

export function SourceProvenanceTag({
  mode,
  fetchedAt,
  sourceType,
}: SourceProvenanceTagProps): React.ReactElement {
  const isLive = mode === 'LIVE';
  const isSnippet = mode === 'SNIPPET';
  const formattedDate = formatFetchedAt(fetchedAt);
  const chip = sourceTypeChip(sourceType);

  // Pill palette per provenance mode — all from named brand tokens. SNIPPET is a
  // calm neutral qualifier (snapshot only), never an alarm.
  const pillClass = isLive
    ? 'bg-live-bg text-live-text border border-strong-border'
    : isSnippet
      ? 'bg-ink-50 text-ink-600 border border-ink-200'
      : 'bg-cached-bg text-cached-text border border-ink-300';

  return (
    <span className="inline-flex items-center gap-1.5">
      {chip}
      {/* SIMULATED: fixture-seeded demo survey/interview rows. Loud, honest
          label — these rows demonstrate the ingestion path and remain verbatim-
          groundable, but contribute ZERO to evidence tiers / corroboration. */}
      {mode === 'SIMULATED' && (
        <span
          data-testid="simulated-badge"
          className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-50 text-amber-700 border border-amber-300"
          title="演示用模拟问卷/访谈数据：仅展示问卷采集通路，可做字面值溯源，但不参与证据分档与佐证计数。接入真实问卷后将标记为「已接入」并恢复权威权重。"
        >
          模拟问卷数据 · 不参与分档
        </span>
      )}
      {/* INGESTED now EXCLUSIVELY means real imported survey/interview data
          (POST /runs/{id}/survey/import → ingest_survey, PII-scrubbed,
          authoritative weight). Legacy fixture rows were migrated to
          SIMULATED, so no demo-data marker is needed here — mislabeling real
          research as 示例样本 would be the inverse honesty bug. */}
      {mode === 'INGESTED' && (
        <span
          data-testid="ingested-badge"
          className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-strong-bg text-strong-text border border-strong-border"
          title="真实接入的问卷/访谈数据（已 PII 脱敏；同一问卷的全部回答按一个独立信源域计权，享受权威来源权重）"
        >
          真实调研数据
        </span>
      )}
      <span
        className={['inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium', pillClass].join(' ')}
        title={
          isSnippet
            ? '来自搜索摘要，未抓取原文全文'
            : formattedDate
              ? `Source fetched at ${formattedDate}`
              : 'Source provenance'
        }
      >
        {/* Indicator shape doubles as a non-color cue: filled circle = LIVE,
            hollow circle = CACHED/INGESTED, outline square = SNIPPET (snapshot). */}
        {isSnippet ? (
          <span aria-hidden="true" className="inline-block w-2 h-2 rounded-[2px] border border-ink-400" />
        ) : (
          <span
            aria-hidden="true"
            className={['inline-block w-2 h-2 rounded-full', isLive ? 'bg-strong-border' : 'border border-ink-400'].join(' ')}
          />
        )}
        <span>{modeLabel(mode)}</span>
        {formattedDate && <span className="opacity-60">{formattedDate}</span>}
      </span>
    </span>
  );
}

export default SourceProvenanceTag;
