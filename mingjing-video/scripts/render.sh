#!/usr/bin/env bash
# Render the MingJing launch film to MP4 (H.264, 1920x1080@30).
# Remotion bundles its own Chrome + ffmpeg — no system ffmpeg needed.
set -euo pipefail
cd "$(dirname "$0")/.."

OUT="${1:-out/mingjing-launch.mp4}"
echo "→ Rendering MingJingLaunch → ${OUT}"
npx remotion render MingJingLaunch "${OUT}" --codec=h264
echo "✓ Done: ${OUT}"
ls -lh "${OUT}"
