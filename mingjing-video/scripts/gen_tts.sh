#!/usr/bin/env bash
# Generate per-chapter Chinese voiceover via edge-tts (no API key; needs network).
# One mp3 per chapter id → public/audio/vo/<id>.mp3, so narration aligns to each
# scene when placed inside its <Series.Sequence>. Text mirrors timeline.ts cues.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p public/audio/vo
VOICE="${VOICE:-zh-CN-YunxiNeural}"
RATE="${RATE:-+8%}"

gen() { # id  text
  echo "→ $1"
  edge-tts --voice "$VOICE" --rate="$RATE" --text "$2" --write-media "public/audio/vo/$1.mp3" >/dev/null 2>&1 || echo "  ! failed: $1"
}

gen title       "明镜 MingJing，可溯源竞品分析 Agent。"
gen problem     "普通 Deep Research 给你一份只能选择相信的报告；明镜给你一份可以审计、可以打回、可以追溯的报告。目标不是让 AI 更自信，而是让它知道，什么时候不该自信。"
gen approach    "它的核心做法，是把提案和裁定分开：大模型提出结论，确定性的质检规则裁定真值。证据强度只有强、中、弱三档，没有可信度小数。撰写器只投影通过质检的结论，没通过的不进报告。"
gen architecture "后端是 FastAPI 加 LangGraph 状态图，全程留痕的 SQLite；前端是六标签的情报工作台，每两秒轮询轨迹；采集层多引擎检索，带 robots 与 SSRF 防护。"
gen input       "使用很简单：填一个品类、竞品和研究目标就能启动，竞品留空就自动发现。本片的案例输入是，AI 产品竞品分析，Notion 和 Linear。"
gen dag         "调研由采集、分析、质检、撰写四类智能体协作完成，传递的是结构化消息，而不是自由聊天。质检不通过，就回边重新取证、再分析，通过了才撰写。"
gen case1       "先看第一个案例，对单一竞品 Notion 的分析。"
gen n1report    "报告以核心结论开头，再到 SWOT、定价、用户画像和功能，每一句都能溯源。"
gen n1qa        "定价这条结论，第一轮证据里根本没有定价信息，被判为弱、当场打回。系统重新取证，补了四个来源，复核升级为中。来源从一个变成五个，可信度从弱到中，修正增益百分之三十八。"
gen n1trace     "整个过程在执行轨迹里可以回放：采集、分析、质检、打回重采的回边、撰写、综合，每个节点按角色着色。"
gen case2       "再看第二个案例，Notion 和 Linear 的竞品对比，中文报告。"
gen report      "核心结论开头，再到 SWOT，到竞品对比矩阵。每一句结论末尾的引用，都能就地打开证据。"
gen credibility "这一次修正增益是百分之四十二，真闭环确认的印章点亮。覆盖率百分之八十，引用率百分之百。十条提议，质检只准入六条，留下四条并写明原因，强一、中五、弱零。"
gen qareplay    "钱镜头在这里。用户口碑第一轮只有两个来源、被判为弱，打回；重新取证到四个来源，升级为中。同一个闭环里，Linear 的定价从中升到强。这是真实的闭环，不是模型自评。"
gen evidence    "每条结论都能点开，看到原始链接、原文片段、内容哈希，来源出处徽标和 Admiralty 分级，以及质检的判定。没通过的，以暂存保留，不会被偷偷删除。"
gen schema      "Schema 矩阵，把竞品、字段、证据强度排成一张表，未覆盖的字段如实留空。"
gen observ      "可观测里，每个智能体的调用次数和 Token 都有记录，可以逐节点审计它的提示词和输出。"
gen validation  "这些都可以复现地验证：全部准入结论、三十九个引用片段，逐字复核百分之百命中；质检校准集四十三例，准确率百分之百。门禁模型无关，MiniMax 压测加官方豆包实跑。"
gen business    "一份人工需要十几到几十小时的竞品调研，明镜这次二十三分钟完成，约四十二到一百零四倍提速，全程可回放。"
gen final       "明镜的目标，不是让 AI 更自信，而是让它知道，什么时候不该自信。"

echo "✓ per-chapter voiceover in public/audio/vo/"
ls -1 public/audio/vo/ | wc -l
