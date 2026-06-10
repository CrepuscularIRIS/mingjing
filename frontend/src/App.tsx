/**
 * App — MingJing competitive-analysis workbench shell.
 *
 * Layout:
 *  - Top header bar (branding + run-id display)
 *  - Optional polling-error banner
 *  - Left "运行" collapsible panel (run form + activity feed)
 *  - Left nav (5 workbench tabs, vertical)
 *  - KpiBar at the top of main content
 *  - Main content area (active tab view)
 *
 * Tab mapping:
 *   分析报告  → FinalReport
 *   Schema 矩阵 → SchemaMatrix
 *   证据&溯源   → EvidenceAndQA
 *   QA 回放   → QAReplay
 *   执行轨迹  → ExecutionTrace
 *
 * Chrome is built on the shadcn/ui primitives (src/components/ui) + the brand
 * ink/mirror tokens; the main view reveals with a Magic UI BlurFade on tab
 * switch (motion on state change, never idle).
 */

import { Suspense, lazy, useCallback, useEffect, useRef, useState } from 'react';
import {
  Activity,
  ChevronLeft,
  ChevronRight,
  FileText,
  Gauge,
  History,
  ScanSearch,
  Table,
  Workflow,
  type LucideIcon,
} from 'lucide-react';
import { LayoutGroup, MotionConfig, motion } from 'motion/react';
import './index.css';

import { createRun, getSchemas, getTrace } from './api/client';
import type { Claim, TraceEvent } from './api/types';
import { ActivityFeed } from './components/ActivityFeed';
import { CredibilityPanel } from './components/CredibilityPanel';
import { DiscoveredCompetitors } from './components/DiscoveredCompetitors';
import { EvidenceLegend } from './components/EvidenceLegend';
import { KpiBar } from './components/KpiBar';
import { RecentRuns } from './components/RecentRuns';
import { Badge } from './components/ui/badge';
import { BlurFade } from './components/ui/blur-fade';
import { DotPattern } from './components/ui/dot-pattern';
import { Button } from './components/ui/button';
import { Input } from './components/ui/input';
import { Label } from './components/ui/label';
import { Textarea } from './components/ui/textarea';
import { usePanelResize } from './hooks/usePanelResize';
import { usePolling } from './hooks/usePolling';
import { mergeTraceEvents } from './lib/trace';
import { EvidenceAndQA } from './views/EvidenceAndQA';
// Lazy-loaded: only referenced by the 'trace' and 'observability' tabs, which
// pull in reactflow and recharts respectively (~360 KB combined). Keeping them
// out of the initial chunk makes the money-shot path (report / QA replay) load
// faster and eliminates the Vite chunk-size warning.
const ExecutionTrace = lazy(() => import('./views/ExecutionTrace'));
const Observability = lazy(() => import('./views/Observability'));
import { FinalReport } from './views/FinalReport';
import { QAReplay } from './views/QAReplay';
import { SchemaMatrix } from './views/SchemaMatrix';

type Tab = 'report' | 'schema' | 'evidence' | 'qa-replay' | 'trace' | 'observability';

const NAV_ITEMS: { key: Tab; label: string; icon: LucideIcon; description: string }[] = [
  {
    key: 'report',
    label: '分析报告',
    icon: FileText,
    description:
      'AI 分析师综合所有已验证结论生成的竞品简报：结论先行(BLUF) + SWOT + 对比 + 建议 + 情报缺口；每句话可点引用溯源。',
  },
  {
    key: 'schema',
    label: 'Schema 矩阵',
    icon: Table,
    description:
      '竞品 × 字段(定价/功能/用户画像/SWOT)的结构化矩阵，按证据强度着色；支持换分析领域。',
  },
  {
    key: 'evidence',
    label: '证据&溯源',
    icon: ScanSearch,
    description:
      '每条结论的原始证据：点结论查看引用来源与高亮原文，含 LIVE/CACHED 标记与来源可靠性评级。',
  },
  {
    key: 'qa-replay',
    label: 'QA 回放',
    icon: History,
    description:
      '质检反馈闭环回放：看一条结论被打回 → 补充证据 → 变强直至通过（非伪闭环）。',
  },
  {
    key: 'trace',
    label: '执行轨迹',
    icon: Workflow,
    description:
      '多 Agent 协作执行 DAG：采集 → 分析 → 质检 → 打回重采 → 撰写 → 综合，含每步 LLM 调用与 Token。',
  },
  {
    key: 'observability',
    label: '可观测',
    icon: Gauge,
    description:
      '“给我看你的工作”：按 Agent/节点查看每步的 LLM Prompt、输出与 Token 用量（含 Token 柱状图），点 Agent 展开溯源。',
  },
];

