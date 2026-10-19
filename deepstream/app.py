#!/usr/bin/env python3
"""
Real-time vehicle analytics with NVIDIA DeepStream (Python bindings / pyds).

Pipeline:
  nvurisrcbin(RTSP) -> nvstreammux -> nvinfer[PGIE: detect] -> nvtracker[NvDCF: IDs]
    -> nvinfer[SGIE: colour] -> nvdsanalytics[line crossing] -> (probe) -> nvdsosd
    -> encode H.264 -> rtspclientsink (MediaMTX 'annotated' path, shown in the dashboard)

The probe on the analytics src pad is where counting + DB insertion are triggered.
"""
import argparse, logging, os, queue, sys, threading, time, uuid
from datetime import datetime, timezone

import gi
gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gst
import psycopg2
import pyds

log = logging.getLogger("vehicle-analytics")
HERE = os.path.dirname(os.path.abspath(__file__))
CFG = lambda name: os.path.join(HERE, "config", name)
TRACKER_LIB = "/opt/nvidia/deepstream/deepstream/lib/libnvds_nvmultiobjecttracker.so"
TRACKER_CFG = "/opt/nvidia/deepstream/deepstream/samples/configs/deepstream-app/config_tracker_NvDCF_perf.yml"

PGIE_CLASS_VEHICLE = 0          # TrafficCamNet: 0=car, 1=person, 2=bicycle, 3=road_sign
MUX_W, MUX_H = 1280, 720


# --------------------------------------------------------------------------- #
# Persistence: probe never touches the DB directly (would block the GPU pipeline).
# It pushes events on a queue; this thread batches them into PostgreSQL.
# --------------------------------------------------------------------------- #
class EventWriter(threading.Thread):
    SQL = ("INSERT INTO vehicle_events "
           "(vehicle_id, session_id, color, vehicle_type, direction, confidence, stream_id, timestamp) "
           "VALUES (%(vehicle_id)s,%(session_id)s,%(color)s,%(vehicle_type)s,%(direction)s,"
           "%(confidence)s,%(stream_id)s,%(timestamp)s) ON CONFLICT DO NOTHING")

    def __init__(self, dsn):
        super().__init__(daemon=True, name="db-writer")
        self.dsn, self.q, self.conn, self._halt = dsn, queue.Queue(maxsize=10000), None, False

    def submit(self, event):
        try:
            self.q.put_nowait(event)
        except queue.Full:
            log.error("DB queue full, dropping event %s", event)

    def _connect(self):
        while not self._halt:
            try:
                self.conn = psycopg2.connect(self.dsn)
                self.conn.autocommit = True
                log.info("Connected to PostgreSQL")
                return
            except Exception as exc:
                log.warning("DB connect failed (%s); retry in 2s", exc)
                time.sleep(2)

    def run(self):
        self._connect()
        while not self._halt:
            try:
                ev = self.q.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                with self.conn.cursor() as cur:
                    cur.execute(self.SQL, ev)
                log.info("Stored: id=%s %s %s", ev["vehicle_id"], ev["color"], ev["direction"])
            except Exception as exc:
                log.error("Insert failed (%s); reconnecting", exc)
                self.q.put(ev)                      # don't lose the event
                self._connect()

    def stop(self):
        self._halt = True


# --------------------------------------------------------------------------- #
# Probe state
# --------------------------------------------------------------------------- #
class State:
    def __init__(self, writer, session_id, stream_id):
        self.writer, self.session_id, self.stream_id = writer, session_id, stream_id
        self.colors = {}           # tracker_id -> last known colour (SGIE is async)
        self.counted = set()       # tracker_ids already counted => no double counting
        self.totals = {"IN": 0, "OUT": 0}


def get_color(obj_meta):
    """Walk object -> classifier_meta_list -> label_info_list and return the SGIE label."""
    l_cls = obj_meta.classifier_meta_list
    while l_cls is not None:
        cls_meta = pyds.NvDsClassifierMeta.cast(l_cls.data)
        if cls_meta.unique_component_id == 2:       # our colour SGIE
            l_lbl = cls_meta.label_info_list
            if l_lbl is not None:
                return pyds.NvDsLabelInfo.cast(l_lbl.data).result_label
        l_cls = l_cls.next
    return None


def crossed_lines(obj_meta):
    """Return line names crossed by this object in the current frame (from nvdsanalytics)."""
    l_user = obj_meta.obj_user_meta_list
    while l_user is not None:
        user_meta = pyds.NvDsUserMeta.cast(l_user.data)
        if user_meta.base_meta.meta_type == pyds.nvds_get_user_meta_type("NVIDIA.DSANALYTICSOBJ.USER_META"):
            return list(pyds.NvDsAnalyticsObjInfo.cast(user_meta.user_meta_data).lcStatus)
        l_user = l_user.next
    return []


