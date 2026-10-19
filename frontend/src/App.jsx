import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import LivePlayer from "./LivePlayer.jsx";
import { usePolling } from "./usePolling.js";

const HLS_URL = import.meta.env.VITE_HLS_URL || "http://localhost:8888/annotated/index.m3u8";

// Bar colours = the actual vehicle colour, with a visible outline for white/yellow.
const SWATCH = {
  white: "#f4f4f2", black: "#1b1b1d", silver: "#b8bcc2", grey: "#7d838c", gray: "#7d838c",
  red: "#c8312b", maroon: "#7a1f2b", blue: "#2c5fb3", green: "#2f8a57", yellow: "#f0c419",
  orange: "#e8822a", brown: "#7b5334", gold: "#c9a227", unknown: "#d3d8de",
};
const swatch = (c) => SWATCH[(c || "unknown").toLowerCase()] || SWATCH.unknown;

const timeFmt = new Intl.DateTimeFormat([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
const fmtTime = (ts) => (ts ? timeFmt.format(new Date(ts)) : "–");

function Stat({ label, value, tone }) {
  return (
    <div className={`stat ${tone || ""}`}>
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
    </div>
  );
}

export default function App() {
  const summary = usePolling("/api/summary");
  const events = usePolling("/api/events?limit=25");
  const s = summary.data;
  const online = !summary.error && !!s;
  const maxColor = Math.max(1, ...(s?.colors.map((c) => c.count) || [1]));
  const minutes = (s?.perMinute || []).map((m) => ({
    label: new Intl.DateTimeFormat([], { hour: "2-digit", minute: "2-digit" }).format(new Date(m.minute)),
    count: m.count,
  }));

  return (
    <div className="shell">
      <header className="top">
        <div>
          <h1>Laneview</h1>
          <p>Vehicles crossing the line, counted and colour-tagged in real time</p>
        </div>
        <div className={`pill ${online ? "ok" : "bad"}`} role="status">
          <span className="dot" />
          {online ? `Database connected · last count ${fmtTime(s.lastEventAt)}` : "API unreachable – check the backend"}
        </div>
      </header>

      <main className="grid">
        <section className="panel video" aria-label="Live feed">
          <LivePlayer src={HLS_URL} />
          <div className="video-foot">Annotated stream from DeepStream: boxes, track IDs and the counting line.</div>
        </section>

        <section className="panel totals" aria-label="Totals">
          <Stat label="Total vehicles" value={s?.total ?? "–"} tone="big" />
          <div className="split">
            <Stat label="Inbound" value={s?.directions?.IN ?? 0} tone="in" />
            <Stat label="Outbound" value={s?.directions?.OUT ?? 0} tone="out" />
          </div>
        </section>

        <section className="panel colors" aria-label="Colour breakdown">
          <h2>By colour</h2>
          {!s?.colors.length ? (
            <p className="empty">No vehicles counted yet. Counts appear here as cars cross the line.</p>
          ) : (
            <ul className="bars">
              {s.colors.map((c) => (
                <li key={c.color}>
                  <span className="name">{c.color}</span>
                  <span className="track">
                    <span className="fill" style={{ width: `${(c.count / maxColor) * 100}%`, background: swatch(c.color) }} />
                  </span>
                  <span className="num">{c.count}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="panel rate" aria-label="Counts per minute">
          <h2>Counts per minute, last 30 min</h2>
          <div className="chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={minutes} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
                <CartesianGrid vertical={false} stroke="#dde2e7" />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                <Tooltip cursor={{ fill: "#eef1f4" }} />
                <Bar dataKey="count" fill="#0f766e" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="panel table" aria-label="Recent events">
          <h2>Latest crossings</h2>
          <div className="scroll">
            <table>
              <thead>
                <tr><th>Time</th><th>Vehicle</th><th>Colour</th><th>Direction</th><th>Confidence</th><th>Camera</th></tr>
              </thead>
              <tbody>
                {(events.data || []).map((e) => (
                  <tr key={e.id}>
                    <td>{fmtTime(e.timestamp)}</td>
                    <td>#{e.vehicle_id}</td>
                    <td><span className="chip" style={{ background: swatch(e.color) }} />{e.color}</td>
                    <td><span className={`dir ${e.direction}`}>{e.direction === "IN" ? "Inbound" : "Outbound"}</span></td>
                    <td>{e.confidence != null ? `${Math.round(e.confidence * 100)}%` : "–"}</td>
                    <td>{e.stream_id}</td>
                  </tr>
                ))}
                {!events.data?.length && (
                  <tr><td colSpan="6" className="empty">Waiting for the first crossing.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </main>
    </div>
  );
}
