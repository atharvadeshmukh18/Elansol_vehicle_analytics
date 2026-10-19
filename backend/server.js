// REST API between PostgreSQL and the React dashboard (read-only).
const express = require("express");
const cors = require("cors");
const { Pool } = require("pg");

const pool = new Pool({
  connectionString: process.env.DATABASE_URL || "postgres://vision:vision@localhost:5432/vehicles",
});
const app = express();
app.use(cors());

const wrap = (fn) => (req, res) => fn(req, res).catch((e) => {
  console.error(e);
  res.status(500).json({ error: "database_error" });
});

app.get("/api/health", wrap(async (_req, res) => {
  await pool.query("SELECT 1");
  res.json({ ok: true });
}));

// Aggregates for the metrics panel + charts
app.get("/api/summary", wrap(async (_req, res) => {
  const [total, colors, dirs, perMinute, last] = await Promise.all([
    pool.query("SELECT COUNT(*)::int AS n FROM vehicle_events"),
    pool.query("SELECT color, COUNT(*)::int AS count FROM vehicle_events GROUP BY color ORDER BY count DESC"),
    pool.query("SELECT direction, COUNT(*)::int AS count FROM vehicle_events GROUP BY direction"),
    pool.query(`SELECT date_trunc('minute', timestamp) AS minute, COUNT(*)::int AS count
                FROM vehicle_events WHERE timestamp > now() - interval '30 minutes'
                GROUP BY 1 ORDER BY 1`),
    pool.query("SELECT MAX(timestamp) AS ts FROM vehicle_events"),
  ]);
  res.json({
    total: total.rows[0].n,
    colors: colors.rows,
    directions: Object.fromEntries(dirs.rows.map((r) => [r.direction, r.count])),
    perMinute: perMinute.rows,
    lastEventAt: last.rows[0].ts,
  });
}));

// Most recent events (table)
app.get("/api/events", wrap(async (req, res) => {
  const limit = Math.min(parseInt(req.query.limit, 10) || 25, 200);
  const { rows } = await pool.query(
    `SELECT id, vehicle_id, color, vehicle_type, direction, confidence, stream_id, timestamp
     FROM vehicle_events ORDER BY timestamp DESC, id DESC LIMIT $1`, [limit]);
  res.json(rows);
}));

const port = process.env.PORT || 4000;
app.listen(port, () => console.log(`API listening on :${port}`));
