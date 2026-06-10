/**
 * reportMarkdown — serialize a MingJing brief into plain, professional
 * Simplified-Chinese Markdown so a judge can take the analysis away as a file.
 *
 * Pure + synchronous: it reads ONLY the data already on the page (report /
 * synthesis / withheld) and returns a string. No I/O, no clipboard, no mutation
 * of its inputs — the caller owns side effects (e.g. navigator.clipboard).
 *
 * The artifact mirrors the on-screen hierarchy:
 *   1. Title + run id
 *   2. BLUF (if synthesis present)
 *   3. 战略建议 / SWOT / 竞品对比 (each only when present)
 *   4. 已验证结论 — every claim (competitor · schema_field · statement · strength)
 *   5. 未采纳 (WITHHELD) — withheld claim_ids + issue_codes
 *
 * This is the deterministic ledger rendered as text: it never invents or
 * strengthens a conclusion, and the WITHHELD section is always emitted (even
 * when empty) so the "少而精" gate stays legible in the exported file.
 */

import type {
  EvidenceStrength,
  ReportResponse,
  SynthesisResponse,
  WithheldItem,
} from '../api/types';
import { getSchemaFieldLabel } from './schemaFieldMeta';

export interface BuildReportMarkdownInput {
  report: ReportResponse | null;
  synthesis: SynthesisResponse | null;
  withheld: WithheldItem[];
  /** Whether the advisory /withheld fetch has resolved. When false, the export
   *  must NOT claim "no withheld claims" — it qualifies the section instead, so
   *  the artifact never misreports the QA gate. Defaults true for callers that
   *  already hold resolved data (e.g. unit tests). */
  withheldLoaded?: boolean;
  runId: string | null;
}

/** Human-facing label for each evidence tier (kept in step with the UI legend). */
const STRENGTH_LABEL: Record<EvidenceStrength, string> = {
  strong: '强',
  moderate: '中',
  weak: '弱',
};

function strengthLabel(strength: EvidenceStrength): string {
  return STRENGTH_LABEL[strength] ?? strength;
}

/**
 * Build the Markdown document. Sections that have no data are omitted, EXCEPT
 * the WITHHELD section which is always present (it documents what the gate
 * rejected — a load-bearing honesty signal).
 */
