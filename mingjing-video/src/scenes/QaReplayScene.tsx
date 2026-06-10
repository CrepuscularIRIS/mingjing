import React from "react";
import { ShotScene, type Focus } from "../components/ShotScene";

/**
 * Chapter 08 — QA 回放 money-shot (frontend case).
 * Real QAReplay capture (run 4fff4227, Notion 用户口碑): spotlight the static
 * flow PASS 1 弱 → 打回 → 重新取证 → 复核 → PASS 2 中.
 */
// Pixel-calibrated: PASS cards at y=483 (not guessed y=322).
const FOCUSES: Focus[] = [
  { atSec: 1, rect: [205, 472, 952, 242], label: "质检反馈闭环 · 用户口碑" },
  { atSec: 11, rect: [210, 476, 302, 234], label: "PASS 1 · 初判 弱（2 源）→ 打回" },
  { atSec: 20, rect: [512, 500, 342, 200], label: "重新取证 +2 来源" },
  { atSec: 29, rect: [850, 476, 302, 234], label: "PASS 2 · 复核 中（4 源）· 已升级" },
];

export const QaReplayScene: React.FC = () => {
  return <ShotScene src="cap-qareplay.png" mode="spotlight" focuses={FOCUSES} eyebrow="案例二 · QA 钱镜头" />;
};
