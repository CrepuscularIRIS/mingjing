import React from "react";
import { AbsoluteFill } from "remotion";
import { Background } from "./Background";
import { Eyebrow, Rise } from "./primitives";
import { colors, fontSerif } from "../theme";

/**
 * Standard chapter layout for "designed" (non-app) scenes: ambient background,
 * numbered eyebrow + serif chapter title, then content. App-case scenes use
 * <AppFrame> instead.
 */
export const Chapter: React.FC<
  React.PropsWithChildren<{ index: string; eyebrow: string; title?: React.ReactNode }>
> = ({ index, eyebrow, title, children }) => {
  return (
    <AbsoluteFill>
      <Background />
      <AbsoluteFill style={{ padding: "96px 120px 120px" }}>
        <Rise>
          <Eyebrow index={index}>{eyebrow}</Eyebrow>
        </Rise>
        {title ? (
          <Rise delay={6} style={{ marginTop: 18 }}>
            <div
              style={{
                fontFamily: fontSerif,
                fontSize: 64,
                fontWeight: 600,
                color: colors.text,
                lineHeight: 1.1,
              }}
            >
              {title}
            </div>
          </Rise>
        ) : null}
        <div style={{ flex: 1, marginTop: title ? 46 : 36, minHeight: 0 }}>{children}</div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
