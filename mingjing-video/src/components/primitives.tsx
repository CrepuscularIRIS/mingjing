import React from "react";
import {
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { colors, fontMono, fontSans } from "../theme";
import type { Tier } from "../data/run";

/** Small uppercase teal eyebrow label, optionally numbered (章节 01 ·). */
export const Eyebrow: React.FC<{ children: React.ReactNode; index?: string }> = ({
  children,
  index,
}) => (
  <div
    style={{
      fontFamily: fontSans,
      // DESIGN.md label signature: small uppercase, wide tracking, muted.
      fontSize: 18,
      fontWeight: 600,
      letterSpacing: 4,
      textTransform: "uppercase",
      color: colors.mirrorBright,
      display: "flex",
      alignItems: "center",
      gap: 14,
    }}
  >
    {index ? (
      <span style={{ fontFamily: fontMono, color: colors.mirror }}>{index}</span>
    ) : null}
    {children}
  </div>
);

/** Raised dark panel (mirrors the product `.depth-card`). */
export const DepthCard: React.FC<
  React.PropsWithChildren<{ style?: React.CSSProperties; accent?: boolean }>
> = ({ children, style, accent }) => (
  <div
    style={{
      backgroundColor: colors.surface,
      border: `1px solid ${accent ? colors.mirror + "66" : colors.border}`,
      borderRadius: 16,
      boxShadow:
        "inset 0 1px 0 0 rgba(255,255,255,0.03), 0 18px 44px -20px rgba(0,0,0,0.75)",
      ...style,
    }}
  >
    {children}
  </div>
);

const TIER_LABEL: Record<Tier, string> = { strong: "强", moderate: "中", weak: "弱" };
const TIER_COLOR = (t: Tier) => colors[t];

/** Evidence-strength pill — 强 / 中 / 弱 (never red-for-weak). */
export const TierBadge: React.FC<{ tier: Tier; sources?: number; big?: boolean }> = ({
  tier,
  sources,
  big,
}) => {
  const c = TIER_COLOR(tier);
  return (
    <span
      style={{
        fontFamily: fontSans,
        fontSize: big ? 30 : 22,
        fontWeight: 600,
        color: c.text,
        backgroundColor: c.bg,
        border: `1px solid ${c.border}`,
        borderRadius: 999,
        padding: big ? "8px 20px" : "4px 14px",
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        whiteSpace: "nowrap",
      }}
    >
      {TIER_LABEL[tier]}
      {sources != null ? (
        <span style={{ fontFamily: fontMono, opacity: 0.85 }}>{sources}源</span>
      ) : null}
    </span>
  );
};

/** Header-style KPI chip: small label over a big mono value. */
export const KpiChip: React.FC<{
  label: string;
  value: React.ReactNode;
  accent?: "mirror" | "lime" | "default";
  sub?: string;
}> = ({ label, value, accent = "default", sub }) => {
  const valueColor =
    accent === "lime" ? colors.lime : accent === "mirror" ? colors.mirrorBright : colors.text;
  return (
    <DepthCard style={{ padding: "16px 22px", minWidth: 150 }} accent={accent !== "default"}>
      <div style={{ fontFamily: fontSans, fontSize: 19, color: colors.textMuted }}>{label}</div>
      <div
        style={{
          fontFamily: fontMono,
          fontSize: 40,
          fontWeight: 700,
          color: valueColor,
          lineHeight: 1.1,
          marginTop: 4,
        }}
      >
        {value}
      </div>
      {sub ? (
        <div style={{ fontFamily: fontSans, fontSize: 15, color: colors.textFaint, marginTop: 2 }}>
          {sub}
        </div>
      ) : null}
    </DepthCard>
  );
};

/** Spring count-up number. Mono font, tabular. */
export const AnimatedNumber: React.FC<{
  to: number;
  decimals?: number;
  prefix?: string;
  suffix?: string;
  delay?: number;
  duration?: number;
  style?: React.CSSProperties;
}> = ({ to, decimals = 0, prefix = "", suffix = "", delay = 0, duration = 26, style }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spring({ frame: frame - delay, fps, durationInFrames: duration, config: { damping: 200 } });
  const v = interpolate(p, [0, 1], [0, to]);
  return (
    <span style={{ fontFamily: fontMono, fontVariantNumeric: "tabular-nums", ...style }}>
      {prefix}
      {v.toFixed(decimals)}
      {suffix}
    </span>
  );
};

/** Simple fade+rise on entry, keyed off a frame offset. */
export const Rise: React.FC<
  React.PropsWithChildren<{ delay?: number; y?: number; style?: React.CSSProperties }>
> = ({ children, delay = 0, y = 18, style }) => {
  const frame = useCurrentFrame();
  const o = interpolate(frame - delay, [0, 14], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const ty = interpolate(frame - delay, [0, 14], [y, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return <div style={{ opacity: o, transform: `translateY(${ty}px)`, ...style }}>{children}</div>;
};
