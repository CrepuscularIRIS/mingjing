/**
 * MingJing (明镜) design tokens — mirrored verbatim from the frontend
 * `tailwind.config.js` + `index.css` so the film matches the product 1:1.
 * Dark "intelligence" canvas, teal "mirror" brand accent, lime money-shot,
 * and the honest strong/moderate/weak evidence palette (never red-for-weak).
 */
import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont as loadSerif } from "@remotion/google-fonts/SourceSerif4";
import { loadFont as loadMono } from "@remotion/google-fonts/JetBrainsMono";

// Fonts load synchronously into Remotion's render via delayRender internally.
// Constrain to the weights/subsets actually used so each render makes a handful
// of font requests instead of ~100. CJK glyphs fall back to the headless
// shell's system serif/sans (Google's latin fonts carry no CJK).
const subsets: ["latin"] = ["latin"];
const ignoreTooManyRequestsWarning = true;

export const fontSans = loadInter("normal", {
  weights: ["400", "500", "600", "700"],
  subsets,
  ignoreTooManyRequestsWarning,
}).fontFamily; // UI / body
export const fontSerif = loadSerif("normal", {
  weights: ["400", "600"],
  subsets,
  ignoreTooManyRequestsWarning,
}).fontFamily; // report + brand wordmark
export const fontMono = loadMono("normal", {
  weights: ["400", "600"],
  subsets,
  ignoreTooManyRequestsWarning,
}).fontFamily; // metric numerals

export const colors = {
  // Dark "ink" canvas scale (inverted: 50 = near-black surface, 900 = near-white text)
  canvas: "#0a0e10", // ink-50 — page background
  surface: "#11171a", // ink-100 — raised slate
  surfaceRaised: "#1b2329", // ink-200 — panels / borders
  border: "#1b2329",
  borderSoft: "#2a343b", // ink-300
  textFaint: "#8b969c", // ink-400
  textMuted: "#a7b4ba", // ink-600
  text: "#f1f5f6", // ink-900 — primary text

  // Brand "mirror" teal
  mirror: "#449a96", // mirror-400 — primary action
  mirrorBright: "#71bbb6", // mirror-300 — text/icon pop on dark
  mirrorDeep: "#15302d", // mirror-100 — accent band

  // Money-shot lime — RESERVED for the repair_delta (+42%) / 真闭环 / gains
  lime: "#84cc16",
  limeBright: "#a3e635",

  // Honest evidence-strength palette
  strong: { bg: "#11271b", text: "#5fd08a", border: "#2e9e5a" },
  moderate: { bg: "#16182e", text: "#9aa0ee", border: "#6060b8" },
  weak: { bg: "#241f10", text: "#d9c06a", border: "#b89830" },
} as const;

export const VIDEO = {
  WIDTH: 1920,
  HEIGHT: 1080,
  FPS: 30,
} as const;
