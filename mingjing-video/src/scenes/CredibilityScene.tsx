import React from "react";
import { ShotScene, type Focus } from "../components/ShotScene";

/**
 * Chapter 07 — 可信度 (frontend case).
 * Real report capture; spotlight walks the hero band: +42% 修正增益 →
 * 准入漏斗 10→6 → 证据强度构成 强1·中5·弱0.
 */
// Pixel-calibrated against the live DOM (hero band at y=137; not guessed).
const FOCUSES: Focus[] = [
  { atSec: 1, rect: [188, 144, 206, 132], label: "修正增益 +42% · 真闭环确认" },
  { atSec: 11, rect: [398, 162, 350, 96], label: "覆盖率 80% · 引用率 100% · 准入率 60%" },
  { atSec: 21, rect: [746, 188, 234, 50], label: "准入漏斗 10 提议 → 6 准入 · 4 留存" },
];

export const CredibilityScene: React.FC = () => {
  return <ShotScene src="cap-report.png" mode="spotlight" focuses={FOCUSES} eyebrow="案例二 · 可信度" />;
};