def analytics_probe(pad, info, state: State):
    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(info.get_buffer()))
    l_frame = batch_meta.frame_meta_list
    while l_frame is not None:
        frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        l_obj = frame_meta.obj_meta_list
        while l_obj is not None:
            obj = pyds.NvDsObjectMeta.cast(l_obj.data)
            if obj.class_id == PGIE_CLASS_VEHICLE:
                tid = obj.object_id                              # ID assigned by nvtracker
                color = get_color(obj)
                if color:
                    state.colors[tid] = color
                for line in crossed_lines(obj):                  # 'IN' or 'OUT'
                    if tid in state.counted:
                        continue
                    state.counted.add(tid)
                    state.totals[line] = state.totals.get(line, 0) + 1
                    bbox = obj.rect_params
                    state.writer.submit({
                        "vehicle_id": int(tid), "session_id": state.session_id,
                        "color": state.colors.get(tid, "unknown"), "vehicle_type": "car",
                        "direction": line, "confidence": float(obj.confidence),
                        "stream_id": state.stream_id, "timestamp": datetime.now(timezone.utc),
                    })
                    log.debug("cross tid=%s bbox=(%d,%d,%d,%d)", tid, bbox.left, bbox.top, bbox.width, bbox.height)
            try:
                l_obj = l_obj.next
            except StopIteration:
                break

        # On-screen counter
        disp = pyds.nvds_acquire_display_meta_from_pool(batch_meta)
        disp.num_labels = 1
        txt = disp.text_params[0]
        txt.display_text = f"IN: {state.totals['IN']}   OUT: {state.totals['OUT']}"
        txt.x_offset, txt.y_offset = 20, 20
        txt.font_params.font_name, txt.font_params.font_size = "Serif", 18
        txt.font_params.font_color.set(1.0, 1.0, 1.0, 1.0)
        txt.set_bg_clr = 1
        txt.text_bg_clr.set(0.0, 0.0, 0.0, 0.6)
        pyds.nvds_add_display_meta_to_frame(frame_meta, disp)
        try:
            l_frame = l_frame.next
        except StopIteration:
            break
    return Gst.PadProbeReturn.OK


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #
def make(factory, name, **props):
    el = Gst.ElementFactory.make(factory, name)
    if not el:
        raise RuntimeError(f"Cannot create '{factory}' (is DeepStream / the plugin installed?)")
    for k, v in props.items():
        el.set_property(k.replace("_", "-"), v)
    return el


def build_pipeline(args, state):
    pipeline = Gst.Pipeline()
    source = make("nvurisrcbin", "source", uri=args.input, rtsp_reconnect_interval=5)
    mux = make("nvstreammux", "mux", batch_size=1, width=MUX_W, height=MUX_H,
               batched_push_timeout=40000, live_source=1)
    pgie = make("nvinfer", "pgie", config_file_path=CFG("pgie_trafficcamnet.txt"))
    tracker = make("nvtracker", "tracker", ll_lib_file=TRACKER_LIB, ll_config_file=TRACKER_CFG,
                   tracker_width=640, tracker_height=384)
    sgie = make("nvinfer", "sgie-color", config_file_path=CFG("sgie_color_config.txt"))
    analytics = make("nvdsanalytics", "analytics", config_file=CFG("analytics_config.txt"))
    conv1 = make("nvvideoconvert", "conv1")
    osd = make("nvdsosd", "osd")
    conv2 = make("nvvideoconvert", "conv2")
    caps = make("capsfilter", "caps", caps=Gst.Caps.from_string("video/x-raw(memory:NVMM),format=I420"))
    enc = make("nvv4l2h264enc", "enc", bitrate=3000000, iframeinterval=30)
    parse = make("h264parse", "parse")
    sink = make("rtspclientsink", "sink", location=args.output, protocols="tcp")

    for el in (source, mux, pgie, tracker, sgie, analytics, conv1, osd, conv2, caps, enc, parse, sink):
        pipeline.add(el)

    # nvurisrcbin has dynamic pads -> link when its video pad appears
    def on_pad_added(_src, pad):
        if pad.get_current_caps().get_structure(0).get_name().startswith("video"):
            pad.link(mux.get_request_pad("sink_0"))
    source.connect("pad-added", on_pad_added)

    chain = [mux, pgie, tracker, sgie, analytics, conv1, osd, conv2, caps, enc, parse, sink]
    for a, b in zip(chain, chain[1:]):
        if not a.link(b):
            raise RuntimeError(f"Failed to link {a.get_name()} -> {b.get_name()}")

    analytics.get_static_pad("src").add_probe(Gst.PadProbeType.BUFFER, analytics_probe, state)
    return pipeline


def main():
    p = argparse.ArgumentParser(description="DeepStream vehicle analytics")
    p.add_argument("--input", default=os.getenv("RTSP_INPUT", "rtsp://localhost:8554/traffic"))
    p.add_argument("--output", default=os.getenv("RTSP_OUTPUT", "rtsp://localhost:8554/annotated"))
    p.add_argument("--db", default=os.getenv("DATABASE_URL", "postgres://vision:vision@localhost:5432/vehicles"))
    p.add_argument("--stream-id", default="cam-0")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    Gst.init(None)
    writer = EventWriter(args.db)
    writer.start()
    state = State(writer, uuid.uuid4().hex[:12], args.stream_id)
    pipeline = build_pipeline(args, state)

    loop = GLib.MainLoop()
    bus = pipeline.get_bus()
    bus.add_signal_watch()

    def on_message(_bus, msg):
        if msg.type == Gst.MessageType.EOS:
            log.info("EOS"); loop.quit()
        elif msg.type == Gst.MessageType.ERROR:
            err, dbg = msg.parse_error()
            log.error("Pipeline error: %s (%s)", err, dbg); loop.quit()
    bus.connect("message", on_message)

    pipeline.set_state(Gst.State.PLAYING)
    log.info("Running. session=%s input=%s", state.session_id, args.input)
    try:
        loop.run()
    except KeyboardInterrupt:
        pass
    finally:
        pipeline.set_state(Gst.State.NULL)
        time.sleep(1)           # let the writer drain
        writer.stop()


if __name__ == "__main__":
    sys.exit(main())