export function buildReportMarkdown({
  report,
  synthesis,
  withheld,
  withheldLoaded = true,
  runId,
}: BuildReportMarkdownInput): string {
  const lines: string[] = [];

  // 1. Title + run id ------------------------------------------------------
  lines.push('# 明镜 · 竞品分析简报');
  lines.push('');
  lines.push(`> Run ID: \`${runId ?? '未知'}\``);
  lines.push('');

  // 2. BLUF ----------------------------------------------------------------
  if (synthesis?.bluf?.text) {
    lines.push('## 核心结论（BLUF）');
    lines.push('');
    lines.push(synthesis.bluf.text);
    lines.push('');
  }

  // 3a. 战略建议 -----------------------------------------------------------
  const recommendations = synthesis?.recommendations ?? [];
  if (recommendations.length > 0) {
    lines.push('## 战略建议');
    lines.push('');
    for (const rec of recommendations) {
      lines.push(`- ${rec.text}`);
    }
    lines.push('');
  }

  // 3b. SWOT ---------------------------------------------------------------
  const swot = synthesis?.swot;
  if (swot) {
    const quadrants: { label: string; sentences: { text: string }[] }[] = [
      { label: '优势 (Strengths)', sentences: swot.strengths },
      { label: '劣势 (Weaknesses)', sentences: swot.weaknesses },
      { label: '机会 (Opportunities)', sentences: swot.opportunities },
      { label: '威胁 (Threats)', sentences: swot.threats },
    ];
    const hasAny = quadrants.some((q) => (q.sentences?.length ?? 0) > 0);
    if (hasAny) {
      lines.push('## SWOT 分析');
      lines.push('');
      for (const q of quadrants) {
        const sentences = q.sentences ?? [];
        if (sentences.length === 0) continue;
        lines.push(`### ${q.label}`);
        lines.push('');
        for (const s of sentences) {
          lines.push(`- ${s.text}`);
        }
        lines.push('');
      }
    }
  }

  // 3c. 竞品对比 -----------------------------------------------------------
  const comparison = synthesis?.comparison ?? [];
  if (comparison.length > 0) {
    lines.push('## 竞品对比');
    lines.push('');
    for (const c of comparison) {
      lines.push(`- ${c.text}`);
    }
    lines.push('');
  }

  // 4. 已验证结论 ----------------------------------------------------------
  const sections = report?.sections ?? [];
  const totalClaims = sections.reduce((n, s) => n + s.claims.length, 0);
  lines.push(`## 已验证结论（${totalClaims} 条）`);
  lines.push('');
  if (totalClaims === 0) {
    lines.push('（暂无通过质检的结论。）');
    lines.push('');
  } else {
    for (const section of sections) {
      for (const claim of section.claims) {
        const competitor = claim.competitor ?? '未知竞品';
        const field = getSchemaFieldLabel(section.schema_field);
        const strength = strengthLabel(claim.evidence_strength);
        lines.push(
          `- **${competitor}** · ${field} · ${claim.statement} · 证据强度: ${strength}`,
        );
      }
    }
    lines.push('');
  }

  // 5. 未采纳 (WITHHELD) — always emitted ---------------------------------
  // Honesty: only assert "no withheld claims" once the advisory /withheld fetch
  // has resolved; otherwise qualify it, so the artifact never misreports the gate.
  if (!withheldLoaded) {
    lines.push('## 未采纳（WITHHELD）');
    lines.push('');
    lines.push('（质检披露数据尚未加载，未纳入本次导出。）');
    lines.push('');
  } else {
    lines.push(`## 未采纳（WITHHELD，${withheld.length} 条）`);
    lines.push('');
    if (withheld.length === 0) {
      lines.push('（本次运行无被质检打回的结论。）');
      lines.push('');
    } else {
      for (const item of withheld) {
        const codes = item.issue_codes.length > 0 ? item.issue_codes.join(', ') : '未标注';
        lines.push(`- \`${item.claim_id}\` · 问题: ${codes} · 轮次: ${item.round}`);
      }
      lines.push('');
    }
  }

  // 6. 范围与方法 (Scope & Methodology) — emitted when the backend supplied the
  // deterministic projection. Professional-CI transparency: what was analyzed,
  // from which sources, what was excluded and why, and how conclusions are gated.
  const scope = report?.scope_methodology;
  if (scope) {
    lines.push('## 范围与方法（Scope & Methodology）');
    lines.push('');
    const modeLabel = scope.mode === 'discovery' ? '自动发现模式' : '指定竞品模式';
    lines.push(
      `- 纳入范围：${modeLabel} — ${scope.competitors.map((c) => `${c.name}（${c.reason}）`).join('、')}`,
    );
    lines.push(
      `- 数据源：共 ${scope.source_stats.total} 个来源 · 独立信源域 ${scope.source_stats.independent_domains} 个 · 提议 ${scope.admission.proposed_claims} 条 → 准入 ${scope.admission.admitted_claims} 条`,
    );
    if (scope.excluded.withheld_count > 0) {
      lines.push(
        `- 未纳入：${scope.excluded.withheld_count} 条被确定性 QA 留存（${scope.excluded.issue_codes.join(', ')}）`,
      );
    }
    if (scope.excluded.uncovered_fields.length > 0) {
      lines.push(`- 未覆盖字段：${scope.excluded.uncovered_fields.join('、')}（证据不足，诚实留空）`);
    }
    for (const d of scope.excluded.disclosures) {
      lines.push(`- 披露：${d}`);
    }
    for (const s of scope.method.statements) {
      lines.push(`- 方法：${s}`);
    }
    lines.push('');
  }

  return lines.join('\n').trimEnd() + '\n';
}

export default buildReportMarkdown;
