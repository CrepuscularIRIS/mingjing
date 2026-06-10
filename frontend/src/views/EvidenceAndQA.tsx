/**
 * EvidenceAndQA — Merged 证据&溯源 + QA 回放 inspection page.
 *
 * 3-column layout:
 *   Left  (~w-72)  — claim list, grouped by schema_field, default-selects first.
 *   Middle (flex-1) — 证据&溯源: lists ALL cited sources for the selected claim
 *                      with SourceProvenanceTag + 查看原文 (opens EvidenceDrawer).
 *   Right  (~w-96) — QA 回放: shows QAReplayFlow (weak→strong) or "一次通过" note.
 *
 * The EvidenceDrawer overlays as a modal-style panel over the right column
 * when the user clicks 查看原文 on a specific source.
 */

import { useEffect, useMemo, useRef, useState } from 'react';

import { getClaimHistory, getReport, getSource, getSurveyDesign } from '../api/client';
import type {
  Claim,
  ClaimVersion,
  ReportSection,
  SourceProvenance,
  SurveyDesign,
  TraceEvent,
} from '../api/types';
import { Badge } from '../components/Badge';
import { ContradictionCard } from '../components/ContradictionCard';
import { EvidenceDrawer } from '../components/EvidenceDrawer';
import { QAReplayFlow } from '../components/QAReplayFlow';
import { SourceProvenanceTag } from '../components/SourceProvenanceTag';
import { SpotlightCard } from '../components/ui/spotlight-card';
import { SurveyDesignCard } from '../components/SurveyDesignCard';
import { usePolling } from '../hooks/usePolling';
import { internalSourceLabel, isHttpUrl } from '../lib/sourceUrl';
import { parseEventPayload } from '../lib/trace';
import { getSchemaFieldLabel } from '../lib/schemaFieldMeta';

// ---------------------------------------------------------------------------
// Helper: extract rejection reason from trace events (lifted from QAReplay)
// ---------------------------------------------------------------------------

function rejectionReasonFor(events: TraceEvent[], claimId: string | null): string | undefined {
  if (!claimId) return undefined;
  for (let i = events.length - 1; i >= 0; i--) {
    const ev = events[i];
    if (ev.event_type !== 'qa_fail' && ev.event_type !== 'qa_verdict') continue;
    const payload = parseEventPayload(ev);
    if (payload['claim_id'] !== claimId) continue;
    const reason =
      (payload['reason'] as string | undefined) ??
      (payload['issue'] as string | undefined) ??
      (payload['verdict'] as string | undefined);
    if (reason) return reason;
  }
  return undefined;
}

// ---------------------------------------------------------------------------
// ClaimWithField — claim + its section's schema_field for left-column grouping
// ---------------------------------------------------------------------------

interface ClaimWithField extends Claim {
  schema_field: string;
}

