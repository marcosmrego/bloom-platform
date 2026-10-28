BEGIN;

ALTER TABLE products
    ADD COLUMN IF NOT EXISTS marketplace VARCHAR(20) NOT NULL DEFAULT 'amazon',
    ADD COLUMN IF NOT EXISTS external_id VARCHAR(40),
    ADD COLUMN IF NOT EXISTS affiliate_link VARCHAR(1000);

-- Amazon products keep their ASIN; Mercado Livre items have none.
ALTER TABLE products ALTER COLUMN asin DROP NOT NULL;

-- Legacy writers (seed, scripts) insert Amazon products with an ASIN only.
CREATE OR REPLACE FUNCTION products_fill_external_id() RETURNS trigger AS $$
BEGIN
    IF NEW.marketplace = 'amazon' AND NEW.external_id IS NULL THEN
        NEW.external_id := NEW.asin;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_products_fill_external_id ON products;
CREATE TRIGGER trg_products_fill_external_id
    BEFORE INSERT OR UPDATE ON products
    FOR EACH ROW EXECUTE FUNCTION products_fill_external_id();

UPDATE products SET external_id = asin
 WHERE marketplace = 'amazon' AND external_id IS NULL;

ALTER TABLE products DROP CONSTRAINT IF EXISTS products_marketplace_identity_check;
ALTER TABLE products ADD CONSTRAINT products_marketplace_identity_check CHECK (
    (marketplace = 'amazon'
        AND asin IS NOT NULL AND external_id = asin)
    OR
    (marketplace = 'mercadolivre'
        AND asin IS NULL
        AND external_id ~ '^MLB[0-9]{6,}$'
        AND affiliate_link IS NOT NULL)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_products_marketplace_external
    ON products(tenant_id, marketplace, external_id);

-- products.affiliate_url stays a generated Amazon-only column (NULL without
-- an ASIN). Mercado Livre destinations live in post_commerce.destination_url,
-- which vw_posts_enriched already prefers over products.affiliate_url.

ALTER TABLE financial_entries DROP CONSTRAINT IF EXISTS financial_entries_provider_check;
ALTER TABLE financial_entries ADD CONSTRAINT financial_entries_provider_check
    CHECK (provider IN ('amazon', 'mercadolivre', 'adsense', 'adcash', 'manual'));

CREATE TABLE IF NOT EXISTS marketplace_tokens (
    provider      VARCHAR(30) PRIMARY KEY,
    access_token  TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    expires_at    TIMESTAMPTZ NOT NULL,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMIT;
