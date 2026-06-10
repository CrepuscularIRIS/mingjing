/**
 * Build-time / render-time switches.
 *
 * Audio is OPTIONAL and never breaks a render:
 *  - Pointing <Audio> at a missing staticFile fails the render, so audio is
 *    gated. It turns on either by setting the flags below to `true`, OR by
 *    passing `--props='{"hasVoiceover":true}'` at render time (the
 *    `scripts/render_with_audio.sh` helper does this automatically when it
 *    detects `public/audio/voiceover.wav`).
 *  - Default = silent render; the burned-in captions carry the narration.
 *
 * Workflow: record one continuous `public/audio/voiceover.wav` reading
 * `docs/VOICEOVER.md`, then run `./scripts/render_with_audio.sh`. Tune cue
 * timing in `src/timeline.ts` if the voiceover pacing drifts from the captions.
 */
export const HAS_VOICEOVER = false; // manual override; the render script also auto-detects the file
export const VOICEOVER_FILE = "audio/voiceover.wav";
export const VOICEOVER_VOLUME = 1;

export const HAS_BGM = false; // background music — kept off by default; very quiet when on
export const BGM_FILE = "audio/bgm.mp3";
export const BGM_VOLUME = 0.05;
