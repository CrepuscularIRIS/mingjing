/**
 * Canonical run fixture — exported from the live MingJing app DB (run 4fff4227).
 * Every on-screen number/label in the film traces to this run, which a judge can
 * open at http://localhost:5173/?run=4fff4227cdce4661a654603566a0385e.
 * See docs/SPEC.md §4. DO NOT invent figures here.
 */

export type Tier = "strong" | "moderate" | "weak";

export const RUN = {
  id: "4fff4227cdce4661a654603566a0385e",
  shortId: "4fff4227",
  category: "AI 产品竞品分析",
  goal: "对比 Notion vs Linear 的定价、用户画像、功能与 SWOT",
  competitors: ["Notion", "Linear"] as const,
  market: "中国 / 全球",
} as const;

/** Header KPI chips (mirrors KpiBar / CredibilityPanel). */
export const KPI = {
  proposed: 10,
  admitted: 6,
  withheld: 4,
  strong: 1,
  moderate: 5,
  weak: 0,
  coverage: 0.8, // 80% — swot honestly uncovered, self-disclosed in 情报缺口
  citation: 1.0, // 100%
  repairDelta: 0.423, // +42% groundedness repair (is_tier_upgrade = true)
  qaRounds: 4,
  avgSourceStrength: 1.0,
  // From live /metrics on 4fff4227: elapsed 1385.8s = 23分6秒, speedup 42–104×,
  // 33 sources. (Earlier 17min/57–142× was a DIFFERENT run's header — fixed.)
  durationLabel: "23 分 6 秒",
  baselineLabel: "16–40 小时",
  speedupLabel: "约 42–104×",
  sourceCount: 33,
  independentDomains: 7,
} as const;

/**
 * Honesty hard-numbers (defense narrative §5.5) — every figure has a
 * reproducible source command. These are what make "可信" concrete.
 */
export const VALIDATION = {
  verbatim: { snippets: "39/39", claims: "10/10", label: "两标杆 run · 全部准入结论逐字复核命中率", source: "scripts/audit_verbatim.py" },
  calibration: { cases: 43, metric: "P / R / acc = 1.00", label: "QA 门 admit/withhold 校准集（6 类 IssueCode 全覆盖）", source: "tests/test_qa_calibration.py" },
  qaEvents: { fail: 28, pass: 3, label: "高幻觉压测模型下，质检持续工作（拒绝与通过都留痕）" },
  providerAgnostic: {
    stress: "MiniMax-M2.7 · 高幻觉压力测试",
    contest: "官方豆包 Doubao-Seed-2.0-lite 实跑验证",
    contestRun: "33835db0",
    contestDetail: "18 次调用全为官方 EP · 5 提议→1 准入（强档，逐字 100%）· +20% 档位跃升",
  },
} as const;

/** The 10 proposed claims → 6 admitted (pass) / 4 withheld (draft). */
export interface ClaimRow {
  competitor: string;
  field: string; // Chinese label
  tier: Tier;
  admitted: boolean;
}
export const CLAIMS: ClaimRow[] = [
  { competitor: "Linear", field: "定价模式", tier: "strong", admitted: true },
  { competitor: "Linear", field: "功能树", tier: "moderate", admitted: true },
  { competitor: "Linear", field: "用户画像", tier: "moderate", admitted: true },
  { competitor: "Linear", field: "用户口碑", tier: "moderate", admitted: true },
  { competitor: "Linear", field: "SWOT", tier: "moderate", admitted: false },
  { competitor: "Notion", field: "功能树", tier: "moderate", admitted: true },
  { competitor: "Notion", field: "用户口碑", tier: "moderate", admitted: true },
  { competitor: "Notion", field: "定价模式", tier: "moderate", admitted: false },
  { competitor: "Notion", field: "SWOT", tier: "strong", admitted: false },
  { competitor: "Notion", field: "用户画像", tier: "strong", admitted: false },
];

