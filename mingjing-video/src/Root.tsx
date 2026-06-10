import React from "react";
import { Composition } from "remotion";
import { VIDEO } from "./theme";
import { MingJingLaunch, DURATION_IN_FRAMES } from "./MingJingLaunch";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="MingJingLaunch"
      component={MingJingLaunch}
      durationInFrames={DURATION_IN_FRAMES}
      fps={VIDEO.FPS}
      width={VIDEO.WIDTH}
      height={VIDEO.HEIGHT}
    />
  );
};
