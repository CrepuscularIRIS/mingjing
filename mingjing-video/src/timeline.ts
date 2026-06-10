/**
 * Single source of truth for the film's structure: chapter order, durations,
 * titles, and burned-in caption cues. The composition (MingJingLaunch), the
 * captions overlay, and the chapter-progress bar all read from here.
 *
 * Two case studies (Notion-only run 3775d21a + Notion×Linear run 4fff4227) and
 * all six product pages (报告/Schema/证据/QA/执行轨迹/可观测). Target ≈ 6:16.
 */
export const FPS = 30;
export const sec = (s: number) => Math.round(s * FPS);

/** A burned-in caption cue, timed relative to its chapter's start. */
export interface Cue {
  atSec: number;
  text: string;
}

export interface ChapterDef {
  id: string;
  index: string; // "01"…
  eyebrow: string;
  title: string;
  durSec: number;
  cues: Cue[];
}

export const CHAPTERS: ChapterDef[] = [
  {
    id: "title",
    index: "00",
    eyebrow: "MINGJING",
    title: "开场",
    durSec: 12,
    cues: [{ atSec: 1.5, text: "明镜 MingJing · 可溯源竞品分析 Agent" }],
  },
  {
    id: "problem",
    index: "01",
    eyebrow: "问题",
    title: "为什么需要明镜",
    durSec: 20,
    cues: [
      { atSec: 1, text: "普通 Deep Research：给你一份只能选择「相信」的报告" },
      { atSec: 8, text: "明镜：给你一份可以「审计」、可以打回、可以追溯的报告" },
      { atSec: 14, text: "目标不是让 AI 更自信，而是让它知道何时不该自信" },
    ],
  },
  {
    id: "approach",
    index: "02",
    eyebrow: "产品构建思路",
    title: "LLM 负责提案，确定性代码负责裁定",
    durSec: 26,
    cues: [
      { atSec: 1, text: "提案与裁定分离：LLM 提结论，确定性 QA 裁定真值" },
      { atSec: 9, text: "证据强度只有透明三档：强 / 中 / 弱，没有可信度小数" },
      { atSec: 18, text: "Writer 只投影 QA 通过的结论，未过准入不进报告" },
    ],
  },
  {
    id: "architecture",
    index: "03",
    eyebrow: "系统架构",
    title: "前端 · 后端 · Agent 编排 · 数据层",
    durSec: 26,
    cues: [
      { atSec: 1, text: "后端：FastAPI + LangGraph 状态图，append-only SQLite" },
      { atSec: 10, text: "前端：React 19 + Vite，6 标签 BI 工作台，2s 轮询 trace" },
      { atSec: 18, text: "采集层：多引擎检索 · robots/SSRF 防护 · 证据缓存" },
    ],
  },
  {
    id: "input",
    index: "04",
    eyebrow: "输入场景",
    title: "一个市场方向即可启动",
    durSec: 18,
    cues: [
      { atSec: 1, text: "真实表单：品类 + 竞品 + 目标即可启动（竞品留空 = 自动发现）" },
      { atSec: 9, text: "本片案例输入：AI 产品竞品分析 · Notion, Linear" },
    ],
  },
  {
    id: "dag",
    index: "05",
    eyebrow: "Agent 协作",
    title: "Collector → Analyst → QA → Writer",
    durSec: 24,
    cues: [
      { atSec: 1, text: "四类 Agent 协作，传递结构化消息，而非自由聊天" },
      { atSec: 9, text: "QA 打回 → 回边重新取证 → 再分析 → 通过才撰写" },
      { atSec: 17, text: "DAG 迭代闭环：采集 · 分析 · 质检 · 撰写 · 综合" },
    ],
  },

  /* ---- 案例一 · Notion 单一竞品（3775d21a）---- */
  {
    id: "case1",
    index: "06",
    eyebrow: "案例一",
    title: "单一竞品分析 · Notion",
    durSec: 6,
    cues: [{ atSec: 0.5, text: "案例一 · 单一竞品分析 Notion（run 3775d21a）" }],
  },
  {
    id: "n1report",
    index: "06",
    eyebrow: "案例一 · 报告",
    title: "Notion 单品报告",
    durSec: 16,
    cues: [{ atSec: 1, text: "Notion 单品报告：BLUF + SWOT + 定价/用户画像/功能，每句可溯源" }],
  },
  {
    id: "n1qa",
    index: "06",
    eyebrow: "案例一 · QA 回放",
    title: "定价 弱1 → 中5",
    durSec: 24,
    cues: [
      { atSec: 1, text: "PASS 1 · 定价 初判：弱（1 源）「证据中无定价信息」→ 打回" },
      { atSec: 10, text: "重新取证 +4 来源 → PASS 2 · 复核 中（5 源）" },
      { atSec: 17, text: "来源 1 → 5 · 弱 → 中 · 修正增益 +38%（真实闭环）" },
    ],
  },
  {
    id: "n1trace",
    index: "06",
    eyebrow: "案例一 · 执行轨迹",
    title: "执行轨迹 DAG",
    durSec: 16,
    cues: [{ atSec: 1, text: "执行轨迹 DAG：采集→分析→质检→打回重采(回边)→撰写→综合，节点按角色着色" }],
  },

  /* ---- 案例二 · Notion × Linear（4fff4227）---- */
  {
    id: "case2",
    index: "07",
    eyebrow: "案例二",
    title: "竞品对比 · Notion × Linear",
    durSec: 6,
    cues: [{ atSec: 0.5, text: "案例二 · 竞品对比 Notion × Linear（run 4fff4227，中文矩阵）" }],
  },
  {
    id: "report",
    index: "07",
    eyebrow: "案例二 · 分析报告",
    title: "可溯源报告",
    durSec: 26,
    cues: [
      { atSec: 1, text: "BLUF 核心结论（衬线大字）→ SWOT → 竞品对比矩阵" },
      { atSec: 11, text: "Notion vs Linear：定价、用户画像、功能树、口碑" },
      { atSec: 19, text: "每一句结论末尾的引用 chip 都能就地打开证据" },
    ],
  },
  {
    id: "credibility",
    index: "07",
    eyebrow: "案例二 · 可信度",
    title: "准入与可信度",
    durSec: 22,
    cues: [
      { atSec: 1, text: "修正增益 +42% · 真闭环确认印章点亮" },
      { atSec: 9, text: "覆盖率 80% · 引用率 100% · 准入率 60%" },
      { atSec: 16, text: "准入漏斗 10 提议 → 6 准入 · 4 留存（标明原因）· 强1·中5·弱0" },
    ],
  },
  {
    id: "qareplay",
    index: "07",
    eyebrow: "案例二 · QA 钱镜头",
    title: "真实修复闭环",
    durSec: 30,
    cues: [
      { atSec: 1, text: "用户口碑 PASS 1 初判：弱（2 源）→ 打回" },
      { atSec: 11, text: "重新取证 +2 来源 → PASS 2 复核：中（4 源）· 已升级" },
      { atSec: 21, text: "同一闭环里 Linear 定价 中(2源) → 强(4源)；修正增益 +42%" },
    ],
  },
  {
    id: "evidence",
    index: "07",
    eyebrow: "案例二 · 证据溯源",
    title: "每条结论可追溯",
    durSec: 22,
    cues: [
      { atSec: 1, text: "点开任意结论 → 原始 URL · 原文片段 · 内容哈希" },
      { atSec: 9, text: "来源出处徽标：LIVE / CACHED / 快照；Admiralty 分级" },
      { atSec: 16, text: "右栏 QA 判定 · 采纳 / 驳回；未通过的以「暂存」保留" },
    ],
  },
  {
    id: "schema",
    index: "07",
    eyebrow: "案例二 · Schema 矩阵",
    title: "字段完整度",
    durSec: 14,
    cues: [{ atSec: 1, text: "Schema 矩阵：竞品 × 字段 × 证据强度；未覆盖字段如实留空（不掩盖）" }],
  },
  {
    id: "observ",
    index: "07",
    eyebrow: "案例二 · 可观测",
    title: "全链路可观测",
    durSec: 14,
    cues: [{ atSec: 1, text: "可观测：每个 Agent 的调用次数与 Token 全程留痕，可逐节点审计 prompt/输出" }],
  },

  {
    id: "validation",
    index: "08",
    eyebrow: "诚实性硬证据",
    title: "可被复现地验证，不是声称",
    durSec: 24,
    cues: [
      { atSec: 1, text: "两标杆 run 全部准入结论逐字复核：39/39 片段 · 10/10 结论 = 100%" },
      { atSec: 8, text: "QA 判定校准集 43 例：admit/withhold P/R/acc = 1.00" },
      { atSec: 15, text: "门禁 provider-agnostic：MiniMax 高幻觉压测 + 官方豆包 Doubao 实跑（run 33835db0）" },
      { atSec: 20, text: "诚实边界：是「被来源逐字支撑率」，不是「对世界为真率」" },
    ],
  },
  {
    id: "business",
    index: "09",
    eyebrow: "业务价值",
    title: "从十几小时，到二十几分钟",
    durSec: 18,
    cues: [
      { atSec: 1, text: "人工竞品调研约 16–40 小时（行业估算）" },
      { atSec: 8, text: "明镜本次 23 分 6 秒完成，约 42–104× 提速，全程可回放" },
    ],
  },
  {
    id: "final",
    index: "10",
    eyebrow: "MINGJING",
    title: "收尾",
    durSec: 12,
    cues: [
      { atSec: 1, text: "不只是一份报告，而是一条可审计的情报链路" },
      { atSec: 6, text: "明镜 — 让 AI 知道，什么时候不该自信" },
    ],
  },
];

export const TOTAL_SEC = CHAPTERS.reduce((a, c) => a + c.durSec, 0);
export const TOTAL_FRAMES = sec(TOTAL_SEC);

/** Absolute start (seconds) of each chapter, by index. */
export const chapterStartsSec = (): number[] => {
  const starts: number[] = [];
  let acc = 0;
  for (const c of CHAPTERS) {
    starts.push(acc);
    acc += c.durSec;
  }
  return starts;
};

/** All caption cues flattened to absolute frame ranges. */
export interface AbsCue {
  fromFrame: number;
  toFrame: number;
  text: string;
}
export const absoluteCues = (): AbsCue[] => {
  const starts = chapterStartsSec();
  const out: AbsCue[] = [];
  CHAPTERS.forEach((c, ci) => {
    const base = starts[ci];
    c.cues.forEach((cue, i) => {
      const from = sec(base + cue.atSec);
      const next = c.cues[i + 1];
      const to = next ? sec(base + next.atSec) : sec(base + c.durSec);
      out.push({ fromFrame: from, toFrame: to, text: cue.text });
    });
  });
  return out;
};
