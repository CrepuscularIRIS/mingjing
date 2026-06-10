import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { Background } from "./Background";
import { colors, fontMono, fontSans, fontSerif } from "../theme";

/** Big "案例 N" divider card between the two case studies. */
export const SectionCard: React.FC<{
  kicker: string; // "案例一 · CASE 01"
  title: React.ReactNode; // "单一竞品分析"
  subtitle: string; // "Notion · run 3775d21a · 弱→中 修复"
}> = ({ kicker, title, subtitle }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame, fps, durationInFrames: 22, config: { damping: 200 } });
  const y = interpolate(s, [0, 1], [22, 0]);
  const rule = interpolate(frame, [14, 40], [0, 260], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <AbsoluteFill>
      <Background />
      <AbsoluteFill style={{ justifyContent: "center", paddingLeft: 160 }}>
        <div
          style={{
            fontFamily: fontMono,
            fontSize: 26,
            letterSpacing: 6,
            color: colors.mirrorBright,
            opacity: interpolate(frame, [0, 14], [0, 1], { extrapolateRight: "clamp" }),
          }}
        >
          {kicker}
        </div>
        <div
          style={{
            fontFamily: fontSerif,
            fontSize: 96,
            fontWeight: 600,
            color: colors.text,
            marginTop: 16,
            opacity: s,
            transform: `translateY(${y}px)`,
          }}
        >
          {title}
        </div>
        <div style={{ height: 4, width: rule, backgroundColor: colors.mirror, borderRadius: 2, marginTop: 30, marginBottom: 26 }} />
        <div
          style={{
            fontFamily: fontSans,
            fontSize: 30,
            color: colors.textMuted,
            opacity: interpolate(frame, [24, 44], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
          }}
        >
          {subtitle}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
