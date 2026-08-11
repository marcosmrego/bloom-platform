BEGIN;

CREATE TABLE IF NOT EXISTS traffic_recovery_attempts (
    id BIGSERIAL PRIMARY KEY,
    tenant_id INT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    post_id INT NOT NULL,
    diagnosis VARCHAR(40) NOT NULL CHECK (diagnosis IN (
        'indexing_unknown', 'not_indexed', 'low_impressions', 'low_ctr',
        'missing_internal_links', 'distribution_gap', 'low_demand'
    )),
    action VARCHAR(40) NOT NULL CHECK (action IN (
        'request_indexing', 'generate_social_package', 'propose_internal_links',
        'propose_metadata', 'monitor', 'escalate_human'
    )),
    rationale VARCHAR(2000) NOT NULL,
    evidence JSONB NOT NULL DEFAULT '[]',
    status VARCHAR(20) NOT NULL CHECK (status IN ('completed', 'blocked', 'ineffective')),
    idempotency_key VARCHAR(128) NOT NULL UNIQUE,
    agent_name VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (post_id, tenant_id) REFERENCES posts(id, tenant_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_traffic_recovery_post_created
    ON traffic_recovery_attempts(tenant_id, post_id, created_at DESC);

COMMIT;
