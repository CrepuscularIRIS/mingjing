# 明镜 MingJing · 演示视频交付报告（Video Delivery Report）

> 本文件是 `mingjing-video/` 这支演示视频的交付说明，配合 `mingjing/SUBMISSION.md`
> （评委唯一入口）阅读。视频用于填补提交清单中的「演示视频链接」一项。

## 1. 是什么

- **类型**：产品介绍 / 宣传演示片（Remotion 程序化生成，React → MP4）。
- **规格**：`out/mingjing-launch.mp4` · **1920×1080 · 30fps · H.264 · ≈6 分 16 秒**。
- **核心特征**：**前端案例全部是真实产品页面截图**（两条真实 run 实跑，非重绘 UI），
  叠加电影级运镜（聚光灯 / 纵向平移 / 推近）+ 烧录中文字幕。设计页按
  `mingjing/docs/DESIGN.md` 的暗色情报终端刻度制作。
- **两个案例 + 全部 6 个页面**：
  - **案例一 · 单一竞品 Notion**（run `3775d21a`）：报告 / QA 回放（定价 弱1→中5，+38%）/ 执行轨迹。
  - **案例二 · 竞品对比 Notion × Linear**（run `4fff4227`）：报告 / 可信度 / QA 钱镜头（双弧线 +42%）/ 证据溯源 / Schema 矩阵 / 可观测。
  - 6 个产品页面（分析报告 / Schema 矩阵 / 证据&溯源 / QA 回放 / 执行轨迹 / 可观测）全部出现。
- **片头**：采用既有品牌封面，从当前 `docs/presentation/cover.html` 重新渲染（`cap-cover.png`，
  显示 **+42% / 4fff4227**，与答辩 deck/cover 同源、与正片数字一致）。
- **输入场景**：真实「发起实时分析」表单截图，已填入案例二的真实输入。

## 2. 章节结构（12 章 · 对齐答辩主线）

主线 = `DEFENSE-NARRATIVE.md` 的灵魂句：**「明镜不是写报告的 AI，而是一个会拒绝不可靠结论、
会补证、会留下审计链的竞品分析工作台——它知道自己什么时候不该自信。」**

| # | 章节 | 类型 | 对应 P0 验收 / 硬数字 |
|---|------|------|----------------------|
| 00 | 开场（真实品牌封面） | 品牌 | thesis |
| 01–03 | 问题 / 产品构建思路 / 系统架构 | 设计页 | §1 / §3① / — |
| 04 | 输入场景（**真实表单**，已填案例二输入） | 🟢 真实页面 | 验收 1 |
| 05 | Agent 协作 DAG | 设计页 | 验收 6 |
| 06 | **案例一 章节卡** + 报告 / QA回放(弱1→中5,+38%) / 执行轨迹 | 🟢 真实页面 ×3 | 验收 2/4/6 |
| 07 | **案例二 章节卡** + 报告 / 可信度(+42%,漏斗10→6) / QA钱镜头(双弧线) / 证据溯源 / Schema矩阵 / 可观测 | 🟢 真实页面 ×6 | 验收 2/3/4/5/7/6 |
| 08 | 诚实性硬证据（逐字 100% · 校准 P/R/acc=1.00 · 豆包实跑） | 设计页 | §5.5 硬数字卡 |
| 09 | 业务价值（16–40h → 23分6秒 · 42–104×） | 设计页 | 验收 8 / §2 |
| 10 | 收尾 | 设计页 | thesis |

> 章节顺序与时长的唯一事实源 = `src/timeline.ts`（20 个 `Series.Sequence`）。
> 真实页面运镜：案例一 + Schema/可观测用「推近」（无叠加，零错位风险）；案例二的
> 可信度/QA/证据用「聚光灯」，坐标按真实 DOM `getBoundingClientRect` 标定。

## 3. 数据真实性（每个数字都可溯）

所有屏上数字均来自**真实运行 `4fff4227`**（Notion×Linear 中文矩阵），直接读自
`mingjing/data/mingjing.db` 与 live API `/runs/4fff…/{credibility,metrics,report}`：

