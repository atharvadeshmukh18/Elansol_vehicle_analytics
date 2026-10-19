# Laneview – Real-Time Vehicle Analytics Pipeline

RTSP video → **MediaMTX** → **NVIDIA DeepStream** (detect → track → classify colour → line-cross) → **PostgreSQL** → **REST API** → **React dashboard**.

```
 MP4/Camera ──FFmpeg──► MediaMTX ──RTSP /traffic──► DeepStream (GPU)
                          ▲  │                         │ nvinfer  (PGIE: TrafficCamNet)
        HLS /annotated ───┘  │                         │ nvtracker (NvDCF)
              ▲              │                         │ nvinfer  (SGIE: car colour)
              │              │                         │ nvdsanalytics (line crossing)
   RTSP /annotated ◄─────────┴─── encoded OSD video ◄──┤
                                                       │ probe → queue → writer thread
 React (Vite) ◄── /api ── Express API ◄── PostgreSQL ◄─┘
```

## Prerequisites
| Component | Notes |
|---|---|
| NVIDIA GPU + driver | Required by DeepStream |
| DeepStream SDK 6.x/7.x | Install per NVIDIA docs (or use the `nvcr.io/nvidia/deepstream` container) |
| DeepStream Python bindings (`pyds`) | https://github.com/NVIDIA-AI-IOT/deepstream_python_apps (wheel matching your DS version) |
| GStreamer RTSP sink | `sudo apt install gstreamer1.0-rtsp` (provides `rtspclientsink`) |
| Docker + Compose | MediaMTX, PostgreSQL, API |
| FFmpeg | publishes the test video |
| Node.js 18+ | React dashboard |
| Python 3.8+ | `pip install -r deepstream/requirements.txt` |

## Run (5 terminals)
```bash
# 1. Infrastructure: MediaMTX + PostgreSQL (+ schema) + API
docker compose up -d

# 2. Publish a looping traffic video as a live RTSP stream  (Phase 1)
./scripts/publish_stream.sh ~/videos/traffic.mp4
#    verify: vlc rtsp://localhost:8554/traffic

# 3. Models (see docs/MODELS.md) then start the DeepStream pipeline  (Phase 2+3)
cd deepstream && python3 app.py --input rtsp://localhost:8554/traffic -v

# 4. Dashboard (Phase 4)
cd frontend && cp .env.example .env && npm install && npm run dev   # http://localhost:5173

# 5. Watch the DB fill
docker compose exec postgres psql -U vision -d vehicles -c "SELECT * FROM vehicle_events ORDER BY id DESC LIMIT 10;"
```

## Configuration
| File | Purpose |
|---|---|
| `deepstream/config/pgie_trafficcamnet.txt` | Primary detector (nvinfer). Threshold, model paths, classes |
| `deepstream/config/sgie_color_config.txt` | Secondary classifier: `process-mode=2`, `operate-on-gie-id=1`, `operate-on-class-ids=0` → colour only on detected cars |
| `deepstream/config/analytics_config.txt` | **Counting line coordinates** – edit to match your video (1280×720 space). Two lines with opposite direction vectors give IN / OUT |
| `deepstream/app.py` (`TRACKER_CFG`) | NvDCF tracker config (swap for IOU/DeepSORT yml if desired) |
| `mediamtx/mediamtx.yml` | RTSP/HLS/WebRTC ports, CORS for browser playback |
| `db/init.sql` | Schema |

Environment variables: `DATABASE_URL`, `RTSP_INPUT`, `RTSP_OUTPUT`, `VITE_HLS_URL`.

## Design notes
- **No double counting:** tracker ID + an in-memory `counted` set in the probe + `UNIQUE(session_id, vehicle_id)` in the DB.
- **Async persistence:** the GStreamer probe only enqueues; a writer thread does the INSERT with reconnect/retry, so DB latency never stalls inference. (A ZeroMQ broker is a drop-in alternative: `submit()` would `socket.send_json` and a separate consumer would insert.)
- **Async colour classification:** the SGIE can finish after the first frames of a track; the probe remembers the last colour per tracker ID.
- **Bonus:** DeepStream publishes the annotated video back to MediaMTX (`/annotated`); the React app plays it via HLS.

## Troubleshooting
- *No `rtspclientsink`* → install `gstreamer1.0-rtsp`.
- *No counts* → the line is not where cars cross; adjust `analytics_config.txt`.
- *Colour always `unknown`* → colour model missing/not loaded, or objects smaller than 64 px.
- *Video black in browser* → check HLS URL `http://localhost:8888/annotated/index.m3u8` in VLC.
