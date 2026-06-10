/**
 * EvidenceDrawer — Right-side drawer proving "every conclusion is traceable".
 *
 * Given the claim's cited sources, it shows the URL, LIVE/CACHED provenance,
 * and the raw source text — with the cited chunk SCROLLED TO and visually
 * HIGHLIGHTED via a substring match against the claim's statement (or a
 * snippet of it). This click-to-source-with-highlight is the load-bearing
 * proof in the demo, so the matching degrades gracefully:
 *   1. exact statement substring,
 *   2. then the longest leading word-run that still matches,
 *   3. else no highlight (raw text still shown).
 */

import { useEffect, useMemo, useRef } from 'react';

import type { SourceProvenance } from '../api/types';
import { findHighlight } from '../lib/highlight';
import { internalSourceLabel, isHttpUrl } from '../lib/sourceUrl';
import { SourceProvenanceTag } from './SourceProvenanceTag';

export interface EvidenceDrawerProps {
  source: SourceProvenance | null;
  /**
   * ALL cited sources of the claim (M1, judge P1). When provided with more
   * than one entry, the drawer renders a citation list — real web sources are
   * expected first (the caller orders them) — and clicking an entry switches
   * the displayed source via `onSelectSource`. Optional: existing single-source
   * callers are unchanged.
   */
  sources?: SourceProvenance[];
  onSelectSource?: (s: SourceProvenance) => void;
  /** Whether a fetch for the source is currently in flight. */
  loading?: boolean;
  /** Error message if the source fetch failed (live-timeout / 404). */
  error?: string | null;
  /** The claim statement used to locate and highlight the cited chunk. */
  citedText?: string;
  onClose: () => void;
}

