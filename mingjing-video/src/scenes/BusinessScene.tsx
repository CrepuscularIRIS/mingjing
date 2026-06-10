import React from "react";
import { Chapter } from "../components/Chapter";
import { AnimatedNumber, DepthCard, Rise } from "../components/primitives";
import { colors, fontMono, fontSans } from "../theme";
import { KPI } from "../data/run";

const PILLARS = ["每条结论的来源级溯源", "确定性 QA 准入闸门", "可回放的执行轨迹 trace"];

export const BusinessScene: React.FC = () => {
  return (
    <Chapter index="11" eyebrow="业务价值 · IMPACT" title="从十几小时，到二十几分钟">
      <div style={{ display: "flex", flexDirection: "column", gap: 28, height: "100%" }}>
        <div style={{ display: "flex", gap: 24 }}>
          <Rise delay={6} style={{ flex: 1 }}>
            <DepthCard style={{ padding: 34 }}>
              <div style={{ fontFamily: fontSans, fontSize: 22, color: colors.textMuted }}>人工竞品调研（行业估算）</div>
              <div style={{ fontFamily: fontMono, fontSize: 64, fontWeight: 800, color: colors.textMuted }}>16–40 h</div>
            </DepthCard>
          </Rise>
          <div style={{ alignSelf: "center", fontFamily: fontSans, fontSize: 40, color: colors.mirrorBright }}>→</div>
          <Rise delay={14} style={{ flex: 1 }}>
            <DepthCard style={{ padding: 34, borderColor: colors.lime + "55" }} accent>
              <div style={{ fontFamily: fontSans, fontSize: 22, color: colors.textMuted }}>明镜（本次实测 · 可回放）</div>
              <div style={{ fontFamily: fontMono, fontSize: 60, fontWeight: 800, color: colors.lime }}>23 分 6 秒</div>
              <div style={{ fontFamily: fontSans, fontSize: 18, color: colors.textFaint, marginTop: 4 }}>4 轮打回重采 · 质量换时间</div>
            </DepthCard>
          </Rise>
          <Rise delay={20} style={{ flex: 1 }}>
            <DepthCard style={{ padding: 34, height: "100%", display: "flex", flexDirection: "column", justifyContent: "center" }}>
              <div style={{ fontFamily: fontSans, fontSize: 22, color: colors.textMuted }}>提速（估算基线）</div>
              <div style={{ fontFamily: fontMono, fontSize: 54, fontWeight: 800, color: colors.mirrorBright }}>
                约 <AnimatedNumber to={42} delay={20} />–<AnimatedNumber to={104} delay={24} />×
              </div>
            </DepthCard>
          </Rise>
        </div>
        <Rise delay={28} style={{ display: "flex", gap: 20 }}>
          {PILLARS.map((p, i) => (
            <DepthCard key={i} style={{ padding: "24px 28px", flex: 1, display: "flex", alignItems: "center", gap: 14 }}>
              <div style={{ color: colors.strong.text, fontSize: 26 }}>✓</div>
              <div style={{ fontFamily: fontSans, fontSize: 24, color: colors.text }}>{p}</div>
            </DepthCard>
          ))}
        </Rise>
        <div style={{ fontFamily: fontSans, fontSize: 22, color: colors.textFaint }}>
          速度只是表象——真正的价值是「可被审计」：{KPI.citation * 100}% 引用率，每条结论都能回到原始来源。
        </div>
      </div>
    </Chapter>
  );
};