/** The two real repair arcs that ended admitted — the money-shot. */
export const ARCS = {
  // Primary arc: weak → moderate (Notion 用户口碑)
  primary: {
    competitor: "Notion",
    field: "用户口碑",
    rejectCode: "WEAK_EVIDENCE",
    rejectReason: "证据偏弱 · 仅 2 个来源，未达「中」档的独立交叉印证",
    from: {
      tier: "weak" as Tier,
      sources: 2,
      statement:
        "根据调查数据，Notion 用户整体满意度较高，用户赞赏其灵活性，但部分用户认为移动应用程序运行缓慢。",
    },
    to: {
      tier: "moderate" as Tier,
      sources: 4,
      statement:
        "Notion 用户满意度整体较高，用户赞赏其灵活性，但也有用户反映移动应用较慢、界面过于复杂且缺乏离线功能。",
    },
  },
  // Secondary arc: moderate → strong (Linear 定价)
  secondary: {
    competitor: "Linear",
    field: "定价模式",
    from: { tier: "moderate" as Tier, sources: 2 },
    to: { tier: "strong" as Tier, sources: 4 },
  },
} as const;

/** Rule shown under the money-shot. */
export const TIER_RULE = "中 = 2 个及以上相互独立的来源相互印证；强 = 含权威官方来源";

/** BLUF + SWOT (Notion) for the report scene — verbatim from synthesis. */
export const BLUF =
  "Notion 用户整体满意度较高但移动应用体验有待提升；Linear 用户评价积极且强调 AI 驱动的协作工作流。两者在功能深度与灵活性上仍有改进空间。";

export const SWOT = {
  strengths: [
    "用户满意度整体较高，因灵活性受到好评",
    "功能树以数据库与模板为核心，支持任务、路线图、设计仓库",
    "功能覆盖广泛，可自定义工作空间",
  ],
  weaknesses: [
    "移动应用较慢、界面过于复杂、缺乏离线功能",
    "功能树未涉及 AI 驱动工作流（Linear 已作为核心）",
    "界面复杂导致学习成本较高",
  ],
} as const;

/** Linear pricing tiers (strong claim) — for the comparison/evidence scene. */
export const PRICING_LINEAR = [
  "免费版 $0",
  "基础版 $10 / 用户 / 月",
  "成长版 $16 / 用户 / 月",
  "企业定制版",
] as const;

/** Evidence example (Linear 定价 strong claim → its cited sources). */
export const EVIDENCE_EXAMPLE = {
  claim:
    "Linear 采用简单的按座位计费模式，提供四个订阅层级：免费版（$0）、基础版（$10/用户/月）、成长版（$16/用户/月）和企业定制版，支持按年计费。",
  tier: "strong" as Tier,
  field: "Linear · 定价模式",
  sources: [
    {
      url: "https://linear.app/pricing",
      kind: "官方",
      admiralty: "B2",
      badge: "LIVE" as const,
      snippet:
        "Free $0 Free for everyone. Unlimited members. 2 teams. 250 issues. Basic $10 per user/month. Billed yearly…",
    },
    {
      url: "https://costbench.com/software/developer-tools/linear/",
      kind: "第三方",
      admiralty: "D2",
      badge: "CACHED" as const,
      snippet:
        "Linear uses a simple per-seat model with four tiers: a Free plan for small teams, a paid Basic plan, a Business plan…",
    },
    {
      url: "survey:SV-2 / pricing_model",
      kind: "问卷",
      admiralty: "D1",
      badge: "SNIPPET" as const,
      snippet:
        "Most surveyed Linear users are on the Basic plan at $10 per user/month and consider it fair value…",
    },
  ],
} as const;

/** Agent DAG nodes (Collector → Analyst → QA → Writer). */
export const DAG = [
  { id: "collect", label: "采集", en: "Collector", desc: "联网检索 · robots 校验 · SSRF 防护 · 证据切片", pure: false },
  { id: "analyze", label: "分析", en: "Analyst", desc: "每字段一次 LLM · 注入隔离信封", pure: false },
  { id: "qa", label: "质检", en: "QA", desc: "7 类确定性校验 · 无 LLM · 提案/裁定分离", pure: true },
  { id: "write", label: "撰写", en: "Writer", desc: "仅投影 QA 通过的结论", pure: true },
] as const;
