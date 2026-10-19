import { useEffect, useRef, useState } from "react";
import Hls from "hls.js";

// Bonus: plays the annotated (bounding-box) stream that DeepStream publishes to MediaMTX.
export default function LivePlayer({ src }) {
  const ref = useRef(null);
  const [status, setStatus] = useState("connecting");

  useEffect(() => {
    const video = ref.current;
    let hls;
    let retry;
    const start = () => {
      if (Hls.isSupported()) {
        hls = new Hls({ lowLatencyMode: true, liveSyncDurationCount: 2 });
        hls.loadSource(src);
        hls.attachMedia(video);
        hls.on(Hls.Events.MANIFEST_PARSED, () => { setStatus("live"); video.play().catch(() => {}); });
        hls.on(Hls.Events.ERROR, (_e, d) => {
          if (d.fatal) { setStatus("offline"); hls.destroy(); retry = setTimeout(start, 4000); }
        });
      } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
        video.src = src; setStatus("live");
      }
    };
    start();
    return () => { clearTimeout(retry); hls && hls.destroy(); };
  }, [src]);

  return (
    <div className="player">
      <video ref={ref} muted playsInline controls={false} aria-label="Live annotated camera feed" />
      {status !== "live" && (
        <div className="player-empty">
          <strong>{status === "connecting" ? "Connecting to the stream…" : "No video from DeepStream yet"}</strong>
          <span>Start the publisher and <code>deepstream/app.py</code>; this retries automatically.</span>
        </div>
      )}
    </div>
  );
}
