import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { Chapter } from "../components/Chapter";
import { DepthCard } from "../components/primitives";
import { colors, fontMono, fontSans, fontSerif } from "../theme";
import { DAG } from "../data/run";

const NODE_W = 300;

const Node: React.FC<{ node: (typeof DAG)[number]; lit: number; reject?: boolean }> = ({ node, lit }) => (
  <DepthCard
    style={{
      width: NODE_W,
      padding: 26,
      borderColor: lit > 0.5 ? colors.mirror : colors.border,
      boxShadow:
        lit > 0.5
          ? `inset 0 1px 0 0 rgba(255,255,255,0.04), 0 0 0 1px ${colors.mirror}55, 0 18px 40px -20px rgba(0,0,0,0.8)`
          : undefined,
      transform: `translateY(${interpolate(lit, [0, 1], [12, 0])}px)`,
      opacity: interpolate(lit, [0, 1], [0.35, 1]),
    }}
  >
    <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
      <div style={{ fontFamily: fontSerif, fontSize: 34, fontWeight: 600, color: colors.text }}>{node.label}</div>
      <div style={{ fontFamily: fontMono, fontSize: 18, color: colors.mirrorBright }}>{node.en}</div>
    </div>
    <div style={{ fontFamily: fontSans, fontSize: 18, color: colors.textMuted, marginTop: 12, lineHeight: 1.45 }}>
      {node.desc}
    </div>
    <div
      style={{
        marginTop: 14,
        fontFamily: fontMono,
        fontSize: 15,
        color: node.pure ? colors.strong.text : colors.textFaint,
      }}
    >
      {node.pure ? "纯函数 · 可复现" : "有 I/O"}
    </div>
  </DepthCard>
);

const Arrow: React.FC<{ lit: number }> = ({ lit }) => (
  <div style={{ fontFamily: fontSans, fontSize: 40, color: lit > 0.5 ? colors.mirrorBright : colors.borderSoft }}>→</div>
);

export const DagScene: React.FC = () => {
  const frame = useCurrentFrame();
  const lit = (i: number) => interpolate(frame, [10 + i * 12, 26 + i * 12], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const rejectLit = interpolate(frame, [300, 320], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <Chapter index="05" eyebrow="Agent 协作 · DAG" title="四类 Agent，传递结构化消息">
      <div style={{ display: "flex", flexDirection: "column", height: "100%", justifyContent: "center", gap: 56 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 22, justifyContent: "center" }}>
          {DAG.map((n, i) => (
            <React.Fragment key={n.id}>
              <Node node={n} lit={lit(i)} />
              {i < DAG.length - 1 ? <Arrow lit={lit(i + 1)} /> : null}
            </React.Fragment>
          ))}
        </div>

        {/* reject back-edge */}
        <div
          style={{
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            gap: 18,
            opacity: rejectLit,
          }}
        >
          <div
            style={{
              fontFamily: fontSans,
              fontSize: 24,
              color: colors.weak.text,
              border: `1px solid ${colors.weak.border}`,
              backgroundColor: colors.weak.bg,
              borderRadius: 999,
              padding: "10px 26px",
            }}
          >
            质检不通过 ⟲ 回边重新取证（collect | analyze）
          </div>
          <div style={{ fontFamily: fontSans, fontSize: 22, color: colors.textMuted }}>
            真实自纠闭环，而非一次性生成
          </div>
        </div>
      </div>
    </Chapter>
  );
};
