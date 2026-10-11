#!/usr/bin/env bash
# Re-encode a film for web delivery: same size, frame rate and every frame with its original timestamp
# (-fps_mode passthrough); audio dropped (films are played muted); H.264 High, CRF 29, faststart.
#
# Usage:  scripts/encode_film.sh media/<original>.mp4 media/<web copy>.mp4
# Then set film.local_file (and film.file, the name on JATOS) in your study file to the web copy, and
# film.duration_s to the duration this script prints.
#
# Heights study example (2026-10-04): scripts/encode_film.sh media/towerClimb.mp4 media/towerClimb_crf29.mp4
#   1280x720, 25 fps, all 20,222 frames; 288 MB -> 147 MB (146,877,793 bytes), SSIM 0.979, duration 13:28.88.
# ffmpeg: any build with libx264 (e.g. pip install imageio-ffmpeg; python -c "import imageio_ffmpeg as f; print(f.get_ffmpeg_exe())"),
# then FFMPEG=<that path> scripts/encode_film.sh ...
set -euo pipefail
FF="${FFMPEG:-ffmpeg}"
if [[ $# -ne 2 ]]; then
  echo "Usage: scripts/encode_film.sh <original film> <web copy to write>" >&2; exit 1
fi
IN="$1"; OUT="$2"
"$FF" -hide_banner -y -i "$IN" -map 0:v:0 -c:v libx264 -preset slow -crf 29 -pix_fmt yuv420p \
  -profile:v high -fps_mode passthrough -an -movflags +faststart "$OUT"
# Verify: frame count, duration and SSIM against the original (1 = identical)
"$FF" -hide_banner -i "$OUT" -map 0:v:0 -c copy -f null - 2>&1 | grep -oE "frame= *[0-9]+" | tail -1
"$FF" -hide_banner -i "$OUT" 2>&1 | grep -oE "Duration: [0-9:.]+" || true
"$FF" -hide_banner -i "$OUT" -i "$IN" -lavfi "[0:v][1:v]ssim" -f null - 2>&1 | grep -oE "All:[0-9.]+"
