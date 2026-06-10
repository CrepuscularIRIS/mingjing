/**
 * Shared highlight-matching helper used by both EvidenceDrawer and the
 * source-picker in FinalReport.
 *
 * Strategy (graceful degradation):
 *   1. Strip leading/trailing punctuation from the needle.
 *   2. Try the full cleaned statement as a substring.
 *   3. Fall back to the longest leading word-run (≥3 words) that matches.
 *   4. Return null if nothing matches.
 *
 * By reusing the same logic in both the source-picker and the drawer we
 * guarantee they always agree on which source/snippet best matches a claim.
 */

/** Offset range of a matched substring inside a haystack. */
export interface HighlightRange {
  start: number;
  end: number;
}

/**
 * Find the offset+length of the best substring of `needle` inside `haystack`.
 *
 * @param haystack  The source raw text to search in.
 * @param needle    The claim statement to locate.
 * @returns A {start, end} range, or null if no match is found.
 */
export function findHighlight(
  haystack: string,
  needle: string,
): HighlightRange | null {
  if (!haystack || !needle) return null;
  const hay = haystack.toLowerCase();
  // Strip surrounding/terminal punctuation so a statement ending in "." still
  // matches source prose that continues past the cited phrase.
  const full = needle.trim().toLowerCase().replace(/^[^\w]+|[^\w]+$/g, '');
  if (full.length >= 3) {
    const i = hay.indexOf(full);
    if (i >= 0) return { start: i, end: i + full.length };
  }
  // Fall back to the longest leading word-run that appears in the source.
  const words = full.split(/\s+/).filter(Boolean);
  for (let take = words.length; take >= 3; take--) {
    const phrase = words.slice(0, take).join(' ');
    const i = hay.indexOf(phrase);
    if (i >= 0) return { start: i, end: i + phrase.length };
  }
  return null;
}

/**
 * Score how well a source's raw_text matches a claim statement.
 * Higher is better; 0 means no match.
 *
 * Used by the source-picker to select the most relevant cited source.
 */
export function matchScore(rawText: string | undefined, statement: string): number {
  if (!rawText) return 0;
  const range = findHighlight(rawText, statement);
  if (!range) return 0;
  // Longer match = higher score.
  return range.end - range.start;
}
