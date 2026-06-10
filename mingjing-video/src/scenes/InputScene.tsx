import React from "react";
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import { Background } from "../components/Background";
import { Eyebrow, Rise } from "../components/primitives";
import { colors, fontMono, fontSans, fontSerif } from "../theme";

/**
 * Chapter 04 — 输入场景.
 * Shows the REAL 发起实时分析 form (cap-form.png, filled with run 4fff4227's
 * actual inputs) on the left, with an explanation on the right.
 */
const POINTS: [string, string][] = [
  ["品类 Category", "AI 产品竞品分析"],
  ["竞品 Competitors", "Notion, Linear（留空 = 自动发现）"],
  ["研究目标 Goal", "定价 · 用户画像 · 功能 · SWOT"],
];

export const InputScene: React.FC = () => {
  const frame = useCurrentFrame();
  const formO = interpolate(frame, [4, 18], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const formY = interpolate(frame, [4, 18], [20, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <AbsoluteFill>
      <Background />
      <AbsoluteFill style={{ padding: "96px 140px", flexDirection: "row", alignItems: "center", gap: 96 }}>
        {/* real form image */}
        <div style={{ opacity: formO, transform: `translateY(${formY}px)`, flexShrink: 0 }}>
          <Img
            src={staticFile("shots/cap-form.png")}
            style={{
              height: 760,
              borderRadius: 14,
              border: `1px solid ${colors.border}`,
              boxShadow: "0 30px 70px -28px rgba(0,0,0,0.85)",
            }}
          />
        </div>
        {/* explanation */}
        <div style={{ flex: 1 }}>
          <Rise>
            <Eyebrow index="04">输入场景 · INPUT</Eyebrow>
          </Rise>
          <Rise delay={6} style={{ marginTop: 18 }}>
            <div style={{ fontFamily: fontSerif, fontSize: 60, fontWeight: 600, color: colors.text, lineHeight: 1.12 }}>
              一个市场方向，
              <br />
              即可启动一支分析团队
            </div>
          </Rise>
          <div style={{ marginTop: 40, display: "flex", flexDirection: "column", gap: 20 }}>
            {POINTS.map(([k, v], i) => (
              <Rise key={k} delay={16 + i * 7}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 18 }}>
                  <div style={{ fontFamily: fontMono, fontSize: 20, color: colors.mirrorBright, width: 230 }}>{k}</div>
                  <div style={{ fontFamily: fontSans, fontSize: 28, color: colors.text }}>{v}</div>
                </div>
              </Rise>
            ))}
          </div>
          <Rise delay={40} style={{ marginTop: 38 }}>
            <div style={{ fontFamily: fontSans, fontSize: 22, color: colors.textFaint }}>
              点「开始实时分析」→ 后台 LangGraph 执行器联网采集，活动流实时刷新。
            </div>
          </Rise>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