export function EvidenceDrawer({
  source,
  sources,
  onSelectSource,
  loading = false,
  error = null,
  citedText,
  onClose,
}: EvidenceDrawerProps): React.ReactElement {
  const markRef = useRef<HTMLElement | null>(null);

  const rawText = source?.raw_text;
  const highlight = useMemo(() => {
    if (!rawText || !citedText) return null;
    return findHighlight(rawText, citedText);
  }, [rawText, citedText]);

  // Scroll the highlighted chunk into view once it renders.
  useEffect(() => {
    if (markRef.current) {
      markRef.current.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }
  }, [highlight, source?.id]);

  if (loading && !source) {
    return (
      <aside
        className="w-96 border-l border-border bg-card shadow-lg p-6 flex items-center justify-center text-ink-500 text-base"
        aria-label="Evidence drawer"
        aria-busy="true"
      >
        正在拉取来源…
      </aside>
    );
  }

  if (error && !source) {
    return (
      <aside
        className="w-96 border-l border-border bg-card shadow-lg flex flex-col"
        aria-label="Evidence drawer"
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <h3 className="text-base font-semibold text-ink-900">来源原文</h3>
          <button
            type="button"
            className="text-ink-400 hover:text-ink-700 text-xl leading-none"
            aria-label="Close evidence drawer"
            onClick={onClose}
          >
            ×
          </button>
        </div>
        <div className="p-4 text-sm text-amber-700 bg-amber-50 m-4 rounded border border-amber-200">
          {error}
        </div>
      </aside>
    );
  }

  if (!source) {
    return (
      <aside className="w-96 border-l border-border bg-card shadow-lg p-6 flex items-center justify-center text-ink-400 text-base">
        选择一条结论以查看其证据
      </aside>
    );
  }

  const raw = source.raw_text || '（无原文）';

  return (
    <aside
      className="w-96 border-l border-border bg-card shadow-lg flex flex-col"
      aria-label="Evidence drawer"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <h3 className="text-base font-semibold text-ink-900 truncate">来源原文</h3>
        <button
          type="button"
          className="text-ink-400 hover:text-ink-700 text-xl leading-none"
          aria-label="Close evidence drawer"
          onClick={onClose}
        >
          ×
        </button>
      </div>

      {/* Citation list — every source this claim cites, real web sources first
          (caller-ordered). Hidden for single-citation claims (nothing to pick). */}
      {sources && sources.length > 1 && (
        <div data-testid="drawer-source-list" className="px-4 py-2 border-b border-border">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-500 mb-1.5">
            本结论引用的全部来源（{sources.length}）· 真实来源排前
          </p>
          <div className="space-y-1">
            {sources.map((s) => {
              const active = s.id === source.id;
              return (
                <button
                  key={s.id}
                  type="button"
                  data-testid={`drawer-source-item-${s.id}`}
                  onClick={() => onSelectSource?.(s)}
                  aria-pressed={active}
                  className={[
                    'w-full text-left flex items-center gap-1.5 rounded border px-2 py-1 text-xs transition-colors',
                    active
                      ? 'border-mirror-400 bg-mirror-50 text-ink-900'
                      : 'border-ink-200 bg-ink-50 text-ink-600 hover:bg-ink-100',
                  ].join(' ')}
                >
                  <span
                    className={[
                      'flex-shrink-0 rounded px-1 py-0.5 text-[9px] font-semibold uppercase tracking-wide border',
                      s.source_mode === 'SIMULATED'
                        ? 'bg-weak-bg text-weak-text border-weak-border'
                        : 'bg-ink-100 text-ink-600 border-ink-300',
                    ].join(' ')}
                  >
                    {s.source_mode === 'SIMULATED' ? '模拟 · 不参与分档' : s.source_mode}
                  </span>
                  <span className="truncate font-mono text-[11px]" title={s.url}>
                    {isHttpUrl(s.url) ? s.url : internalSourceLabel(s.url)}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Provenance meta */}
      <div className="px-4 py-3 border-b border-border space-y-2">
        <SourceProvenanceTag
          mode={source.source_mode}
          fetchedAt={source.fetched_at}
          sourceType={source.source_type}
        />
        {isHttpUrl(source.url) ? (
          <a
            href={source.url}
            target="_blank"
            rel="noopener noreferrer"
            className="block text-sm text-mirror-700 hover:text-mirror-800 hover:underline truncate"
            title={source.url}
          >
            {source.url}
          </a>
        ) : (
          /* survey:/interview: locators are internal evidence addresses, not web
             pages — rendering them as <a> produced a dead link (judge P1). */
          <span
            data-testid="nonlink-source-badge"
            className="inline-flex max-w-full items-center gap-1 rounded border border-ink-300 bg-ink-100 px-2 py-0.5 text-xs text-ink-600"
            title={`${source.url} — 站内证据定位符，无外部网页可打开；原文在下方完整展示。`}
          >
            <span className="truncate font-mono">{source.url}</span>
            <span className="flex-shrink-0">· {internalSourceLabel(source.url)}</span>
          </span>
        )}
        <div className="text-xs text-ink-500">
          Type: <span className="font-mono">{source.source_type}</span>
          {source.content_hash && (
            <>
              {' · hash: '}
              <span className="font-mono">{source.content_hash.slice(0, 8)}</span>
            </>
          )}
        </div>
      </div>

      {/* Raw text with the cited chunk highlighted + scrolled into view */}
      <div className="flex-1 overflow-y-auto px-4 py-3">
        <p className="text-xs font-semibold text-ink-500 uppercase tracking-wide mb-2">
          原文 {highlight && <span className="text-strong-text">· 已高亮被引用片段</span>}
        </p>
        <pre className="text-sm text-ink-700 whitespace-pre-wrap leading-relaxed font-mono">
          {highlight ? (
            <>
              {raw.slice(0, highlight.start)}
              <mark
                ref={markRef}
                data-testid="evidence-highlight"
                className="bg-strong-bg text-strong-text ring-1 ring-strong-border rounded px-0.5"
              >
                {raw.slice(highlight.start, highlight.end)}
              </mark>
              {raw.slice(highlight.end)}
            </>
          ) : (
            raw
          )}
        </pre>
      </div>
    </aside>
  );
}

export default EvidenceDrawer;
