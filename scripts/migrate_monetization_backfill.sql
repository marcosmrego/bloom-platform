BEGIN;

CREATE TABLE IF NOT EXISTS monetization_proposals (
    id                BIGSERIAL PRIMARY KEY,
    tenant_id         INT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    post_id           INT NOT NULL,
    idempotency_key   VARCHAR(128) NOT NULL,
    request_hash      CHAR(64) NOT NULL,
    link_type         VARCHAR(20) NOT NULL
                      CHECK (link_type IN ('product', 'search', 'no_match')),
    product_asin      VARCHAR(20),
    product_title     VARCHAR(500),
    destination_url   VARCHAR(2000),
    rationale         VARCHAR(2000) NOT NULL,
    evidence          JSONB NOT NULL DEFAULT '[]'::jsonb,
    proposed_by       VARCHAR(100) NOT NULL DEFAULT 'hermes-bloom',
    status            VARCHAR(20) NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending', 'approved', 'rejected', 'superseded')),
    reviewer          VARCHAR(100),
    review_note       TEXT,
    reviewed_at       TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, idempotency_key),
    FOREIGN KEY (post_id, tenant_id)
        REFERENCES posts(id, tenant_id) ON DELETE CASCADE,
    CHECK (link_type <> 'product' OR (product_asin IS NOT NULL AND product_title IS NOT NULL AND destination_url IS NOT NULL)),
    CHECK (link_type <> 'search' OR destination_url IS NOT NULL),
    CHECK (link_type <> 'no_match' OR (product_asin IS NULL AND destination_url IS NULL))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_monetization_pending_post
    ON monetization_proposals(post_id)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_monetization_proposals_queue
    ON monetization_proposals(tenant_id, status, created_at);

GRANT SELECT, INSERT, UPDATE ON monetization_proposals TO bloom_app;
GRANT USAGE, SELECT ON SEQUENCE monetization_proposals_id_seq TO bloom_app;

COMMIT;