export default function App(): React.ReactElement {
  // ---- Run form state ----
  const [category, setCategory] = useState('');
  const [competitorsRaw, setCompetitorsRaw] = useState('');
  const [goal, setGoal] = useState('');
  // Discovery Mode: market scope hint. Empty competitors + a category triggers
  // the backend's bounded competitor-discovery pre-step.
  const [marketScope, setMarketScope] = useState('global');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // ---- Domain dropdown (optional, populated from getSchemas) ----
  // Fetched once on mount. Failure is silent: the dropdown is a nice-to-have,
  // so if the fetch fails the form still works exactly as before (no select).
  const [domains, setDomains] = useState<string[]>([]);
  const [domain, setDomain] = useState('');

  useEffect(() => {
    getSchemas()
      .then((r) => {
        setDomains(r.domains);
        // Default to `active`, but only if it's a real option — guard a malformed
        // /schemas response so the <select> never sits on an unlisted value.
        setDomain(r.domains.includes(r.active) ? r.active : (r.domains[0] ?? ''));
      })
      .catch(() => {
        // Silent — dropdown is optional; form remains fully functional.
      });
  }, []);

  // ---- Active run ----
  // Deep-link: ?run=<id> seeds the initial active run (for demo / 答辩 / sharing).
  // A run created from the UI uses the live collector; corpus-driven demo runs
  // (scripts/run_demo.py) are best viewed by id via this deep link. Read once
  // via a lazy initializer so no setState-in-effect is needed.
  const [runId, setRunId] = useState<string | null>(
    () => new URLSearchParams(window.location.search).get('run'),
  );
  // Mirror the active run id in a ref so an in-flight trace poll can detect a
  // mid-flight run switch and drop its now-stale result (else old events leak
  // into the new run and its early trace is skipped). Updated SYNCHRONOUSLY in
  // the run setters (loadRun / handleSubmit) — never via a passive effect — so
  // the guard is accurate the instant the run switches, with no post-commit
  // window where a late old-run fetch could slip past it.
  const runIdRef = useRef(runId);

  // ---- Tab ----
  const [activeTab, setActiveTab] = useState<Tab>('report');

  // ---- Claim carried from Final Report → QA Replay ("View QA history") ----
  const [qaClaimId, setQaClaimId] = useState<string | null>(null);

  // ---- Activity feed (live trace polling) ----
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [sinceSeq, setSinceSeq] = useState(0);

  // ---- Polling error banner ----
  const [pollingError, setPollingError] = useState(false);

  // ---- Run panel open/closed ----
  const [runPanelOpen, setRunPanelOpen] = useState(true);
  const { panelWidth, minWidth, maxWidth, handlePointerDown, nudge } = usePanelResize(288, 180, 500);

  // ---- Bump to force the RecentRuns list to refresh (e.g. after create) ----
  const [recentRefreshKey, setRecentRefreshKey] = useState(0);

  // ---- Load an existing run into the workbench (shared by deep-link, the
  // "查看示例分析" button, and the 近期运行 list). Resets the live trace cursor
  // and jumps to the report tab — same path as the ?run= deep link.
  const loadRun = useCallback((id: string): void => {
    runIdRef.current = id; // synchronous: in-flight old-run polls drop immediately
    setRunId(id);
    setEvents([]);
    setSinceSeq(0);
    setQaClaimId(null);
    setPollingError(false);
    setActiveTab('report');
  }, []);

  function handleViewHistory(claim: Claim): void {
    if (claim.id) setQaClaimId(claim.id);
    setActiveTab('qa-replay');
  }

  // Poll trace events when a run is active. Error handling lives INSIDE the
  // callback (not usePolling's onError) so it can be run-id guarded too: a
  // stale old-run poll — success OR failure — that resolves after a run switch
  // must not append events, advance the cursor, or raise the banner for the
  // newly selected run.
  usePolling(
    async () => {
      const rid = runId;
      if (!rid) return;
      try {
        const res = await getTrace(rid, sinceSeq);
        if (rid !== runIdRef.current) return; // run switched mid-flight; drop
        if (res.events.length > 0) {
          setEvents((prev) => mergeTraceEvents(prev, res.events));
          setSinceSeq(res.max_seq);
        }
        setPollingError(false);
      } catch {
        if (rid === runIdRef.current) setPollingError(true);
      }
    },
    runId !== null,
    2000,
  );

  async function handleSubmit(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    setFormError(null);
    const competitors = competitorsRaw
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    // Discovery Mode: competitors may be empty as long as a category is given —
    // the backend discovers them. Directed Mode: competitors provided.
    if (!category.trim() || !goal.trim()) {
      setFormError('品类与研究目标必填。竞品留空则进入 Discovery Mode（自动发现）。');
      return;
    }
    const discoveryMode = competitors.length === 0;
    // Live-run guard: a real collection takes 3–5 min and may yield a thin
    // report. Confirm before kicking it off so judges don't trigger it by
    // accident. The example/demo path stays one-click (no guard there).
    const confirmed = window.confirm(
      '实时采集约需 3-5 分钟，结果可能较薄。若只想快速查看完整效果，请改用「查看示例分析」。确定要发起实时分析吗？',
    );
    if (!confirmed) return;
    setSubmitting(true);
    try {
      const res = await createRun({
        category,
        competitors,
        goal,
        ...(domain ? { domain } : {}),
        ...(discoveryMode ? { market_scope: marketScope } : {}),
      });
      loadRun(res.run_id);
      // Refresh the 近期运行 list so the freshly created run shows up.
      setRecentRefreshKey((k) => k + 1);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Failed to create run');
    } finally {
      setSubmitting(false);
    }
  }

  const activeItem = NAV_ITEMS.find((item) => item.key === activeTab);

  return (
    <div className="min-h-screen bg-ink-50 text-ink-900 relative">
      {/* Ambient dot-grid — a faint static texture on the app canvas only. Every
          panel below is opaque/glass and sits ABOVE it (relative z-10), so text is
          never rendered directly on the dots (readability guardrail). */}
      <DotPattern aria-hidden className="fixed inset-0 z-0 text-ink-300" style={{ opacity: 0.45 }} gap={22} />

      {/* ---- Top bar (glass over the ambient grid) ---- */}
      <header className="glass-surface shadow-sm px-6 py-3 flex items-center gap-3 relative z-10">
        {/* Brand mark — a "mirror/lens" glyph in the accent color. */}
        <span className="flex items-center justify-center w-9 h-9 rounded-lg bg-mirror-50 ring-1 ring-mirror-100 flex-shrink-0">
          <svg className="w-6 h-6 text-mirror-600" viewBox="0 0 28 28" fill="none" aria-hidden="true">
            <circle cx="14" cy="14" r="11" stroke="currentColor" strokeWidth="2" />
            <circle cx="14" cy="14" r="5" fill="currentColor" />
            <path d="M9 9.5a6 6 0 0 1 4-2.2" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </span>
        <div className="flex flex-col leading-none gap-1">
          <div className="flex items-baseline gap-2">
            <span className="font-serif font-semibold text-xl text-ink-900 leading-none">明镜</span>
            <span className="font-semibold text-sm text-ink-500 leading-none tracking-tight">
              MingJing · Evidence Runtime
            </span>
          </div>
          <span className="text-[11px] text-ink-400 leading-none">
            证据驱动的竞品分析 · 多 Agent 协作可信闭环
          </span>
        </div>
        {runId && (
          <Badge
            variant="outline"
            className="ml-auto font-mono text-ink-500 bg-ink-50 gap-1.5"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-mirror-500" aria-hidden="true" />
            run: {runId}
          </Badge>
        )}
      </header>

      {/* Connection-error banner — shown when polling fails; auto-clears on success */}
      {pollingError && (
        <div className="bg-amber-50 border-b border-amber-200 px-6 py-1.5 text-xs text-amber-700 flex items-center gap-2 relative z-10">
          <span>Connection error, retrying…</span>
        </div>
      )}

      <div className="flex relative z-10" style={{ height: 'calc(100vh - 57px)' }}>
        {/* ---- Left: collapsible run panel + vertical nav ---- */}
        <div className="flex flex-shrink-0 h-full">

          {/* Collapsible run panel */}
          <aside
            className="panel-width-transition border-r border-ink-200 bg-ink-100 flex flex-col h-full overflow-hidden flex-shrink-0"
            style={{ width: runPanelOpen ? panelWidth : 40 }}
            aria-expanded={runPanelOpen}
          >
            <div className="relative h-full min-w-10">
              {/* Collapsed rail */}
              <div
                className={[
                  'absolute inset-y-0 left-0 w-10 flex flex-col items-center py-3 panel-content-fade',
                  runPanelOpen ? 'opacity-0 pointer-events-none' : 'opacity-100',
                ].join(' ')}
                aria-hidden={runPanelOpen}
                inert={runPanelOpen}
              >
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={() => setRunPanelOpen(true)}
                  className="h-7 w-7 text-ink-400 hover:text-ink-700"
                  title="展开运行面板"
                  aria-label="展开运行面板"
                >
                  <ChevronRight className="w-4 h-4" />
                </Button>
                <span
                  className="mt-3 text-xs text-ink-400 font-medium"
                  style={{ writingMode: 'vertical-rl', textOrientation: 'mixed' }}
                >
                  运行
                </span>
              </div>

              {/* Full panel content */}
              <div
                className={[
                  'panel-content-fade flex h-full flex-col overflow-y-auto min-h-0',
                  runPanelOpen ? 'opacity-100' : 'opacity-0 pointer-events-none',
                ].join(' ')}
                style={{ width: panelWidth }}
                aria-hidden={!runPanelOpen}
                inert={!runPanelOpen}
              >
                {/* Panel header with collapse button */}
                <div className="flex items-center justify-between px-4 py-3 border-b border-ink-100">
                  <span className="text-sm font-semibold text-ink-700">运行</span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => setRunPanelOpen(false)}
                    className="h-7 w-7 text-ink-400 hover:text-ink-700"
                    title="收起运行面板"
                    aria-label="收起运行面板"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </Button>
                </div>

                {/* 查看分析 — one-click example + recent-runs list (above the form) */}
                <RecentRuns onLoadRun={loadRun} refreshKey={recentRefreshKey} />

                {/* Run input form (LIVE collection) */}
                <div className="p-4 border-b border-ink-100">
                  <h2 className="text-sm font-semibold text-ink-700 mb-1">
                    发起实时分析（联网采集）
                  </h2>
                  <form onSubmit={(e) => { void handleSubmit(e); }} className="space-y-3">
                    <div className="space-y-1.5">
                      <Label htmlFor="category" className="text-xs text-ink-500">
                        Category
                      </Label>
                      <Input
                        id="category"
                        type="text"
                        value={category}
                        onChange={(e) => setCategory(e.target.value)}
                        placeholder="e.g. Cloud Storage"
                      />
                    </div>
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <Label htmlFor="competitors" className="text-xs text-ink-500">
                          Competitors（逗号分隔，可留空）
                        </Label>
                        {competitorsRaw.trim() === '' && (
                          <span
                            data-testid="discovery-mode-badge"
                            className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-mirror-50 text-mirror-600 ring-1 ring-mirror-100"
                          >
                            Discovery Mode
                          </span>
                        )}
                      </div>
                      <Input
                        id="competitors"
                        type="text"
                        value={competitorsRaw}
                        onChange={(e) => setCompetitorsRaw(e.target.value)}
                        placeholder="留空 = 自动发现竞品；或填写 e.g. AWS, Azure, GCP"
                      />
                    </div>
                    {/* Market scope — only relevant to Discovery Mode (empty competitors). */}
                    {competitorsRaw.trim() === '' && (
                      <div className="space-y-1.5">
                        <Label htmlFor="market-scope" className="text-xs text-ink-500">
                          市场范围 / Market scope
                        </Label>
                        <select
                          id="market-scope"
                          data-testid="market-scope-select"
                          value={marketScope}
                          onChange={(e) => setMarketScope(e.target.value)}
                          className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-xs transition-colors focus-visible:outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring"
                        >
                          <option value="global">全球 / Global</option>
                          <option value="china">中国 / China</option>
                        </select>
                      </div>
                    )}
                    <div className="space-y-1.5">
                      <Label htmlFor="goal" className="text-xs text-ink-500">
                        Research Goal
                      </Label>
                      <Textarea
                        id="goal"
                        value={goal}
                        onChange={(e) => setGoal(e.target.value)}
                        rows={2}
                        placeholder="e.g. Compare pricing for 1TB/month"
                        className="resize-none"
                      />
                    </div>
                    {domains.length > 0 && (
                      <div className="space-y-1.5">
                        <Label htmlFor="domain" className="text-xs text-ink-500">
                          领域 / Domain
                        </Label>
                        {/* Native <select> kept intentionally: the test suite drives
                            it via getByRole('option') + fireEvent.change, which a
                            Radix portal-based select would break. */}
                        <select
                          id="domain"
                          data-testid="domain-select"
                          value={domain}
                          onChange={(e) => setDomain(e.target.value)}
                          className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-xs transition-colors focus-visible:outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring"
                        >
                          {domains.map((d) => (
                            <option key={d} value={d}>
                              {d}
                            </option>
                          ))}
                        </select>
                      </div>
                    )}
                    {formError && (
                      <p className="text-xs text-destructive">{formError}</p>
                    )}
                    <Button type="submit" disabled={submitting} className="w-full">
                      {submitting ? 'Starting…' : '开始实时分析'}
                    </Button>
                    <p className="text-xs leading-snug text-ink-400">
                      “开始分析”会实时联网采集（约 3–5 分钟）。想快速看效果，点上方“查看示例分析”。
                    </p>
                  </form>
                </div>

                {/* Discovery-Mode result (renders only when a run discovered competitors) */}
                <DiscoveredCompetitors events={events} />

                {/* Activity feed */}
                <div className="shrink-0 p-4">
                  <h2 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-400 mb-3">
                    <Activity className="w-3.5 h-3.5" />
                    Activity Feed
                  </h2>
                  <ActivityFeed events={events} live={runId !== null} />
                </div>
              </div>
            </div>
          </aside>

          {/* Vertical nav */}
          <nav
            className="w-32 border-r border-ink-200 bg-ink-100 flex flex-col py-4 h-full"
            aria-label="工作台导航"
          >
            {/* reducedMotion="user" makes the layout spring honor
                prefers-reduced-motion (parity with the CSS-driven animations). */}
            <MotionConfig reducedMotion="user">
            <LayoutGroup>
              {NAV_ITEMS.map(({ key, label, icon: Icon }) => {
                const active = activeTab === key;
                return (
                  <button
                    key={key}
                    type="button"
                    data-testid={`nav-${key}`}
                    onClick={() => setActiveTab(key)}
                    aria-current={active ? 'page' : undefined}
                    className={[
                      'group relative overflow-hidden flex items-center gap-2.5 w-full text-left px-3 py-2.5 text-sm font-medium transition-colors border-l-2',
                      active
                        ? 'border-mirror-600 text-mirror-700'
                        : 'border-transparent text-ink-600 hover:text-ink-900 hover:bg-ink-50',
                    ].join(' ')}
                  >
                    {active && (
                      <motion.span
                        layoutId="nav-active"
                        className="absolute inset-0 bg-mirror-50 rounded-sm"
                        style={{ originY: '0px' }}
                        transition={{ type: 'spring', stiffness: 400, damping: 35 }}
                      />
                    )}
                    <Icon
                      className={[
                        'relative z-10 w-4 h-4 flex-shrink-0 transition-colors',
                        active ? 'text-mirror-600' : 'text-ink-400 group-hover:text-ink-600',
                      ].join(' ')}
                    />
                    <span className="relative z-10">{label}</span>
                  </button>
                );
              })}
            </LayoutGroup>
            </MotionConfig>
          </nav>
        </div>

        <div
          onPointerDown={handlePointerDown}
          onKeyDown={(e) => {
            if (e.key === 'ArrowLeft') { e.preventDefault(); nudge(-16); }
            else if (e.key === 'ArrowRight') { e.preventDefault(); nudge(16); }
          }}
          tabIndex={0}
          role="separator"
          aria-orientation="vertical"
          aria-label="调整运行面板宽度（左右方向键微调）"
          aria-valuemin={minWidth}
          aria-valuemax={maxWidth}
          aria-valuenow={Math.round(panelWidth)}
          className="w-1 h-full cursor-col-resize bg-transparent hover:bg-mirror-600/30 focus-visible:bg-mirror-600/50 focus:outline-none transition-colors duration-150 flex-shrink-0 touch-none"
        />

        {/* ---- Main content area ---- */}
        <main className="flex-1 flex flex-col overflow-hidden">
          {/* KPI bar — keyed by runId so it remounts (fresh state) on a run
              switch; combined with the per-component guards this guarantees no
              previous-run data renders or leaks under the newly selected run. */}
          <KpiBar key={runId ?? 'no-run'} runId={runId} />
          <CredibilityPanel runId={runId} />

          {/* Per-tab description bar — one-line explainer for the active tab,
              plus a persistent evidence legend so the trust system is
              self-explaining at a glance (no hover required). */}
          <div className="bg-ink-100 border-b border-ink-200 px-6 py-2.5 flex items-center gap-4 flex-wrap">
            <span data-testid="tab-description" className="text-sm leading-snug text-ink-500">
              {activeItem?.description}
            </span>
            <div className="ml-auto shrink-0">
              <EvidenceLegend />
            </div>
          </div>

          {/* Tab content */}
          <div className="flex-1 overflow-y-auto p-6">
            {/* BlurFade keyed by tab → a quick reveal on every tab switch (motion
                on state change, not idle). Each view is ALSO keyed by runId so
                switching runs fully remounts it with fresh state — no committed
                render or in-flight fetch from a previous run can surface under
                the newly selected run id. */}
            <BlurFade key={activeTab} duration={0.3} offset={8}>
              {activeTab === 'report' && (
                <FinalReport
                  key={runId ?? 'no-run'}
                  runId={runId}
                  events={events}
                  pollingError={pollingError}
                  onViewHistory={handleViewHistory}
                  onSeeClosedLoop={() => setActiveTab('qa-replay')}
                />
              )}

              {activeTab === 'schema' && (
                <SchemaMatrix key={runId ?? 'no-run'} runId={runId} />
              )}

              {activeTab === 'evidence' && (
                <EvidenceAndQA key={runId ?? 'no-run'} runId={runId} events={events} />
              )}

              {activeTab === 'qa-replay' && (
                <QAReplay
                  key={runId ?? 'no-run'}
                  runId={runId}
                  claimId={qaClaimId}
                  events={events}
                  live={runId !== null}
                />
              )}

              {activeTab === 'trace' && (
                <Suspense
                  fallback={
                    <div className="flex-1 animate-pulse rounded-xl bg-ink-900/40 min-h-[320px]" />
                  }
                >
                  <ExecutionTrace key={runId ?? 'no-run'} runId={runId} />
                </Suspense>
              )}

              {activeTab === 'observability' && (
                <Suspense
                  fallback={
                    <div className="flex-1 animate-pulse rounded-xl bg-ink-900/40 min-h-[320px]" />
                  }
                >
                  <Observability key={runId ?? 'no-run'} runId={runId} />
                </Suspense>
              )}
            </BlurFade>
          </div>
        </main>
      </div>
    </div>
  );
}
