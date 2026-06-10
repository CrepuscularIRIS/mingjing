/**
 * Shared source-type display metadata (label + emoji + chip classes + order).
 *
 * One source of truth for how a `source_type` string is shown across the app
 * (SourceTypeBreakdown, and reusable by SourceProvenanceTag). Authoritative types
 * {official, survey, interview} use the strong/accent palette; non-authoritative
 * types {news, review, forum, web} use a deliberately MUTED palette so the UI
 * never visually implies authority a source does not have.
 *
 * Display-only: this metadata never affects scoring/QA — it just renders labels.
 */

export interface SourceTypeMeta {
  label: string;
  emoji: string;
  /** Tailwind chip classes. */
  className: string;
  /** True for the scorer's authoritative types {official, survey, interview}. */
  authoritative: boolean;
}

const META: Record<string, SourceTypeMeta> = {
  official: {
    label: '官方',
    emoji: '🏛',
    className: 'bg-strong-bg text-strong-text border-strong-border',
    authoritative: true,
  },
  survey: {
    label: '问卷',
    emoji: '📋',
    className: 'bg-mirror-50 text-mirror-700 border-mirror-200',
    authoritative: true,
  },
  interview: {
    label: '访谈',
    emoji: '🎤',
    className: 'bg-purple-50 text-purple-700 border-purple-200',
    authoritative: true,
  },
  news: { label: '新闻', emoji: '📰', className: 'bg-ink-50 text-ink-600 border-ink-200', authoritative: false },
  review: { label: '点评', emoji: '⭐', className: 'bg-ink-50 text-ink-600 border-ink-200', authoritative: false },
  forum: { label: '论坛', emoji: '💬', className: 'bg-ink-50 text-ink-600 border-ink-200', authoritative: false },
  web: { label: '网页', emoji: '🌐', className: 'bg-ink-50 text-ink-500 border-ink-200', authoritative: false },
};

const FALLBACK: SourceTypeMeta = {
  label: '其他',
  emoji: '🔗',
  className: 'bg-ink-50 text-ink-500 border-ink-200',
  authoritative: false,
};

/** Authoritative-first display order; unknown types sort last, alphabetically. */
const ORDER = ['official', 'survey', 'interview', 'news', 'review', 'forum', 'web'];

export function sourceTypeMeta(sourceType: string): SourceTypeMeta {
  return META[sourceType] ?? FALLBACK;
}

/** Stable display order for a set of source types (authoritative first). */
export function orderSourceTypes(types: string[]): string[] {
  return [...types].sort((a, b) => {
    const ia = ORDER.indexOf(a);
    const ib = ORDER.indexOf(b);
    if (ia === -1 && ib === -1) return a.localeCompare(b);
    if (ia === -1) return 1;
    if (ib === -1) return -1;
    return ia - ib;
  });
}
