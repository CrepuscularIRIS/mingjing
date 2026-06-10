#!/usr/bin/env bash
# Open Remotion Studio for live preview / scrubbing of the launch film.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "→ Remotion Studio (Ctrl+C to stop). Default: http://localhost:3000"
npx remotion studio
