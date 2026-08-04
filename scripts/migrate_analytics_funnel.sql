BEGIN;

CREATE TABLE IF NOT EXISTS page_views (
    id             BIGSERIAL PRIMARY KEY,
    tenant_id      INT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    post_id        INT NOT NULL,
    session_hash   CHAR(64) NOT NULL,
    view_date      DATE NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC')::date,
    path           VARCHAR(500) NOT NULL,
    referrer_host  VARCHAR(255),
    utm_source     VARCHAR(255),
    utm_medium     VARCHAR(255),
    utm_campaign   VARCHAR(255),
    utm_content    VARCHAR(255),
    utm_term       VARCHAR(255),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (post_id, tenant_id)
        REFERENCES posts(id, tenant_id) ON DELETE CASCADE,
    UNIQUE (tenant_id, post_id, session_hash, view_date)
);

CREATE INDEX IF NOT EXISTS idx_page_views_post_date
    ON page_views(tenant_id, post_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_page_views_source_date
    ON page_views(tenant_id, utm_source, referrer_host, created_at DESC);

ALTER TABLE clicks ADD COLUMN IF NOT EXISTS session_hash CHAR(64);
ALTER TABLE clicks ADD COLUMN IF NOT EXISTS referrer_host VARCHAR(255);
ALTER TABLE clicks ADD COLUMN IF NOT EXISTS destination_host VARCHAR(255);
ALTER TABLE clicks ADD COLUMN IF NOT EXISTS utm_source VARCHAR(255);
ALTER TABLE clicks ADD COLUMN IF NOT EXISTS utm_medium VARCHAR(255);
ALTER TABLE clicks ADD COLUMN IF NOT EXISTS utm_campaign VARCHAR(255);
ALTER TABLE clicks ADD COLUMN IF NOT EXISTS utm_content VARCHAR(255);
ALTER TABLE clicks ADD COLUMN IF NOT EXISTS utm_term VARCHAR(255);

CREATE INDEX IF NOT EXISTS idx_clicks_post_date
    ON clicks(tenant_id, post_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_clicks_source_date
    ON clicks(tenant_id, utm_source, referrer_host, created_at DESC);

GRANT SELECT, INSERT ON page_views TO bloom_app;
GRANT USAGE, SELECT ON SEQUENCE page_views_id_seq TO bloom_app;
GRANT SELECT, INSERT ON clicks TO bloom_app;

COMMIT;
