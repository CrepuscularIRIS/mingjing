import React from "react";
import {
  AbsoluteFill,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { colors, fontMono, fontSans } from "../theme";
import { VIDEO } from "../theme";

/**
 * ShotScene — composites a REAL MingJing frontend screenshot (the product's own
 * 标准排版) with cinematic motion + spotlight callouts. This is how the
 * "frontend case" chapters stay 100% faithful to the product: the layout IS the
 * product, we only add motion + subtitles on top.
 *
 * Two modes:
 *  - "spotlight": a 1920×1080 capture shown 1:1 (crisp), with sequential
 *    spotlight rects (dim-the-rest + teal ring) that direct the eye.
 *  - "panY": a tall full-page capture (e.g. the whole report) scaled to frame
 *    width and panned vertically — crisp, no upscly beyond width-fit.
 */

export interface Focus {
  atSec: number;
  rect: [number, number, number, number]; // x,y,w,h in 1920×1080 display coords
  label?: string;
}

interface ShotSceneProps {
  src: string; // file under public/shots/
  mode: "spotlight" | "panY" | "contain" | "push";
  // panY:
  imgW?: number;
  imgH?: number;
  panFromY?: number; // displayed px at scene start (after width-fit scale)
  panToY?: number;
  // spotlight:
  focuses?: Focus[];
  // shared: gentle arrival
  eyebrow?: string;
}

const Eyebrow: React.FC<{ text: string; o: number }> = ({ text, o }) => (
  <div
    style={{
      position: "absolute",
      top: 30,
      left: 64,
      zIndex: 5,
      opacity: o,
      fontFamily: fontSans,
      fontSize: 17,
      letterSpacing: 4,
      textTransform: "uppercase",
      color: colors.mirrorBright,
      backgroundColor: "rgba(10,14,16,0.66)",
      border: `1px solid ${colors.border}`,
      borderRadius: 8,
      padding: "6px 14px",
      backdropFilter: "blur(6px)",
    }}
  >
    {text}
  </div>
);

const Spotlight: React.FC<{ rect: [number, number, number, number]; label?: string; o: number }> = ({
  rect,
  label,
  o,
}) => {
  const [x, y, w, h] = rect;
  return (
    <>
      <div
        style={{
          position: "absolute",
          left: x,
          top: y,
          width: w,
          height: h,
          borderRadius: 12,
          border: `2px solid ${colors.mirrorBright}`,
          boxShadow: `0 0 0 9999px rgba(8,11,13,${0.5 * o}), 0 0 24px ${colors.mirror}88`,
          opacity: o,
        }}
      />
      {label ? (
        <div
          style={{
            position: "absolute",
            left: x,
            top: y + h + 12,
            opacity: o,
            fontFamily: fontMono,
            fontSize: 20,
            color: colors.mirrorBright,
            backgroundColor: "rgba(10,14,16,0.85)",
            border: `1px solid ${colors.mirror}66`,
            borderRadius: 8,
            padding: "6px 14px",
          }}
        >
          {label}
        </div>
      ) : null}
    </>
  );
};

export const ShotScene: React.FC<ShotSceneProps> = ({
  src,
  mode,
  imgW = 1733,
  imgH = 7452,
  panFromY = 0,
  panToY = 0,
  focuses = [],
  eyebrow,
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames, fps } = useVideoConfig();
  const o = interpolate(frame, [0, 12], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  if (mode === "contain") {
    // Centered contain-fit on dark canvas (for the wide brand cover). Gentle push-in.
    const scale = interpolate(frame, [0, durationInFrames], [1.0, 1.045], { extrapolateRight: "clamp" });
    return (
      <AbsoluteFill style={{ backgroundColor: colors.canvas, justifyContent: "center", alignItems: "center" }}>
        <Img
          src={staticFile(`shots/${src}`)}
          style={{ width: "100%", height: "100%", objectFit: "contain", opacity: o, transform: `scale(${scale})` }}
        />
        {eyebrow ? <Eyebrow text={eyebrow} o={o} /> : null}
      </AbsoluteFill>
    );
  }

  if (mode === "push") {
    // Full-frame screenshot with a gentle Ken Burns push-in. NO overlay rings →
    // zero alignment risk; the page itself IS the content. Caption explains.
    const scale = interpolate(frame, [0, durationInFrames], [1.02, 1.08], { extrapolateRight: "clamp" });
    return (
      <AbsoluteFill style={{ backgroundColor: colors.canvas, overflow: "hidden" }}>
        <Img
          src={staticFile(`shots/${src}`)}
          style={{ width: VIDEO.WIDTH, height: VIDEO.HEIGHT, opacity: o, transform: `scale(${scale})` }}
        />
        {eyebrow ? <Eyebrow text={eyebrow} o={o} /> : null}
      </AbsoluteFill>
    );
  }

  if (mode === "panY") {
    const scale = VIDEO.WIDTH / imgW; // fit width
    const dispH = imgH * scale;
    const ty = interpolate(frame, [10, durationInFrames - 6], [-panFromY, -panToY], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
    return (
      <AbsoluteFill style={{ backgroundColor: colors.canvas, overflow: "hidden" }}>
        <Img
          src={staticFile(`shots/${src}`)}
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            width: VIDEO.WIDTH,
            height: dispH,
            transform: `translateY(${ty}px)`,
            opacity: o,
          }}
        />
        {eyebrow ? <Eyebrow text={eyebrow} o={o} /> : null}
      </AbsoluteFill>
    );
  }

  // spotlight mode — find the active focus (the last one whose atSec has passed)
  const t = frame / fps;
  let active = -1;
  focuses.forEach((f, i) => {
    if (t >= f.atSec) active = i;
  });
  // gentle push-in for life (no spotlight contradiction since rects scale-free here)
  return (
    <AbsoluteFill style={{ backgroundColor: colors.canvas, overflow: "hidden" }}>
      <Img
        src={staticFile(`shots/${src}`)}
        style={{ position: "absolute", inset: 0, width: VIDEO.WIDTH, height: VIDEO.HEIGHT, opacity: o }}
      />
      {focuses.map((f, i) => {
        if (i !== active) return null;
        const local = t - f.atSec;
        const fo = interpolate(local, [0, 0.4], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
        return <Spotlight key={i} rect={f.rect} label={f.label} o={fo} />;
      })}
      {eyebrow ? <Eyebrow text={eyebrow} o={o} /> : null}
    </AbsoluteFill>
  );
};
