BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM products pr
        JOIN categories c ON c.id = pr.category_id
        WHERE pr.tenant_id IS DISTINCT FROM c.tenant_id
    ) OR EXISTS (
        SELECT 1
        FROM posts p
        JOIN categories c ON c.id = p.category_id
        WHERE p.tenant_id IS DISTINCT FROM c.tenant_id
    ) OR EXISTS (
        SELECT 1
        FROM posts p
        JOIN products pr ON pr.id = p.product_id
        WHERE p.tenant_id IS DISTINCT FROM pr.tenant_id
    ) OR EXISTS (
        SELECT 1
        FROM clicks cl
        LEFT JOIN products pr ON pr.id = cl.product_id
        LEFT JOIN posts p ON p.id = cl.post_id
        LEFT JOIN users u ON u.id = cl.user_id
        WHERE (cl.product_id IS NOT NULL AND cl.tenant_id IS DISTINCT FROM pr.tenant_id)
           OR (cl.post_id IS NOT NULL AND cl.tenant_id IS DISTINCT FROM p.tenant_id)
           OR (cl.user_id IS NOT NULL AND cl.tenant_id IS DISTINCT FROM u.tenant_id)
    ) THEN
        RAISE EXCEPTION 'Cross-tenant references found. Run the audit queries and repair data before applying constraints.';
    END IF;

    IF EXISTS (SELECT 1 FROM categories WHERE tenant_id IS NULL)
       OR EXISTS (SELECT 1 FROM products WHERE tenant_id IS NULL)
       OR EXISTS (SELECT 1 FROM posts WHERE tenant_id IS NULL)
       OR EXISTS (SELECT 1 FROM users WHERE tenant_id IS NULL)
       OR EXISTS (SELECT 1 FROM clicks WHERE tenant_id IS NULL) THEN
        RAISE EXCEPTION 'Rows with null tenant_id found. Repair data before applying constraints.';
    END IF;
END $$;

ALTER TABLE categories ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE products ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE posts ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE users ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE clicks ALTER COLUMN tenant_id SET NOT NULL;

ALTER TABLE categories ADD CONSTRAINT categories_id_tenant_key UNIQUE (id, tenant_id);
ALTER TABLE products ADD CONSTRAINT products_id_tenant_key UNIQUE (id, tenant_id);
ALTER TABLE posts ADD CONSTRAINT posts_id_tenant_key UNIQUE (id, tenant_id);
ALTER TABLE users ADD CONSTRAINT users_id_tenant_key UNIQUE (id, tenant_id);

ALTER TABLE products DROP CONSTRAINT IF EXISTS products_category_id_fkey;
ALTER TABLE posts DROP CONSTRAINT IF EXISTS posts_category_id_fkey;
ALTER TABLE posts DROP CONSTRAINT IF EXISTS posts_product_id_fkey;
ALTER TABLE clicks DROP CONSTRAINT IF EXISTS clicks_product_id_fkey;
ALTER TABLE clicks DROP CONSTRAINT IF EXISTS clicks_post_id_fkey;
ALTER TABLE clicks DROP CONSTRAINT IF EXISTS clicks_user_id_fkey;

ALTER TABLE products
    ADD CONSTRAINT products_category_tenant_fkey
    FOREIGN KEY (category_id, tenant_id) REFERENCES categories(id, tenant_id);
ALTER TABLE posts
    ADD CONSTRAINT posts_category_tenant_fkey
    FOREIGN KEY (category_id, tenant_id) REFERENCES categories(id, tenant_id);
ALTER TABLE posts
    ADD CONSTRAINT posts_product_tenant_fkey
    FOREIGN KEY (product_id, tenant_id) REFERENCES products(id, tenant_id);
ALTER TABLE clicks
    ADD CONSTRAINT clicks_product_tenant_fkey
    FOREIGN KEY (product_id, tenant_id) REFERENCES products(id, tenant_id);
ALTER TABLE clicks
    ADD CONSTRAINT clicks_post_tenant_fkey
    FOREIGN KEY (post_id, tenant_id) REFERENCES posts(id, tenant_id);
ALTER TABLE clicks
    ADD CONSTRAINT clicks_user_tenant_fkey
    FOREIGN KEY (user_id, tenant_id) REFERENCES users(id, tenant_id);

CREATE TABLE IF NOT EXISTS post_slug_redirects (
    tenant_id   INT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    old_slug    VARCHAR(500) NOT NULL,
    post_id     INT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (tenant_id, old_slug),
    FOREIGN KEY (post_id, tenant_id)
        REFERENCES posts(id, tenant_id) ON DELETE CASCADE
);

CREATE OR REPLACE VIEW vw_posts_enriched AS
SELECT
    p.id, p.tenant_id, p.title, p.slug, p.excerpt, p.content, p.image_url,
    p.rating, p.pros, p.cons, p.status, p.tags, p.published_at,
    c.name AS category_name, c.slug AS category_slug,
    pr.asin, pr.title AS product_title, pr.price, pr.image_url AS product_image,
    pr.affiliate_url,
    t.name AS tenant_name, t.slug AS tenant_slug, t.domain,
    p.seo_title, p.seo_description, p.created_at, p.updated_at
FROM posts p
LEFT JOIN categories c ON p.category_id = c.id AND p.tenant_id = c.tenant_id
LEFT JOIN products pr ON p.product_id = pr.id AND p.tenant_id = pr.tenant_id
JOIN tenants t ON p.tenant_id = t.id;

COMMIT;
