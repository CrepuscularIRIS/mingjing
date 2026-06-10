import React from "react";
import { ShotScene } from "../components/ShotScene";

/**
 * Chapter 06 — 分析报告 (frontend case).
 * Real full-page capture of the report on run 4fff4227, panned top→down:
 * 范围与方法 → BLUF（衬线大字 + 引用 chip）→ SWOT → 竞品对比 → 建议.
 */
export const ReportScene: React.FC = () => {
  return (
    <ShotScene
      src="cap-report-scroll.png"
      mode="panY"
      imgW={1733}
      imgH={7452}
      panFromY={0}
      panToY={2100}
      eyebrow="案例二 · 分析报告"
    />
  );
};
