/**
 * SchemaMatrix — evidence-strength grid: competitors × schema fields.
 *
 * Columns are driven by the active schema domain's field set.
 * A 换领域 (switch-domain) dropdown lets judges see field sets for any domain,
 * demonstrating the config-driven extensibility / 前瞻性 of the schema registry.
 *
 * Cell logic:
 *   - Claim exists for (competitor, field) → <Badge strength=... sourceCount=... />
 *   - No claim → red "缺口" pill
 *
 * The competitor row set is derived from the union of claim.competitor across
 * all report sections, sorted alphabetically for stable rendering.
 * Rows with undefined competitor are skipped.
 *
 * If no runId is provided, the domain dropdown + columns still render so the
 * schema is demoable without needing to start a run.
 */

import { useEffect, useRef, useState } from 'react';

import { getReport, getSchemaDomain, getSchemas } from '../api/client';
import type { Claim, DomainSchemaResponse, ReportResponse, SchemasListResponse } from '../api/types';
import { Badge } from '../components/Badge';
import { SourceTypeBreakdown } from '../components/SourceTypeBreakdown';
import { orderSourceTypes, sourceTypeMeta } from '../components/sourceTypeMeta';
import { usePolling } from '../hooks/usePolling';
import { getSchemaFieldLabel } from '../lib/schemaFieldMeta';

