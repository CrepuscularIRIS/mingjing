/**
 * Admiralty Code gloss helpers — shared between Badge and ContradictionCard.
 *
 * The Admiralty (NATO) Code rates evidence on two axes:
 *   - Source RELIABILITY  (letter A–F): how trustworthy the source is.
 *   - Information CREDIBILITY (digit 1–6): how well-corroborated the claim is.
 *
 * We surface the grade as a compact monospace tag (e.g. "B2") plus a Chinese
 * tooltip gloss, so analysts can read the meaning without memorising the code.
 */

const RELIABILITY: Record<string, string> = {
  A: '完全可靠',
  B: '可靠',
  C: '较可靠',
  D: '不太可靠',
  E: '不可靠',
  F: '无法判断',
};

const CREDIBILITY: Record<string, string> = {
  '1': '已确认',
  '2': '多源印证',
  '3': '基本可信',
  '4': '存疑',
  '5': '不可信',
  '6': '无法判断',
};

/**
 * Build the tooltip gloss for an Admiralty grade such as "B2".
 * Falls back gracefully to the raw grade if it does not match the A–F / 1–6 form.
 */
export function admiraltyGloss(grade: string): string {
  const letter = grade.charAt(0).toUpperCase();
  const digit = grade.charAt(1);
  const reliability = RELIABILITY[letter];
  const credibility = CREDIBILITY[digit];
  if (!reliability || !credibility) {
    return `Admiralty 代码 ${grade}`;
  }
  return `来源可靠性 ${letter}（${reliability}）· 信息可信度 ${digit}（${credibility}）`;
}
