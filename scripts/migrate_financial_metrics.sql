BEGIN;

CREATE TABLE IF NOT EXISTS financial_entries (
    id            BIGSERIAL PRIMARY KEY,
    tenant_id     INT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    post_id       INT,
    provider      VARCHAR(20) NOT NULL CHECK (provider IN ('amazon', 'adsense', 'adcash', 'manual')),
    entry_type    VARCHAR(10) NOT NULL CHECK (entry_type IN ('revenue', 'cost')),
    occurred_on   DATE NOT NULL,
    amount        NUMERIC(14, 4) NOT NULL CHECK (amount >= 0),
    currency      CHAR(3) NOT NULL DEFAULT 'BRL' CHECK (currency ~ '^[A-Z]{3}$'),
    external_id   VARCHAR(200) NOT NULL,
    description   VARCHAR(500),
    metadata      JSONB NOT NULL DEFAULT '{}',
    imported_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (post_id, tenant_id)
        REFERENCES posts(id, tenant_id),
    UNIQUE (tenant_id, provider, external_id)
);

CREATE INDEX IF NOT EXISTS idx_financial_entries_period
    ON financial_entries(tenant_id, occurred_on DESC, provider);
CREATE INDEX IF NOT EXISTS idx_financial_entries_post
    ON financial_entries(tenant_id, post_id, occurred_on DESC);

GRANT SELECT, INSERT, UPDATE ON financial_entries TO bloom_app;
GRANT USAGE, SELECT ON SEQUENCE financial_entries_id_seq TO bloom_app;

COMMIT;