export interface SchemaMatrixProps {
  runId: string | null;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build competitor → field → Claim lookup from a report. */
function buildLookup(report: ReportResponse): Map<string, Map<string, Claim>> {
  const outer = new Map<string, Map<string, Claim>>();
  for (const section of report.sections) {
    const field = section.schema_field;
    for (const claim of section.claims) {
      if (!claim.competitor) continue;
      const competitor = claim.competitor;
      if (!outer.has(competitor)) outer.set(competitor, new Map());
      // The report already carries one latest claim per (competitor, field),
      // so this set never collides — last-write is a defensive no-op.
      outer.get(competitor)!.set(field, claim);
    }
  }
  return outer;
}

/** Sorted unique competitor names from the lookup. */
function sortedCompetitors(lookup: Map<string, Map<string, Claim>>): string[] {
  return Array.from(lookup.keys()).sort((a, b) => a.localeCompare(b));
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function SchemaMatrix({ runId }: SchemaMatrixProps): React.ReactElement {
  // --- Domain list (for the dropdown) ---
  const [schemasList, setSchemasList] = useState<SchemasListResponse | null>(null);
  const [selectedDomain, setSelectedDomain] = useState<string | null>(null);
  const [schemasError, setSchemasError] = useState<string | null>(null);

  // --- Domain field definitions (matrix columns) ---
  const [domainSchema, setDomainSchema] = useState<DomainSchemaResponse | null>(null);
  const [domainError, setDomainError] = useState<string | null>(null);

  // --- Report data (matrix rows / cells) ---
  const [report, setReport] = useState<ReportResponse | null>(null);
  const [reportError, setReportError] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // 1. Fetch schemas list once on mount
  // ---------------------------------------------------------------------------
  useEffect(() => {
    let cancelled = false;
    getSchemas()
      .then((data) => {
        if (cancelled) return;
        setSchemasList(data);
        setSelectedDomain(data.active);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setSchemasError(err instanceof Error ? err.message : String(err));
      });
    return () => { cancelled = true; };
  }, []);

  // ---------------------------------------------------------------------------
  // 2. Fetch domain field definitions whenever selectedDomain changes
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!selectedDomain) return;
    let cancelled = false;
    getSchemaDomain(selectedDomain)
      .then((data) => {
        if (cancelled) return;
        setDomainError(null);
        setDomainSchema(data);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setDomainError(err instanceof Error ? err.message : String(err));
        // Keep last good domainSchema so the table stays visible
      });
    return () => { cancelled = true; };
  }, [selectedDomain]);

  // ---------------------------------------------------------------------------
  // 3. Poll report every 2 s when runId is set
  // ---------------------------------------------------------------------------
  const latestRunId = useRef(runId);
  useEffect(() => { latestRunId.current = runId; }, [runId]);

  usePolling(
    async () => {
      if (!latestRunId.current) return;
      try {
        const data = await getReport(latestRunId.current);
        setReport(data);
        setReportError(null);
      } catch (err: unknown) {
        setReportError(err instanceof Error ? err.message : String(err));
        // Keep last good report
      }
    },
    runId !== null,
    2000,
  );

  // ---------------------------------------------------------------------------
  // Derived data
  // ---------------------------------------------------------------------------
  const fields = domainSchema ? Object.keys(domainSchema.fields) : [];
  const lookup = report ? buildLookup(report) : new Map<string, Map<string, Claim>>();
  const competitors = sortedCompetitors(lookup);

  // Source-weights legend rows (advisory): union of the domain's own weights and
  // the built-in fallback; the effective letter prefers the domain weight.
  const sw = domainSchema?.source_weights ?? null;
  const legendRows = sw
    ? orderSourceTypes(
        Array.from(new Set([...Object.keys(sw.weights), ...Object.keys(sw.fallback)])),
      ).map((type) => {
        const fromDomain = sw.weights[type];
        return {
          type,
          letter: fromDomain ?? sw.fallback[type] ?? sw.unknown_letter,
          isFallback: fromDomain === undefined,
        };
      })
    : [];

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  return (
    <div className="depth-card rounded-lg p-4 flex flex-col gap-4">
      {/* Header row: title + domain switcher */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <h2 className="text-sm font-semibold text-ink-700 uppercase tracking-wide">
          Schema 矩阵
        </h2>

        <div className="flex items-center gap-2">
          <label htmlFor="domain-select-label" className="text-xs text-ink-500 whitespace-nowrap">
            换领域
          </label>
          {schemasList ? (
            <select
              id="domain-select-label"
              data-testid="domain-select"
              className="text-xs border border-input rounded px-2 py-1 text-ink-700 bg-card focus:outline-none focus:ring-2 focus:ring-ring focus:border-ring transition-colors"
              value={selectedDomain ?? ''}
              onChange={(e) => setSelectedDomain(e.target.value)}
            >
              {schemasList.domains.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          ) : schemasError ? (
            <span className="text-xs text-destructive">{schemasError}</span>
          ) : (
            <span className="text-xs text-muted-foreground">加载中…</span>
          )}
        </div>
      </div>

      {/* Caption: domain-switch explanation */}
      <p className="text-xs text-muted-foreground">
        切换领域可预览各领域的字段集；发起新分析时，可直接在左侧表单的「领域」下拉中选择该领域（无需改代码或设环境变量）。
      </p>

      {/* Source-weights legend (advisory Admiralty reliability metadata) */}
      {legendRows.length > 0 && (
        <section data-testid="source-weights-legend" className="flex flex-col gap-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[11px] font-medium text-ink-500">来源可信权重</span>
            {legendRows.map((row) => {
              const meta = sourceTypeMeta(row.type);
              return (
                <span
                  key={row.type}
                  data-testid={`weight-${row.type}`}
                  title={`${meta.label}：Admiralty 可信度等级 ${row.letter}${row.isFallback ? '（内置默认）' : '（本领域配置）'}`}
                  className={[
                    'inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium border',
                    meta.className,
                  ].join(' ')}
                >
                  {meta.emoji} {meta.label}
                  <span className="font-mono font-semibold">{row.letter}</span>
                </span>
              );
            })}
          </div>
          <p className="text-[10px] leading-snug text-ink-400">
            次级 Admiralty 来源可信度元数据（A 最高 · F 最低），仅供参考——不参与证据强度判定与准入。
          </p>
        </section>
      )}

      {/* Domain fetch error notice */}
      {domainError && (
        <p className="text-xs text-amber-400">
          字段加载失败（显示上一次结果）：{domainError}
        </p>
      )}

      {/* Report error notice */}
      {reportError && (
        <p className="text-xs text-amber-400">
          报告加载失败（显示上一次结果）：{reportError}
        </p>
      )}

      {/* No-run state */}
      {!runId && (
        <p className="text-sm text-muted-foreground" data-testid="no-run-message">
          发起一次运行后,矩阵将按字段×竞品填充。
        </p>
      )}

      {/* Unified loading/empty skeleton: shown when runId is set but no data yet.
          Replaces the bare "等待分析结果…" text to prevent a double-flicker between
          the plain-text empty state and the awaiting-data state on first load. */}
      {runId && competitors.length === 0 && (
        <div className="space-y-2 py-2" data-testid="matrix-loading-skeleton">
          <div className="h-8 rounded-lg bg-ink-100 animate-pulse" />
          <div className="h-8 rounded-lg bg-ink-100 animate-pulse opacity-70" />
          <div className="h-8 rounded-lg bg-ink-100 animate-pulse opacity-40" />
        </div>
      )}

      {/* Matrix table */}
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm border-collapse">
          <thead>
            <tr>
              {/* Competitor column header */}
              <th className="text-left pr-4 pb-2 text-xs text-muted-foreground uppercase tracking-wide font-medium whitespace-nowrap border-b border-border">
                竞争对手
              </th>
              {fields.map((field) => (
                <th
                  key={field}
                  className="text-left px-3 pb-2 text-xs text-muted-foreground uppercase tracking-wide font-medium whitespace-nowrap border-b border-border"
                  data-testid={`col-header-${field}`}
                >
                  {getSchemaFieldLabel(field)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {/* No tbody placeholder needed: skeleton above handles the loading/empty case. */}

            {/* Data rows */}
            {competitors.map((competitor) => (
              <tr key={competitor} className="hover:bg-ink-50 transition-colors">
                <th
                  className="text-left pr-4 py-2 font-medium text-ink-900 whitespace-nowrap border-b border-ink-100 text-sm"
                  scope="row"
                >
                  {competitor}
                </th>
                {fields.map((field) => {
                  const claim = lookup.get(competitor)?.get(field);
                  return (
                    <td
                      key={field}
                      className="px-3 py-2 border-b border-ink-100 whitespace-nowrap"
                    >
                      {claim ? (
                        <>
                          <Badge
                            strength={claim.evidence_strength}
                            sourceCount={claim.evidence_source_ids.length}
                          />
                          <SourceTypeBreakdown
                            counts={claim.source_types}
                            competitor={competitor}
                            field={field}
                          />
                        </>
                      ) : (
                        <span
                          data-testid="gap-cell"
                          title="该领域字段暂无可佐证的声明"
                          className="bg-weak-bg text-weak-text border border-weak-border rounded px-2 py-0.5 text-xs opacity-80"
                        >
                          缺口
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
    </div>
  );
}

export default SchemaMatrix;
