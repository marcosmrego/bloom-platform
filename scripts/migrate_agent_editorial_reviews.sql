BEGIN;

CREATE TABLE IF NOT EXISTS agent_editorial_reviews (
    id                BIGSERIAL PRIMARY KEY,
    tenant_id         INT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    post_id           INT NOT NULL,
    idempotency_key   VARCHAR(128) NOT NULL,
    request_hash      CHAR(64) NOT NULL,
    input_hash        CHAR(64) NOT NULL,
    recommendation    VARCHAR(20) NOT NULL
                      CHECK (recommendation IN ('pass', 'needs_changes', 'block')),
    risk_level        VARCHAR(10) NOT NULL
                      CHECK (risk_level IN ('low', 'medium', 'high')),
    summary           TEXT NOT NULL,
    checks            JSONB NOT NULL DEFAULT '[]'::jsonb,
    suggested_edits   JSONB NOT NULL DEFAULT '[]'::jsonb,
    status            VARCHAR(20) NOT NULL DEFAULT 'current'
                      CHECK (status IN ('current', 'superseded')),
    reviewer_agent    VARCHAR(100) NOT NULL DEFAULT 'hermes-reviewer',
    human_decision    VARCHAR(20)
                      CHECK (human_decision IN ('approved', 'rejected')),
    human_reviewer    VARCHAR(100),
    human_note        TEXT,
    human_decided_at  TIMESTAMPTZ,
    agreement         BOOLEAN,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, idempotency_key),
    FOREIGN KEY (post_id, tenant_id)
        REFERENCES posts(id, tenant_id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_editorial_reviews_current
    ON agent_editorial_reviews(post_id)
    WHERE status = 'current';

CREATE INDEX IF NOT EXISTS idx_agent_editorial_reviews_queue
    ON agent_editorial_reviews(tenant_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_agent_editorial_reviews_agreement
    ON agent_editorial_reviews(human_decided_at DESC)
    WHERE human_decision IS NOT NULL;

GRANT SELECT, INSERT, UPDATE ON agent_editorial_reviews TO bloom_app;
GRANT USAGE, SELECT ON SEQUENCE agent_editorial_reviews_id_seq TO bloom_app;

COMMIT;