function flattenClaims(sections: ReportSection[]): ClaimWithField[] {
  return sections.flatMap((s) =>
    s.claims.map((c) => ({ ...c, schema_field: s.schema_field })),
  );
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface EvidenceAndQAProps {
  runId: string | null;
  /** Trace events shared from the App-level poll (for QA rejection reason). */
  events: TraceEvent[];
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function EvidenceAndQA({ runId, events }: EvidenceAndQAProps): React.ReactElement {
  // ---- Report / claim list ------------------------------------------------
  const [sections, setSections] = useState<ReportSection[]>([]);
  const [reportError, setReportError] = useState<string | null>(null);

  // Track the active runId so a slow in-flight fetch for a PREVIOUS run can be
  // dropped once the active run switches (mirror of SchemaMatrix). Synced in an
  // effect — never written during render.
  const latestRunId = useRef(runId);
  useEffect(() => {
    latestRunId.current = runId;
  }, [runId]);

  usePolling(
    async () => {
      if (!runId) return;
      const id = runId;
      try {
        const res = await getReport(id);
        if (id !== latestRunId.current) return;
        setSections(res.sections);
        setReportError(null);
      } catch (err) {
        if (id !== latestRunId.current) return;
        setReportError(err instanceof Error ? err.message : 'Failed to load report');
      }
    },
    runId !== null,
    2000,
  );

  const allClaims = useMemo(() => flattenClaims(sections), [sections]);

  // G13: GLOBAL count of claims carrying a source-vs-source contradiction across
  // the whole run (the per-claim ContradictionCard still shows the detail). Pure
  // derived state from the already-loaded report — no new fetch.
  const totalContradictions = useMemo(
    () => allClaims.filter((c) => c.contradiction).length,
    [allClaims],
  );

  // ---- Selected claim — keyed by stable id, not object reference ----------
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  /** Stable key per claim — matches the React key= used in the left list. */
  function claimKey(claim: ClaimWithField, field: string, index: number): string {
    return claim.id ?? `${field}-${index}`;
  }

  /** Derive the selected claim LIVE from allClaims so it always reflects the
   *  freshest poll result without triggering a new selection. */
  const selectedClaim = useMemo((): ClaimWithField | null => {
    if (!selectedKey) return null;
    // Rebuild the grouped index in the same order as the left list so indices match.
    let i = 0;
    for (const c of allClaims) {
      if (claimKey(c, c.schema_field, i) === selectedKey) return c;
      i++;
    }
    return null;
  }, [allClaims, selectedKey]);

  // Default-select the first claim when the list first loads.
  const defaultSelectedRef = useRef(false);

  // On runId change, RESET the report-derived state + the default-selection
  // latch so the prior run's claims never show under the new id. The setState
  // calls live inside an async callback (not the effect body) to satisfy the
  // react-hooks/set-state-in-effect lint rule.
  useEffect(() => {
    async function reset(): Promise<void> {
      setSections([]);
      setReportError(null);
      setSelectedKey(null);
    }
    defaultSelectedRef.current = false;
    void reset();
  }, [runId]);

  useEffect(() => {
    async function maybeSelectFirst(): Promise<void> {
      if (defaultSelectedRef.current) return;
      if (allClaims.length > 0) {
        defaultSelectedRef.current = true;
        setSelectedKey(claimKey(allClaims[0], allClaims[0].schema_field, 0));
      }
    }
    void maybeSelectFirst();
  }, [allClaims]);

  // ---- Middle: 问卷设计 (Collector) for this run --------------------------
  const [design, setDesign] = useState<Partial<SurveyDesign>>({});
  useEffect(() => {
    // No synchronous reset needed: this view is keyed by runId in App.tsx, so a
    // run switch remounts it with the {} initial state. Bail when there's no run.
    if (!runId) {
      return;
    }
    const id = runId;
    let cancelled = false;
    getSurveyDesign(id)
      .then((d) => {
        if (!cancelled && id === latestRunId.current) setDesign(d);
      })
      .catch(() => {
        if (!cancelled) setDesign({});
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  // ---- Middle: sources for selected claim ---------------------------------
  const [sources, setSources] = useState<SourceProvenance[]>([]);
  const [sourcesLoading, setSourcesLoading] = useState(false);
  const [sourcesError, setSourcesError] = useState<string | null>(null);

  // Stable dep: join of source ids for the selected claim.
  const selectedClaimId = selectedClaim?.id ?? null;
  const selectedSourceIdsKey = selectedClaim?.evidence_source_ids.join(',') ?? '';

  useEffect(() => {
    let cancelled = false;
    // Capture the stable ids at effect-run time (not at closure-creation time).
    const ids = selectedSourceIdsKey ? selectedSourceIdsKey.split(',').filter(Boolean) : [];
    async function fetchSources(): Promise<void> {
      setSources([]);
      setSourcesError(null);
      setSourcesLoading(false);
      if (ids.length === 0) return;
      setSourcesLoading(true);
      // BUG 2 fix: use Promise.allSettled so one failing source doesn't blank the pane.
      const settled = await Promise.allSettled(ids.map((sid) => getSource(sid)));
      if (cancelled) return;
      const results: SourceProvenance[] = settled
        .filter((r): r is PromiseFulfilledResult<SourceProvenance> => r.status === 'fulfilled')
        .map((r) => r.value);
      if (!cancelled) {
        setSources(results);
        // Only show an error if EVERY source failed.
        if (results.length === 0 && ids.length > 0) {
          const firstRejection = settled.find((r) => r.status === 'rejected') as
            | PromiseRejectedResult
            | undefined;
          setSourcesError(
            firstRejection?.reason instanceof Error
              ? firstRejection.reason.message
              : 'Failed to load sources',
          );
        }
        setSourcesLoading(false);
      }
    }
    void fetchSources();
    return () => {
      cancelled = true;
    };
  }, [selectedClaimId, selectedSourceIdsKey]);

  // ---- Right: QA history for selected claim -------------------------------
  const [versions, setVersions] = useState<ClaimVersion[]>([]);

  useEffect(() => {
    let cancelled = false;
    async function fetchHistory(): Promise<void> {
      setVersions([]);
      if (!runId || !selectedClaimId) return;
      try {
        const res = await getClaimHistory(runId, selectedClaimId);
        if (!cancelled) setVersions(res.versions);
      } catch {
        // Silent — QA history is a nice-to-have
      }
    }
    void fetchHistory();
    return () => {
      cancelled = true;
    };
  }, [runId, selectedClaimId]);

  const rejectionReason = useMemo(
    () => rejectionReasonFor(events, selectedClaimId),
    [events, selectedClaimId],
  );

  const hasMultipleVersions = versions.length > 1;

  // ---- Evidence Drawer (opened per source via 查看原文) --------------------
  const [drawerSource, setDrawerSource] = useState<SourceProvenance | null>(null);

  function openDrawer(src: SourceProvenance): void {
    setDrawerSource(src);
  }

  function closeDrawer(): void {
    setDrawerSource(null);
  }

  // ---- STATE: no run -------------------------------------------------------
  if (!runId) {
    return (
      <div className="flex items-center justify-center h-full text-ink-400 text-base">
        发起一次运行后,可在此核验证据与 QA 判决。
      </div>
    );
  }

  const noData = sections.length === 0;

  // ---- STATE: waiting for data --------------------------------------------
  if (noData && !reportError) {
    return (
      <div className="flex items-center justify-center h-full text-ink-400 text-base">
        等待分析结果…
      </div>
    );
  }

  // ---- Group allClaims by schema_field for the left column ----------------
  const grouped: Map<string, ClaimWithField[]> = new Map();
  for (const c of allClaims) {
    const arr = grouped.get(c.schema_field) ?? [];
    arr.push(c);
    grouped.set(c.schema_field, arr);
  }

  return (
    <div className="flex h-full overflow-hidden gap-0">
      {/* ---- Left: claim list ---- */}
      <aside
        className="w-72 flex-shrink-0 border-r border-border bg-card overflow-y-auto"
        aria-label="Claim list"
      >
        <div className="px-3 py-2 border-b border-border">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-ink-400">
            结论列表
          </h2>
          {reportError && (
            <p className="text-xs text-amber-700 mt-1">{reportError}</p>
          )}
        </div>
        <div className="py-1">
          {Array.from(grouped.entries()).map(([field, claims]) => (
            <div key={field}>
              <p className="px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-ink-400 bg-ink-50 border-b border-border">
                {getSchemaFieldLabel(field)}
              </p>
              {claims.map((claim, i) => {
                const key = claimKey(claim, field, i);
                const isSelected = key === selectedKey;
                return (
                  <button
                    key={key}
                    type="button"
                    className={[
                      'w-full text-left px-3 py-2.5 flex items-start gap-2 border-b border-border last:border-b-0 border-l-2 transition-colors',
                      isSelected
                        ? 'bg-mirror-50 text-mirror-900 border-l-mirror-600'
                        : 'border-l-transparent hover:bg-ink-50 text-ink-800',
                    ].join(' ')}
                    onClick={() => setSelectedKey(key)}
                    aria-pressed={isSelected}
                  >
                    <span className="pt-0.5 shrink-0">
                      <Badge strength={claim.evidence_strength} />
                    </span>
                    <span className="text-sm leading-snug">{claim.statement}</span>
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </aside>

      {/* ---- Middle: 证据&溯源 ---- */}
      <section
        className="flex-1 min-w-0 border-r border-border overflow-y-auto bg-card"
        aria-label="证据&溯源"
      >
        <div className="px-4 py-3 border-b border-border sticky top-0 bg-card z-10">
          <h2 className="text-sm font-semibold text-ink-700">证据&溯源</h2>
          {selectedClaim && (
            <p className="text-xs text-ink-500 mt-0.5 truncate">
              {selectedClaim.statement}
            </p>
          )}
        </div>

        <div className="p-4 space-y-3">
          {/* 问卷设计 (Collector) — the deterministic questionnaire the collector
              designed for this run. Renders nothing when no survey lane was used. */}
          <SurveyDesignCard design={design} />
          {/* Source-vs-source conflict surfaced ABOVE the sources so a reader
              sees the disagreement (and the confidence demotion) before the
              evidence. Rendered only when the backend detected a conflict. */}
          {selectedClaim?.contradiction && (
            <ContradictionCard
              sourceA={selectedClaim.contradiction.source_a}
              sourceB={selectedClaim.contradiction.source_b}
              from={selectedClaim.contradiction.from}
              to={selectedClaim.contradiction.to}
            />
          )}
          {!selectedClaim ? (
            <p className="text-sm text-ink-400 py-8 text-center">
              请在左侧选择一个结论
            </p>
          ) : sourcesLoading ? (
            <p className="text-sm text-ink-400 py-8 text-center">加载引用来源…</p>
          ) : sourcesError ? (
            <p className="text-sm text-amber-700 py-4 text-center">{sourcesError}</p>
          ) : sources.length === 0 ? (
            <p
              className="text-sm text-ink-400 py-8 text-center"
              data-testid="no-sources-msg"
            >
              此结论暂无引用来源
            </p>
          ) : (
            sources.map((src, i) => (
              <SpotlightCard
                key={src.id}
                className="border border-border bg-card shadow-card transition-shadow hover:shadow-md hover:border-mirror-200 animate-in fade-in slide-in-from-bottom-1 fill-mode-both duration-300"
                style={{ animationDelay: `${i * 40}ms` }}
              >
                <div data-testid="source-row" className="p-3 space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="space-y-1 flex-1 min-w-0">
                    <SourceProvenanceTag
                      mode={src.source_mode}
                      sourceType={src.source_type}
                      fetchedAt={src.fetched_at}
                    />
                    {isHttpUrl(src.url) ? (
                      <a
                        href={src.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="block text-sm text-mirror-700 hover:text-mirror-800 hover:underline truncate"
                        title={src.url}
                      >
                        {src.url}
                      </a>
                    ) : (
                      /* survey:/interview: locators are internal evidence
                         addresses, not web pages — never render a dead <a>. */
                      <span
                        data-testid="nonlink-source-badge"
                        className="inline-flex max-w-full items-center gap-1 rounded border border-ink-300 bg-ink-100 px-2 py-0.5 text-xs text-ink-600"
                        title={`${src.url} — 站内证据定位符，无外部网页可打开；原文可在本卡内查看。`}
                      >
                        <span className="truncate font-mono">{src.url}</span>
                        <span className="flex-shrink-0">· {internalSourceLabel(src.url)}</span>
                      </span>
                    )}
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-ink-500">
                        Type: <span className="font-mono">{src.source_type}</span>
                      </span>
                      {src.content_hash && (
                        <span className="text-xs text-ink-400 font-mono">
                          {src.content_hash.slice(0, 8)}
                        </span>
                      )}
                    </div>
                  </div>
                  <button
                    type="button"
                    data-testid="jump-to-source-btn"
                    className="shrink-0 px-3 py-1.5 text-xs font-medium rounded border border-border text-mirror-700 hover:bg-mirror-50 hover:border-mirror-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring transition-colors"
                    onClick={() => openDrawer(src)}
                  >
                    查看原文
                  </button>
                </div>
                </div>
              </SpotlightCard>
            ))
          )}
        </div>
      </section>

      {/* ---- Right: QA 回放 ---- */}
      <aside
        className="w-96 flex-shrink-0 overflow-y-auto bg-card"
        aria-label="QA 回放"
      >
        <div className="px-4 py-3 border-b border-border sticky top-0 bg-card z-10 flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-ink-700">QA 回放</h2>
          {totalContradictions > 0 && (
            <span
              data-testid="global-contradiction-badge"
              title={`全局检测到 ${totalContradictions} 处证据冲突`}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200"
            >
              <span aria-hidden="true">⚠</span>
              <span>{totalContradictions} 处冲突</span>
            </span>
          )}
        </div>

        <div className="p-4 space-y-3">
          {!selectedClaim ? (
            <p className="text-sm text-ink-400 py-8 text-center">
              请在左侧选择一个结论
            </p>
          ) : !hasMultipleVersions ? (
            <p
              className="text-sm text-ink-400 bg-ink-50 rounded border border-border px-4 py-3 text-center"
              data-testid="single-version-note"
            >
              此结论一次通过，无打回记录
            </p>
          ) : (
            <>
              {/* Version summary above the flow */}
              <div className="space-y-2">
                {versions.map((v) => (
                  <div
                    key={`${v.id}-v${v.version}`}
                    className="flex flex-col gap-0.5 text-xs text-ink-600"
                  >
                    <div className="flex items-start gap-2">
                      <span className="font-mono text-ink-400">v{v.version}</span>
                      <Badge strength={v.evidence_strength} />
                      <span className="flex-1 leading-snug">{v.statement}</span>
                      {v.produced_by && (
                        <span
                          className={[
                            'px-1.5 py-0.5 rounded font-medium text-xs shrink-0',
                            v.produced_by.startsWith('human')
                              ? 'bg-amber-100 text-amber-800'
                              : 'bg-ink-100 text-ink-600',
                          ].join(' ')}
                        >
                          {v.produced_by}
                        </span>
                      )}
                    </div>
                    {v.note && (
                      <p
                        data-testid="version-note"
                        className="ml-5 text-xs text-ink-500 italic"
                      >
                        修正说明：{v.note}
                      </p>
                    )}
                  </div>
                ))}
              </div>

              <QAReplayFlow
                versions={versions}
                rejectionReason={rejectionReason}
                revealed
              />
            </>
          )}
        </div>
      </aside>

      {/* ---- EvidenceDrawer overlay (when a source is selected via 查看原文) ---- */}
      {drawerSource && (
        <div className="fixed inset-0 z-50 flex items-stretch justify-end pointer-events-none">
          <div className="pointer-events-auto h-full">
            <EvidenceDrawer
              source={drawerSource}
              citedText={selectedClaim?.statement}
              onClose={closeDrawer}
            />
          </div>
        </div>
      )}
    </div>
  );
}

export default EvidenceAndQA;
