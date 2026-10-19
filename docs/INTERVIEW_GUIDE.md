# Interview Guide – what to learn and how to explain it

## 1. 60-second pitch
"I built an end-to-end pipeline: FFmpeg loops a traffic video into MediaMTX as RTSP. A DeepStream pipeline pulls that stream, detects vehicles with TrafficCamNet, tracks them with NvDCF so each car has a stable ID, classifies colour with a secondary classifier on the car crops, and uses nvdsanalytics to detect a line crossing. On each crossing a probe sends an event to a queue; a writer thread inserts it into PostgreSQL. An Express API exposes the data and a React dashboard polls it, plus plays the annotated HLS stream."

## 2. Architecture walk-through (MediaMTX → React)
1. **FFmpeg → MediaMTX (RTSP).** MediaMTX is a media router: one publisher, many readers, converts to HLS/WebRTC.
2. **MediaMTX → DeepStream.** `nvurisrcbin` decodes RTSP on the GPU (NVDEC), reconnects on failure.
3. **nvstreammux** batches frames and resizes to 1280×720 (batch size = number of streams).
4. **nvinfer PGIE** → bounding boxes + class (TensorRT engine).
5. **nvtracker** → `object_id` per object across frames.
6. **nvinfer SGIE** → colour label for each car crop.
7. **nvdsanalytics** → line-crossing metadata (`lcStatus`).
8. **Probe** → reads metadata, builds event, enqueues.
9. **Writer thread → PostgreSQL.**
10. **Express API → React.** Dashboard polls every 1.5 s.
11. **Video path (bonus):** nvdsosd draws boxes → H.264 encode → `rtspclientsink` → MediaMTX `/annotated` → HLS → hls.js `<video>`.

## 3. Concepts you must understand
- **GStreamer:** elements, pads, caps, `pad-added` (dynamic pads), buses, pad probes.
- **DeepStream metadata hierarchy:** `NvDsBatchMeta → NvDsFrameMeta → NvDsObjectMeta → NvDsClassifierMeta → NvDsLabelInfo`. Also `obj_user_meta_list` for analytics.
- **PGIE vs SGIE:** `process-mode=1` (full frame) vs `2` (objects). `gie-unique-id`, `operate-on-gie-id`, `operate-on-class-ids`.
- **Why a tracker is mandatory:** detections are per-frame and anonymous. Without IDs one car is counted every frame it overlaps the line. NvDCF = discriminative correlation filter + detector association (more robust to missed detections than IOU; cheaper than DeepSORT re-ID).
- **Why `classifier-async-mode=1` needs a tracker:** results are cached per tracker ID and attached to later frames.
- **TensorRT:** first run builds an `.engine` (slow); later runs reuse it. `network-mode`: 0 FP32, 1 INT8, 2 FP16.
- **Line crossing geometry:** a segment-intersection test on the object's bottom-centre between consecutive frames; direction = sign of the cross-product with the direction vector. `mode=strict` means count only the specified direction.
- **Python probe cost:** probe runs inside the streaming thread – keep it fast, never do blocking I/O (hence the queue).
- **Database:** why `TIMESTAMPTZ`, indexes on timestamp/color, `UNIQUE(session_id, vehicle_id)`, `ON CONFLICT DO NOTHING`, `date_trunc` for time buckets.
- **React:** hooks (`useEffect`, `useState`), polling with cleanup, hls.js lifecycle, empty/error states.
- **Streaming protocols:** RTSP (low latency, not browser-playable) vs HLS (browser, 2–6 s delay; LL-HLS ~1–2 s) vs WebRTC (sub-second, more complex).

## 4. Code walk-through map (`deepstream/app.py`)
| Part | What to say |
|---|---|
| `make()` / `build_pipeline()` | Creates and links elements in order; dynamic source pad linked in `on_pad_added` |
| `analytics_probe()` | Iterates batch → frame → object; bounding box in `obj.rect_params`; tracker ID in `obj.object_id` |
| `get_color()` | Walks `classifier_meta_list`, filters on `unique_component_id == 2` |
| `crossed_lines()` | Reads `NvDsAnalyticsObjInfo.lcStatus` |
| `State.counted` | One count per vehicle |
| `EventWriter` | Queue + thread, reconnect, no lost events |

## 5. Likely questions (with short answers)
- **Why queue instead of inserting in the probe?** Probe runs in the pipeline thread; a slow DB write would drop frames.
- **Why a tracker and not just a line check?** Need identity across frames; also gives colour caching.
- **What if the same car gets a new ID (ID switch/occlusion)?** Could double count; mitigate with larger `maxShadowTrackingAge`, ReID tracker, or a time window. Be honest about this limitation.
- **How would you scale to many cameras?** Raise `batch-size`, one source per mux pad, add `stream_id` (already in the schema), shard workers; Kafka/ZeroMQ between pipeline and DB.
- **Why polling, not WebSockets?** Simpler/robust at this scale; SSE/WebSocket or Postgres `LISTEN/NOTIFY` is the upgrade path.
- **How did you test accuracy?** Count a clip manually and compare; report precision/recall of counts and colour accuracy.
- **How would you improve colour accuracy?** Fine-tune a TAO classifier on local data, handle lighting, crop only the car body.
- **Why MediaMTX?** One ingest, many consumers, protocol conversion (RTSP→HLS/WebRTC) with a single binary.
- **What's FP16/INT8?** Reduced precision for speed; INT8 needs a calibration file.
- **Security?** DB creds via env, API is read-only, restrict CORS, put MediaMTX auth in front for real cameras.

## 6. Walkthrough-video checklist (camera on)
1. Intro + goals (30 s). 2. Diagram (1 min). 3. Code: `build_pipeline`, `analytics_probe`, `EventWriter` (3 min). 4. Live demo in this order: MediaMTX + VLC playing `/traffic` → `app.py` logs → `psql` query showing new rows → dashboard updating + annotated video. 5. Mention limitations and next steps.

## 7. Practise before recording
- Run everything from scratch on a clean clone using only the README.
- Tune the line to your video and verify a manual count against the DB.
- Know which DeepStream version you used and where the colour model came from.
