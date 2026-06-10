import React from "react";
import { ShotScene } from "../components/ShotScene";
import { SectionCard } from "../components/SectionCard";
import { colors } from "../theme";

/* ---- Case dividers ---- */

export const Case1Section: React.FC = () => (
  <SectionCard
    kicker="案例一 · CASE 01"
    title={<>单一竞品分析 · <span style={{ color: colors.mirrorBright }}>Notion</span></>}
    subtitle="run 3775d21a · 定价结论 弱(1 源) → 中(5 源) · 修正增益 +38%"
  />
);

export const Case2Section: React.FC = () => (
  <SectionCard
    kicker="案例二 · CASE 02"
    title={<>竞品对比 · <span style={{ color: colors.mirrorBright }}>Notion × Linear</span></>}
    subtitle="run 4fff4227 · 中文矩阵 · 6/10 准入 · 双弧线 · 修正增益 +42%"
  />
);

/* ---- Case 1 (Notion-only, 3775d21a) real pages — push-in, no overlay ---- */

export const N1ReportScene: React.FC = () => (
  <ShotScene src="cap-n-report.png" mode="push" eyebrow="案例一 · 分析报告" />
);

export const N1QaScene: React.FC = () => (
  <ShotScene src="cap-n-qareplay.png" mode="push" eyebrow="案例一 · QA 回放 · 定价 弱1→中5" />
);

export const N1TraceScene: React.FC = () => (
  <ShotScene src="cap-n-trace.png" mode="push" eyebrow="案例一 · 执行轨迹 DAG" />
);

/* ---- Case 2 (Notion×Linear, 4fff4227) additional pages ---- */

export const SchemaScene: React.FC = () => (
  <ShotScene src="cap-schema.png" mode="push" eyebrow="案例二 · Schema 矩阵 · 竞品 × 字段 × 强度" />
);

export const ObservScene: React.FC = () => (
  <ShotScene src="cap-observ.png" mode="push" eyebrow="案例二 · 可观测 · 每 Agent 调用 / Token" />
);
