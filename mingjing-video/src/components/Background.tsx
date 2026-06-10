import React from "react";
import { AbsoluteFill } from "remotion";
import { colors } from "../theme";

/**
 * Ambient dark canvas with a faint dot-grid and a soft teal radial glow —
 * the same "intelligence workbench" backdrop the MingJing shell uses.
 */
export const Background: React.FC = () => {
  return (
    <AbsoluteFill style={{ backgroundColor: colors.canvas }}>
      {/* dot grid */}
      <AbsoluteFill
        style={{
          backgroundImage: `radial-gradient(rgba(255,255,255,0.045) 1px, transparent 1px)`,
          backgroundSize: "32px 32px",
        }}
      />
      {/* soft teal glow, top-left */}
      <AbsoluteFill
        style={{
          background: `radial-gradient(60% 50% at 18% 12%, ${colors.mirror}22 0%, transparent 60%)`,
        }}
      />
    </AbsoluteFill>
  );
};
