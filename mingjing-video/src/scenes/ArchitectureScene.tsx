import React from "react";
import { Chapter } from "../components/Chapter";
import { DepthCard, Rise } from "../components/primitives";
import { colors, fontMono, fontSans } from "../theme";

const LAYERS = [
  {
    tag: "前端 FRONTEND",
    tech: "React 19 · Vite · TypeScript · Tailwind",
    desc: "6 标签 BI 工作台：分析报告 / Schema 矩阵 / 证据溯源 / QA 回放 / 执行轨迹 / 可观测。每 2 秒轮询 trace。",
  },
  {
    tag: "后端 BACKEND",
    tech: "FastAPI · 只读视图 + POST /runs",
    desc: "REST 接口暴露报告、可信度、证据、轨迹；run 级并发 worker 线程，单写者串行提交。",
  },
  {
    tag: "Agent 编排 ORCHESTRATION",
    tech: "LangGraph StateGraph",
    desc: "采集 → 分析 → 质检 → 路由（通过则撰写 / 打回则回边重做）。append-only 状态，可断点续传。",
  },
  {
    tag: "数据 & 采集 DATA",
    tech: "SQLite(WAL) · 多引擎检索 · 证据缓存",
    desc: "claims / sources / evidence_chunks / qc_reports / trace_events 全程留痕；robots 与 SSRF 防护。",
  },
];

export const ArchitectureScene: React.FC = () => {
  return (
    <Chapter index="03" eyebrow="系统架构 · ARCHITECTURE" title="前端 · 后端 · Agent 编排 · 数据层">
      <div style={{ display: "flex", flexDirection: "column", gap: 18, height: "100%" }}>
        {LAYERS.map((l, i) => (
          <Rise key={l.tag} delay={6 + i * 7} style={{ flex: 1 }}>
            <DepthCard style={{ padding: "22px 34px", height: "100%", display: "flex", alignItems: "center", gap: 36 }}>
              <div style={{ width: 320, flexShrink: 0 }}>
                <div style={{ fontFamily: fontSans, fontSize: 26, fontWeight: 700, color: colors.mirrorBright }}>{l.tag}</div>
                <div style={{ fontFamily: fontMono, fontSize: 18, color: colors.textMuted, marginTop: 6 }}>{l.tech}</div>
              </div>
              <div style={{ width: 1, alignSelf: "stretch", backgroundColor: colors.border }} />
              <div style={{ fontFamily: fontSans, fontSize: 24, color: colors.text, lineHeight: 1.45, flex: 1 }}>{l.desc}</div>
            </DepthCard>
          </Rise>
        ))}
      </div>
    </Chapter>
  );
};
