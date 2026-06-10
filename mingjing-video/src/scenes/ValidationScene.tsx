import React from "react";
import { Chapter } from "../components/Chapter";
import { DepthCard, Rise } from "../components/primitives";
import { colors, fontMono, fontSans, fontSerif } from "../theme";
import { VALIDATION } from "../data/run";

const Card: React.FC<{
  delay: number;
  metric: React.ReactNode;
  metricColor?: string;
  title: string;
  sub: string;
  source?: string;
}> = ({ delay, metric, metricColor, title, sub, source }) => (
  <Rise delay={delay} style={{ flex: 1 }}>
    <DepthCard style={{ padding: 32, height: "100%", display: "flex", flexDirection: "column" }}>
      <div style={{ fontFamily: fontMono, fontSize: 50, fontWeight: 800, color: metricColor ?? colors.mirrorBright, lineHeight: 1.05 }}>
        {metric}
      </div>
      <div style={{ fontFamily: fontSerif, fontSize: 28, fontWeight: 600, color: colors.text, marginTop: 14 }}>{title}</div>
      <div style={{ fontFamily: fontSans, fontSize: 21, color: colors.textMuted, marginTop: 12, lineHeight: 1.45, flex: 1 }}>{sub}</div>
      {source ? (
        <div style={{ fontFamily: fontMono, fontSize: 16, color: colors.textFaint, marginTop: 16, paddingTop: 14, borderTop: `1px solid ${colors.border}` }}>
          可复现 · {source}
        </div>
      ) : null}
    </DepthCard>
  </Rise>
);

export const ValidationScene: React.FC = () => {
  const v = VALIDATION;
  return (
    <Chapter index="10" eyebrow="诚实性硬证据 · VALIDATION" title="不是「声称可信」，而是可被复现地验证">
      <div style={{ display: "flex", flexDirection: "column", gap: 22, height: "100%" }}>
        <div style={{ display: "flex", gap: 22, flex: 1, minHeight: 0 }}>
          <Card
            delay={6}
            metric="100%"
            metricColor={colors.strong.text}
            title="全量逐字复核"
            sub={`${v.verbatim.snippets} 片段 · ${v.verbatim.claims} 结论 — ${v.verbatim.label}`}
            source={v.verbatim.source}
          />
          <Card
            delay={12}
            metric={`P / R / acc = 1.00`}
            title="QA 判定校准集"
            sub={`${v.calibration.cases} 例 · ${v.calibration.label}`}
            source={v.calibration.source}
          />
          <Card
            delay={18}
            metric={`${v.qaEvents.fail} / ${v.qaEvents.pass}`}
            metricColor={colors.weak.text}
            title="qa_fail / qa_pass"
            sub={v.qaEvents.label}
            source="/runs/4fff…/trace"
          />
        </div>

        {/* provider-agnostic strip */}
        <Rise delay={24}>
          <DepthCard style={{ padding: "24px 32px", display: "flex", alignItems: "center", gap: 28 }} accent>
            <div style={{ fontFamily: fontSans, fontSize: 22, fontWeight: 700, color: colors.mirrorBright, width: 240, flexShrink: 0 }}>
              门禁 Provider-Agnostic
            </div>
            <div style={{ width: 1, alignSelf: "stretch", backgroundColor: colors.border }} />
            <div style={{ fontFamily: fontSans, fontSize: 22, color: colors.text, lineHeight: 1.5, flex: 1 }}>
              <span style={{ color: colors.weak.text }}>{v.providerAgnostic.stress}</span>
              {" + "}
              <span style={{ color: colors.strong.text }}>{v.providerAgnostic.contest}</span>
              <span style={{ fontFamily: fontMono, fontSize: 18, color: colors.textFaint }}>（run {v.providerAgnostic.contestRun}）</span>
              <br />
              <span style={{ fontSize: 19, color: colors.textMuted }}>{v.providerAgnostic.contestDetail}</span>
            </div>
          </DepthCard>
        </Rise>

        <div style={{ fontFamily: fontSans, fontSize: 19, color: colors.textFaint }}>
          诚实边界：以上是「被来源逐字支撑率」，不是「对世界为真率」——来源本身可能错，故按可靠性 × 可信度双轴分级、跨源矛盾独立检测。
        </div>
      </div>
    </Chapter>
  );
};
