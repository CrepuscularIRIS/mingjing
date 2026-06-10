/**
 * ComparisonMatrix — the deterministic 对比矩阵 (competitor × field grid).
 *
 * Unlike ComparisonList (LLM-written comparison *sentences*), this is a pure,
 * deterministic projection of the QA-passed claim ledger (`report.sections`):
 * rows = competitors, columns = schema fields, each cell = that competitor's
 * claim for that field, shown as an evidence-strength Badge. Every populated cell
 * is click-to-cite (opens the EvidenceDrawer on the underlying claim), so the
 * at-a-glance comparison stays fully traceable — no unbacked synthesis.
 *
 * Renders only when there are >= 2 competitors (a single-competitor run is better
 * served by the per-field ledger). PURE display — derives everything from props.
 */
import { useMemo } from 'react';

import type { Claim, EvidenceStrength, ReportSection } from '../api/types';
import { Badge } from './Badge';
import { getSchemaFieldLabel } from '../lib/schemaFieldMeta';

const STRENGTH_CN: Record<EvidenceStrength, string> = {
  strong: '强',
  moderate: '中',
  weak: '弱',
};

export interface ComparisonMatrixProps {
  sections: ReportSection[];
  onCite: (claimId: string) => void;
  canCite?: (claimId: string) => boolean;
}

interface MatrixModel {
  competitors: string[];
  fields: string[];
  /** cell[competitor][field] = ALL claims for that pair (usually one). */
  cell: Record<string, Record<string, Claim[]>>;
}

function buildModel(sections: ReportSection[]): MatrixModel {
  const fields: string[] = [];
  const competitors: string[] = [];
  const seenComp = new Set<string>();
  const cell: Record<string, Record<string, Claim[]>> = {};

  for (const section of sections) {
    if (!fields.includes(section.schema_field)) fields.push(section.schema_field);
    for (const claim of section.claims) {
      const comp = (claim.competitor ?? '').trim();
      if (!comp) continue;
      if (!seenComp.has(comp)) {
        seenComp.add(comp);
        competitors.push(comp);
        cell[comp] = {};
      }
      // Keep EVERY claim for a (competitor, field) — the ledger is the
      // latest-version projection (normally one per pair), but if it ever carries
      // multiple, the cell must show them all rather than silently hide some.
      (cell[comp][section.schema_field] ??= []).push(claim);
    }
  }
  return { competitors, fields, cell };
}

export function ComparisonMatrix({
  sections,
  onCite,
  canCite,
}: ComparisonMatrixProps): React.ReactElement | null {
  const { competitors, fields, cell } = useMemo(() => buildModel(sections), [sections]);

  // A comparison needs at least two competitors to compare.
  if (competitors.length < 2 || fields.length === 0) return null;

  return (
    <section data-testid="comparison-matrix">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2">
        对比矩阵
      </h2>
      <div className="rounded-lg border border-border bg-card shadow-card overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left font-medium text-ink-500 px-3 py-2 sticky left-0 bg-card">
                竞品 \ 维度
              </th>
              {fields.map((f) => (
                <th key={f} className="text-left font-medium text-ink-500 px-3 py-2 whitespace-nowrap">
                  {getSchemaFieldLabel(f)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {competitors.map((comp) => (
              <tr key={comp} className="border-b border-border last:border-0">
                <th
                  scope="row"
                  className="text-left font-semibold text-ink-800 px-3 py-2 sticky left-0 bg-card whitespace-nowrap"
                >
                  {comp}
                </th>
                {fields.map((f) => {
                  const claims = cell[comp]?.[f] ?? [];
                  return (
                    <td key={f} className="px-3 py-2 align-top">
                      {claims.length > 0 ? (
                        <span className="inline-flex flex-wrap items-center gap-1">
                          {claims.map((claim, idx) => {
                            const cid = claim.id;
                            const citeable = !!cid && (canCite ? canCite(cid) : true);
                            const testid =
                              idx === 0 ? `matrix-cell-${comp}-${f}` : `matrix-cell-${comp}-${f}-${idx}`;
                            // a11y name describes the cell by competitor·field·strength
                            // (NOT the claim statement — the statement stays in `title`
                            // so the matrix doesn't duplicate the ledger's claim text).
                            const label = `${comp} · ${f}：${STRENGTH_CN[claim.evidence_strength]}证据`;
                            return citeable ? (
                              <button
                                key={cid ?? idx}
                                type="button"
                                data-testid={testid}
                                onClick={() => onCite(cid as string)}
                                title={claim.statement}
                                aria-label={`${label}（点击溯源）`}
                                className="inline-flex items-center gap-1 rounded hover:bg-ink-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                              >
                                <Badge strength={claim.evidence_strength} />
                              </button>
                            ) : (
                              <span
                                key={cid ?? idx}
                                data-testid={testid}
                                title={claim.statement}
                                aria-label={label}
                                className="inline-flex items-center gap-1"
                              >
                                <Badge strength={claim.evidence_strength} />
                              </span>
                            );
                          })}
                        </span>
                      ) : (
                        <span className="text-ink-300" title="本维度暂无可采证据" aria-label={`${comp} · ${f}：无可采证据`}>
                          —
                        </span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-1.5 text-[11px] leading-snug text-ink-400">
        每个单元格为该竞品在该维度的 QA 准入结论（按证据强度着色）；点击可溯源到证据。空格表示无可采证据（如实留空）。
      </p>
    </section>
  );
}

export default ComparisonMatrix;
