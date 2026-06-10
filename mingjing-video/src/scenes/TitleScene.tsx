import React from "react";
import { ShotScene } from "../components/ShotScene";

/**
 * Chapter 00 — Title.
 * Uses MingJing's REAL designed cover, re-rendered from the CURRENT
 * docs/presentation/cover.html (shows +42% / run 4fff4227, consistent with the film).
 */
export const TitleScene: React.FC = () => {
  return <ShotScene src="cap-cover.png" mode="contain" />;
};
