import React from "react";
import { AbsoluteFill, Series } from "remotion";
import { CHAPTERS, sec, TOTAL_FRAMES } from "./timeline";
import { CaptionsOverlay, ChapterProgressOverlay, ChapterVoice, Voiceover } from "./components/Overlays";
import { TitleScene } from "./scenes/TitleScene";
import { ProblemScene } from "./scenes/ProblemScene";
import { ApproachScene } from "./scenes/ApproachScene";
import { ArchitectureScene } from "./scenes/ArchitectureScene";
import { InputScene } from "./scenes/InputScene";
import { DagScene } from "./scenes/DagScene";
import { ReportScene } from "./scenes/ReportScene";
import { CredibilityScene } from "./scenes/CredibilityScene";
import { QaReplayScene } from "./scenes/QaReplayScene";
import { EvidenceScene } from "./scenes/EvidenceScene";
import { ValidationScene } from "./scenes/ValidationScene";
import { BusinessScene } from "./scenes/BusinessScene";
import { FinalScene } from "./scenes/FinalScene";
import {
  Case1Section,
  Case2Section,
  N1ReportScene,
  N1QaScene,
  N1TraceScene,
  SchemaScene,
  ObservScene,
} from "./scenes/CaseScenes";

/** Chapter id → scene component. Order + durations come from src/timeline.ts. */
const SCENES: Record<string, React.FC> = {
  title: TitleScene,
  problem: ProblemScene,
  approach: ApproachScene,
  architecture: ArchitectureScene,
  input: InputScene,
  dag: DagScene,
  // case 1 — Notion only (3775d21a)
  case1: Case1Section,
  n1report: N1ReportScene,
  n1qa: N1QaScene,
  n1trace: N1TraceScene,
  // case 2 — Notion × Linear (4fff4227)
  case2: Case2Section,
  report: ReportScene,
  credibility: CredibilityScene,
  qareplay: QaReplayScene,
  evidence: EvidenceScene,
  schema: SchemaScene,
  observ: ObservScene,
  // close
  validation: ValidationScene,
  business: BusinessScene,
  final: FinalScene,
};

export const DURATION_IN_FRAMES = TOTAL_FRAMES;

export const MingJingLaunch: React.FC = () => {
  return (
    <AbsoluteFill>
      <Series>
        {CHAPTERS.map((c) => {
          const Scene = SCENES[c.id];
          return (
            <Series.Sequence key={c.id} durationInFrames={sec(c.durSec)}>
              <Scene />
              <ChapterVoice id={c.id} />
            </Series.Sequence>
          );
        })}
      </Series>
      <CaptionsOverlay />
      <ChapterProgressOverlay />
      <Voiceover />
    </AbsoluteFill>
  );
};
