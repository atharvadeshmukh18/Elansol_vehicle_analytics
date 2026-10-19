#!/usr/bin/env bash
# Phase 1: loop an MP4 traffic video into MediaMTX as a live RTSP stream.
# Usage: ./scripts/publish_stream.sh path/to/traffic.mp4 [rtsp://localhost:8554/traffic]
set -euo pipefail
VIDEO="${1:?usage: publish_stream.sh <video.mp4> [rtsp_url]}"
URL="${2:-rtsp://localhost:8554/traffic}"
# -re             : read at native frame rate (behave like a live camera)
# -stream_loop -1 : loop forever
# libx264 zerolatency baseline : widely decodable, low latency, no B-frames
ffmpeg -re -stream_loop -1 -i "$VIDEO" \
  -vf scale=1280:720 -an \
  -c:v libx264 -preset veryfast -tune zerolatency -profile:v baseline -g 30 -pix_fmt yuv420p \
  -f rtsp -rtsp_transport tcp "$URL"
