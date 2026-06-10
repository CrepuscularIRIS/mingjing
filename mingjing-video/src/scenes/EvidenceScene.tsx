import React from "react";
import { ShotScene, type Focus } from "../components/ShotScene";

/**
 * Chapter 09 — 证据 & 溯源 (frontend case).
 * Real Evidence capture: spotlight a cited source card (URL / 原文 / 哈希 /
 * LIVE·CACHED·SNIPPET / Admiralty) then the QA verdict panel.
 */
// Pixel-calibrated: middle source column + right QA panel [1482,391,384,662].
const FOCUSES: Focus[] = [
  { atSec: 1, rect: [462, 345, 1012, 250], label: "证据来源 · 选中结论的引用" },
  { atSec: 10, rect: [495, 738, 884, 192], label: "原文片段 · URL · LIVE / CACHED · Admiralty" },
  { atSec: 19, rect: [1476, 388, 396, 474], label: "QA 判定 · 采纳 / 驳回 / 暂存" },
];

export const EvidenceScene: React.FC = () => {
  return <ShotScene src="cap-evidence.png" mode="spotlight" focuses={FOCUSES} eyebrow="案例二 · 证据溯源" />;
};