- 10 提议 → **6 准入 · 4 留存** · 强1·中5·弱0
- **+42%** 修正增益（repair_delta 0.423，真闭环印章点亮）
- 双弧线：用户口碑 **弱(2源)→中(4源)** · Linear 定价 **中(2源)→强(4源)**
- 覆盖率 80% · 引用率 100% · 33 来源 · **耗时 23分6秒** · 约 **42–104×**（估算基线 16–40h）
- 诚实性硬数字（`DEFENSE-NARRATIVE.md §5.5`）：逐字复核 39/39 片段 · 10/10 结论 = 100%；
  QA 校准集 43 例 P/R/acc=1.00；门禁 provider-agnostic（MiniMax 高幻觉压测 + 官方豆包
  Doubao-Seed 实跑 run `33835db0`）。

> 修正记录：早期草稿误用了另一 run 的 17min/57–142×，已按 live `/metrics` 改为
> **23分6秒 / 42–104×**。诚实主题的片子不容许数字漂移。

## 4. 如何生成 / 复现

```bash
cd mingjing-video
npm install            # 一次性
npm run render         # → out/mingjing-launch.mp4
npm run dev            # Remotion Studio 实时预览
```

**重新采集真实页面截图**（如 UI 更新）：起 `make api`(:8000) + `make web`(:5173) →
浏览器开 `localhost:5173/?run=4fff4227…` → 收起运行面板 → 逐个点 `nav-*` 标签截 1920×1080 →
存到 `public/shots/`。聚光灯坐标在各 `src/scenes/*Scene.tsx`，**用真实 DOM `getBoundingClientRect`
标定**（不是估算），UI 改版后需重新量。

**旁白 = edge-tts 自动生成（已就绪并已嵌入成片）**：
```bash
./scripts/gen_tts.sh            # 逐章 TTS → public/audio/vo/<id>.mp3（无 API Key，需联网）
./scripts/render_with_audio.sh  # 自动检测并嵌入，渲染带声音 MP4
```
机制：**逐章音频**放进每章 `<Series.Sequence>`，旁白随场景播放、纯视觉段自然停顿——
天然对齐字幕与画面，无累积漂移；实测每章音频短于其场景时长（不裁切）。脚本检测到
`public/audio/vo/` 就用 `--props='{"hasVoiceover":true}'` 自动启用，否则渲染静音版（字幕已烧录，
永不失败）。逐字稿见 `docs/VOICEOVER.md`；换音色 `VOICE=zh-CN-XiaoxiaoNeural`；可选背景乐
`public/audio/bgm.mp3`（默认极低音量 0.05）；想替换某章为真人录音，覆盖同名 mp3 即可。

## 5. 工程要点

- 标准排版来源 = 真实前端（`mingjing/docs/DESIGN.md`：Bloomberg/Palantir 暗色情报终端）。
- 结构单一事实源 `src/timeline.ts`（章节/时长/字幕/进度条）。
- 真实数据 fixture `src/data/run.ts`（从 app DB 导出）。
- 组件套件 `src/components/`：`ShotScene`（真实截图 + 运镜/聚光灯，三种模式 contain/panY/spotlight）、
  `Chapter`、`primitives`、`Overlays`（字幕 + 章节进度条）。
- 独立工程，**不改动** `mingjing/` 应用本身。

## 6. 状态与已知项

- ✅ `tsc --noEmit` clean；20 章关键帧逐一目检；聚光灯按真实坐标校准对齐。
- ✅ 片头封面与正片**数字一致**：从当前 `docs/presentation/cover.html` 重新渲染为
  `cap-cover.png`，显示 **+42% / run 4fff4227**。
- ✅ 旁白已用 edge-tts 逐章生成并嵌入成片（见 §4）；如需真人配音可覆盖同名 mp3。

---
*Generated for the ByteDance CIS competition submission. 配合 `mingjing/SUBMISSION.md` 阅读。*
