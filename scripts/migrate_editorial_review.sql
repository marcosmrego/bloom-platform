BEGIN;

CREATE TABLE IF NOT EXISTS post_reviews (
    id          BIGSERIAL PRIMARY KEY,
    tenant_id   INT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    post_id     INT NOT NULL,
    action      VARCHAR(20) NOT NULL
                CHECK (action IN ('updated', 'approved', 'rejected')),
    reviewer    VARCHAR(100) NOT NULL,
    note        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (post_id, tenant_id)
        REFERENCES posts(id, tenant_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_post_reviews_post
    ON post_reviews(post_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_post_reviews_tenant
    ON post_reviews(tenant_id, created_at DESC);

COMMIT;
