import React from "react";
import { Chapter } from "../components/Chapter";
import { DepthCard, Rise } from "../components/primitives";
import { colors, fontMono, fontSans, fontSerif } from "../theme";

const CARDS = [
  {
    n: "01",
    title: "提案 / 裁定分离",
    body: "LLM 只负责「提案」结论；一个无 LLM 的确定性 QA 负责「裁定」真值。生成与校验互不污染。",
    foot: "analyst → qa",
  },
  {
    n: "02",
    title: "透明三档强度",
    body: "证据强度只有 强 / 中 / 弱，没有可信度小数。强弱由独立来源数与权威性决定，可解释、可复现。",
    foot: "strong · moderate · weak",
  },
  {
    n: "03",
    title: "投影不变式",
    body: "Writer 只投影 QA 通过的结论；未达准入的内容不会进入报告，而是以「暂存」保留并标明原因。",
    foot: "writer = projection(passed)",
  },
];

export const ApproachScene: React.FC = () => {
  return (
    <Chapter index="02" eyebrow="产品构建思路 · APPROACH" title="不是让 AI 更会写，而是让结论可被裁定">
      <div style={{ display: "flex", gap: 30, height: "100%" }}>
        {CARDS.map((c, i) => (
          <Rise key={c.n} delay={8 + i * 9} style={{ flex: 1 }}>
            <DepthCard style={{ padding: 38, height: "100%", display: "flex", flexDirection: "column" }}>
              <div style={{ fontFamily: fontMono, fontSize: 34, color: colors.mirror, fontWeight: 700 }}>{c.n}</div>
              <div style={{ fontFamily: fontSerif, fontSize: 38, fontWeight: 600, color: colors.text, marginTop: 16 }}>
                {c.title}
              </div>
              <div style={{ fontFamily: fontSans, fontSize: 25, color: colors.textMuted, marginTop: 20, lineHeight: 1.5, flex: 1 }}>
                {c.body}
              </div>
              <div
                style={{
                  fontFamily: fontMono,
                  fontSize: 19,
                  color: colors.mirrorBright,
                  marginTop: 22,
                  paddingTop: 18,
                  borderTop: `1px solid ${colors.border}`,
                }}
              >
                {c.foot}
              </div>
            </DepthCard>
          </Rise>
        ))}
      </div>
    </Chapter>
  );
};
