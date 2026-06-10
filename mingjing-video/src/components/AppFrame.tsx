import React from "react";
import { colors, fontMono, fontSans, fontSerif } from "../theme";
import { RUN } from "../data/run";

const TABS = [
  "分析报告",
  "Schema 矩阵",
  "证据 & 溯源",
  "QA 回放",
  "执行轨迹",
  "可观测",
] as const;

/**
 * MingJing app-window chrome — topbar + left sidebar nav — so the "frontend case"
 * scenes read as the real product (mirrors the 6-tab ink/mirror workbench).
 */
export const AppFrame: React.FC<
  React.PropsWithChildren<{ activeTab?: (typeof TABS)[number]; metaRight?: string }>
> = ({ children, activeTab = "分析报告", metaRight }) => {
  return (
    <div
      style={{
        position: "absolute",
        inset: 56,
        borderRadius: 18,
        overflow: "hidden",
        border: `1px solid ${colors.border}`,
        backgroundColor: colors.canvas,
        boxShadow: "0 40px 90px -30px rgba(0,0,0,0.85)",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* topbar */}
      <div
        style={{
          height: 76,
          flexShrink: 0,
          display: "flex",
          alignItems: "center",
          gap: 14,
          padding: "0 28px",
          borderBottom: `1px solid ${colors.border}`,
          backgroundColor: "rgba(12,16,18,0.7)",
        }}
      >
        <div
          style={{
            width: 30,
            height: 30,
            borderRadius: 8,
            background: `linear-gradient(135deg, ${colors.mirror}, ${colors.mirrorDeep})`,
            boxShadow: `0 0 14px ${colors.mirror}55`,
          }}
        />
        <div style={{ fontFamily: fontSerif, fontSize: 26, fontWeight: 600, color: colors.text }}>
          明镜 <span style={{ fontFamily: fontSans, fontSize: 18, color: colors.textMuted }}>MingJing · Evidence Runtime</span>
        </div>
        <div style={{ flex: 1 }} />
        <div
          style={{
            fontFamily: fontMono,
            fontSize: 16,
            color: colors.textFaint,
            border: `1px solid ${colors.border}`,
            borderRadius: 8,
            padding: "5px 12px",
          }}
        >
          {metaRight ?? `run: ${RUN.shortId}…`}
        </div>
      </div>
      {/* body: sidebar + content */}
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        <div
          style={{
            width: 230,
            flexShrink: 0,
            borderRight: `1px solid ${colors.border}`,
            padding: "22px 14px",
            display: "flex",
            flexDirection: "column",
            gap: 6,
            backgroundColor: "rgba(17,23,26,0.5)",
          }}
        >
          <div
            style={{
              fontFamily: fontSans,
              fontSize: 15,
              letterSpacing: 2,
              color: colors.textFaint,
              textTransform: "uppercase",
              padding: "0 12px 8px",
            }}
          >
            查看分析
          </div>
          {TABS.map((t) => {
            const active = t === activeTab;
            return (
              <div
                key={t}
                style={{
                  fontFamily: fontSans,
                  fontSize: 19,
                  color: active ? colors.mirrorBright : colors.textMuted,
                  backgroundColor: active ? colors.mirrorDeep : "transparent",
                  border: `1px solid ${active ? colors.mirror + "55" : "transparent"}`,
                  borderRadius: 9,
                  padding: "10px 14px",
                  fontWeight: active ? 600 : 400,
                }}
              >
                {t}
              </div>
            );
          })}
        </div>
        <div style={{ flex: 1, position: "relative", minWidth: 0, padding: 30 }}>{children}</div>
      </div>
    </div>
  );
};
