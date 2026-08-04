BEGIN;

CREATE TABLE IF NOT EXISTS post_commerce (
    id                BIGSERIAL PRIMARY KEY,
    tenant_id         INT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    post_id           INT NOT NULL,
    link_type         VARCHAR(20) NOT NULL
                      CHECK (link_type IN ('product', 'search', 'offer')),
    product_id        INT,
    destination_url   VARCHAR(2000) NOT NULL,
    coupon_code       VARCHAR(100),
    offer_text        VARCHAR(500),
    valid_from        TIMESTAMPTZ,
    valid_until       TIMESTAMPTZ,
    verified_at       TIMESTAMPTZ NOT NULL,
    status            VARCHAR(20) NOT NULL DEFAULT 'active'
                      CHECK (status IN ('active', 'expired', 'unverified')),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (post_id),
    FOREIGN KEY (post_id, tenant_id)
        REFERENCES posts(id, tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (product_id, tenant_id)
        REFERENCES products(id, tenant_id) ON DELETE RESTRICT,
    CHECK (valid_until IS NULL OR valid_from IS NULL OR valid_until > valid_from),
    CHECK (link_type <> 'product' OR product_id IS NOT NULL),
    CHECK (link_type <> 'offer' OR offer_text IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_post_commerce_status
    ON post_commerce(tenant_id, status, valid_until);

CREATE TABLE IF NOT EXISTS seasonal_events (
    id                  SERIAL PRIMARY KEY,
    slug                VARCHAR(100) NOT NULL,
    name                VARCHAR(200) NOT NULL,
    event_date          DATE NOT NULL,
    planning_start_date DATE NOT NULL,
    publishing_end_date DATE NOT NULL,
    priority            SMALLINT NOT NULL DEFAULT 50 CHECK (priority BETWEEN 1 AND 100),
    audience_intent     VARCHAR(500),
    active              BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (slug, event_date),
    CHECK (planning_start_date <= publishing_end_date),
    CHECK (publishing_end_date <= event_date)
);

CREATE INDEX IF NOT EXISTS idx_seasonal_events_window
    ON seasonal_events(active, planning_start_date, publishing_end_date, event_date);

CREATE TABLE IF NOT EXISTS seasonal_product_targets (
    id             BIGSERIAL PRIMARY KEY,
    event_id       INT NOT NULL REFERENCES seasonal_events(id) ON DELETE CASCADE,
    tenant_id      INT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    product_id     INT,
    search_query   VARCHAR(300),
    rationale      VARCHAR(1000) NOT NULL,
    priority       SMALLINT NOT NULL DEFAULT 50 CHECK (priority BETWEEN 1 AND 100),
    status         VARCHAR(20) NOT NULL DEFAULT 'candidate'
                   CHECK (status IN ('candidate', 'approved', 'rejected')),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (product_id, tenant_id)
        REFERENCES products(id, tenant_id) ON DELETE RESTRICT,
    CHECK (product_id IS NOT NULL OR search_query IS NOT NULL)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_seasonal_target_query
    ON seasonal_product_targets(event_id, tenant_id, search_query)
    WHERE search_query IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_seasonal_targets_event
    ON seasonal_product_targets(event_id, tenant_id, status, priority DESC);

INSERT INTO seasonal_events
    (slug, name, event_date, planning_start_date, publishing_end_date, priority, audience_intent)
VALUES
    ('dia-das-maes', 'Dia das Mães', DATE '2026-05-10', DATE '2026-04-12', DATE '2026-05-07', 95, 'Presentes e experiências para mães'),
    ('dia-dos-pais', 'Dia dos Pais', DATE '2026-08-09', DATE '2026-07-12', DATE '2026-08-06', 95, 'Presentes úteis e escolhas por perfil de pai'),
    ('dia-das-criancas', 'Dia das Crianças', DATE '2026-10-12', DATE '2026-09-14', DATE '2026-10-08', 90, 'Presentes adequados por idade e interesse'),
    ('black-friday', 'Black Friday', DATE '2026-11-27', DATE '2026-10-16', DATE '2026-11-27', 100, 'Comparação de preço, histórico e ofertas verificadas'),
    ('natal', 'Natal', DATE '2026-12-25', DATE '2026-11-01', DATE '2026-12-20', 100, 'Guias de presentes por perfil e orçamento')
ON CONFLICT (slug, event_date) DO UPDATE SET
    name = EXCLUDED.name,
    planning_start_date = EXCLUDED.planning_start_date,
    publishing_end_date = EXCLUDED.publishing_end_date,
    priority = EXCLUDED.priority,
    audience_intent = EXCLUDED.audience_intent,
    updated_at = NOW();

INSERT INTO seasonal_product_targets
    (event_id, tenant_id, search_query, rationale, priority, status)
SELECT e.id, t.id, seed.search_query, seed.rationale, seed.priority, 'candidate'
FROM seasonal_events e
JOIN tenants t ON t.slug = 'viralbarato'
JOIN (VALUES
    ('power bank 20000mah', 'Presente útil para pais que viajam ou usam muito o celular; exige validação de capacidade, potência e segurança.', 85),
    ('fone bluetooth', 'Categoria ampla com intenção de presente; selecionar modelo exato somente após validar especificações e ASIN.', 80),
    ('kit ferramentas', 'Boa aderência à data, mas precisa de recorte por perfil e comparação de composição e garantia.', 75),
    ('aparador de barba', 'Produto presenteável com potencial de comparação; evitar alegações de desempenho sem evidência.', 70)
) AS seed(search_query, rationale, priority) ON TRUE
WHERE e.slug = 'dia-dos-pais' AND e.event_date = DATE '2026-08-09'
ON CONFLICT DO NOTHING;

DROP VIEW IF EXISTS vw_posts_enriched;

CREATE VIEW vw_posts_enriched AS
SELECT
    p.id, p.tenant_id, p.title, p.slug, p.excerpt, p.content, p.image_url,
    p.rating, p.pros, p.cons, p.status, p.tags, p.published_at,
    c.name AS category_name, c.slug AS category_slug,
    pr.asin, pr.title AS product_title, pr.price, pr.image_url AS product_image,
    COALESCE(
        CASE
            WHEN pc.status = 'active'
             AND (pc.valid_from IS NULL OR pc.valid_from <= NOW())
             AND (pc.valid_until IS NULL OR pc.valid_until > NOW())
            THEN pc.destination_url
        END,
        pr.affiliate_url
    ) AS affiliate_url,
    pc.link_type AS commerce_link_type,
    CASE WHEN pc.status = 'active' AND (pc.valid_until IS NULL OR pc.valid_until > NOW()) THEN pc.coupon_code END AS coupon_code,
    CASE WHEN pc.status = 'active' AND (pc.valid_until IS NULL OR pc.valid_until > NOW()) THEN pc.offer_text END AS offer_text,
    pc.valid_until AS offer_valid_until,
    pc.verified_at AS offer_verified_at,
    t.name AS tenant_name, t.slug AS tenant_slug, t.domain,
    p.seo_title, p.seo_description, p.created_at, p.updated_at
FROM posts p
LEFT JOIN categories c ON p.category_id = c.id AND p.tenant_id = c.tenant_id
LEFT JOIN products pr ON p.product_id = pr.id AND p.tenant_id = pr.tenant_id
LEFT JOIN post_commerce pc ON pc.post_id = p.id AND pc.tenant_id = p.tenant_id
JOIN tenants t ON p.tenant_id = t.id;

COMMIT;
