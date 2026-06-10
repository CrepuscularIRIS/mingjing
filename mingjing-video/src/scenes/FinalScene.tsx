import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { Background } from "../components/Background";
import { colors, fontSans, fontSerif } from "../theme";

const Line: React.FC<{ children: React.ReactNode; delay: number; big?: boolean; color?: string }> = ({
  children,
  delay,
  big,
  color,
}) => {
  const frame = useCurrentFrame();
  const o = interpolate(frame - delay, [0, 16], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const y = interpolate(frame - delay, [0, 16], [16, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <div
      style={{
        fontFamily: fontSerif,
        fontSize: big ? 64 : 40,
        fontWeight: big ? 600 : 500,
        color: color ?? colors.text,
        opacity: o,
        transform: `translateY(${y}px)`,
        lineHeight: 1.3,
      }}
    >
      {children}
    </div>
  );
};

export const FinalScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const mark = spring({ frame: frame - 150, fps, durationInFrames: 28, config: { damping: 200 } });
  return (
    <AbsoluteFill>
      <Background />
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", gap: 24, textAlign: "center" }}>
        <Line delay={6} color={colors.textMuted}>不只是一份报告——</Line>
        <Line delay={24} big>
          而是一条可<span style={{ color: colors.strong.text }}>审计</span>的情报链路。
        </Line>
        <div style={{ height: 30 }} />
        <div
          style={{
            opacity: mark,
            transform: `translateY(${interpolate(mark, [0, 1], [18, 0])}px)`,
            fontFamily: fontSerif,
            fontSize: 96,
            fontWeight: 600,
            color: colors.text,
          }}
        >
          明镜 <span style={{ color: colors.mirrorBright }}>MingJing</span>
        </div>
        <Line delay={200} color={colors.textMuted}>
          <span style={{ fontFamily: fontSans, fontSize: 32 }}>让 AI 知道，什么时候不该自信。</span>
        </Line>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
