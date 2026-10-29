BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'products_id_tenant_key') THEN
        RAISE EXCEPTION 'Aplique scripts/migrate_tenant_integrity.sql antes desta migracao';
    END IF;
END $$;

-- Fila de pedidos de draft feitos no painel e consumidos pelo cron do Hermes.
CREATE TABLE IF NOT EXISTS product_draft_requests (
    id           SERIAL PRIMARY KEY,
    tenant_id    INT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    product_id   INT NOT NULL,
    status       VARCHAR(12) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    attempts     INT NOT NULL DEFAULT 0,
    post_id      INT REFERENCES posts(id) ON DELETE SET NULL,
    error        VARCHAR(500),
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    claimed_at   TIMESTAMPTZ,
    finished_at  TIMESTAMPTZ,
    FOREIGN KEY (product_id, tenant_id) REFERENCES products(id, tenant_id) ON DELETE CASCADE
);

-- No máximo um pedido ativo por produto.
CREATE UNIQUE INDEX IF NOT EXISTS uq_product_draft_requests_active
    ON product_draft_requests(product_id)
    WHERE status IN ('pending', 'running');

CREATE INDEX IF NOT EXISTS idx_product_draft_requests_queue
    ON product_draft_requests(tenant_id, status, requested_at);

COMMIT;
