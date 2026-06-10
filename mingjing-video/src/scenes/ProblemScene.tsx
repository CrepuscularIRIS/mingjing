import React from "react";
import { useCurrentFrame } from "remotion";
import { Chapter } from "../components/Chapter";
import { DepthCard, Rise } from "../components/primitives";
import { colors, fontSans, fontSerif } from "../theme";

const Side: React.FC<{
  delay: number;
  tag: string;
  tagColor: string;
  headline: string;
  body: string;
  dim?: boolean;
}> = ({ delay, tag, tagColor, headline, body, dim }) => (
  <Rise delay={delay} style={{ flex: 1 }}>
    <DepthCard style={{ padding: 44, height: "100%", opacity: dim ? 0.92 : 1 }} accent={!dim}>
      <div
        style={{
          fontFamily: fontSans,
          fontSize: 22,
          fontWeight: 600,
          color: tagColor,
          letterSpacing: 1,
          marginBottom: 22,
        }}
      >
        {tag}
      </div>
      <div style={{ fontFamily: fontSerif, fontSize: 50, fontWeight: 600, color: colors.text, lineHeight: 1.18 }}>
        {headline}
      </div>
      <div style={{ fontFamily: fontSans, fontSize: 27, color: colors.textMuted, marginTop: 26, lineHeight: 1.5 }}>
        {body}
      </div>
    </DepthCard>
  </Rise>
);

export const ProblemScene: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <Chapter index="01" eyebrow="问题 · WHY" title="Deep Research 的报告，你只能选择相信">
      <div style={{ display: "flex", gap: 40, height: "100%", alignItems: "stretch" }}>
        <Side
          delay={6}
          tag="普通 Deep Research"
          tagColor={colors.weak.text}
          headline="一份只能「相信」的报告"
          body="结论看起来完整，却无法核对来源、无法判断强弱、无法追问它凭什么这么说。"
          dim
        />
        <div
          style={{
            alignSelf: "center",
            fontFamily: fontSans,
            fontSize: 44,
            color: colors.mirrorBright,
            opacity: frame > 30 ? 1 : 0,
          }}
        >
          →
        </div>
        <Side
          delay={18}
          tag="明镜 MingJing"
          tagColor={colors.strong.text}
          headline="一份可以「审计」的报告"
          body="可以打回、可以追溯、可以核对每一条结论的来源与强度——它知道何时不该自信。"
        />
      </div>
    </Chapter>
  );
};
