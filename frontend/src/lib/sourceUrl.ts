/**
 * Shared helpers for rendering evidence-source URLs.
 *
 * survey:/interview: locators are INTERNAL evidence addresses (survey_seed /
 * ingest write them as `survey:<id>/qN` etc.) — they are not web pages, so
 * rendering them as an <a href> produces a dead link. Every surface that
 * displays a source URL (EvidenceDrawer, EvidenceAndQA source rows) must go
 * through these helpers so the non-link badge behavior stays consistent.
 */

/** True for a real, externally-openable web URL (survey:/interview: locators are not). */
export function isHttpUrl(url: string): boolean {
  return /^https?:\/\//i.test(url);
}

/** Human label for an internal (non-web) evidence locator. */
export function internalSourceLabel(url: string): string {
  if (url.startsWith('survey:')) return '问卷调研来源 · 站内定位符';
  if (url.startsWith('interview:')) return '访谈来源 · 站内定位符';
  return '站内来源（无外部链接）';
}
