-- One row per line-crossing ("count") event.
CREATE TABLE IF NOT EXISTS vehicle_events (
    id           BIGSERIAL PRIMARY KEY,
    vehicle_id   INTEGER      NOT NULL,                -- tracker ID (unique within a session)
    session_id   VARCHAR(32)  NOT NULL,                -- pipeline run, because tracker IDs restart
    color        VARCHAR(20)  NOT NULL DEFAULT 'unknown',
    vehicle_type VARCHAR(20)  NOT NULL DEFAULT 'car',
    direction    VARCHAR(3)   NOT NULL CHECK (direction IN ('IN','OUT')),
    confidence   REAL,
    stream_id    VARCHAR(64)  NOT NULL DEFAULT 'cam-0',
    timestamp    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (session_id, vehicle_id)                    -- DB-level guard: a vehicle counts once
);
CREATE INDEX IF NOT EXISTS idx_events_ts    ON vehicle_events (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_events_color ON vehicle_events (color);
