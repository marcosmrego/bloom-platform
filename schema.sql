-- ==============================================================
-- BLOOM — Plataforma Multi-Tenant de Blogs com IA
-- Schema PostgreSQL — Fase 1: Core (tenants, categories, products, posts)
-- ==============================================================

-- ═══════════════════════════════════════════════════
-- TENANTS (cada blog é um tenant)
-- ═══════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS tenants (
    id          SERIAL PRIMARY KEY,
    slug        VARCHAR(50) UNIQUE NOT NULL,       -- viralbarato, mundonoprato, tenisbarato...
    name        VARCHAR(100) NOT NULL,             -- "ViralBarato"
    domain      VARCHAR(255) NOT NULL,              -- viralbarato.com.br
    niche       VARCHAR(100),                      -- "reviews de produtos", "gastronomia"
    status      VARCHAR(20) DEFAULT 'active',       -- active, paused, archived
    theme       JSONB DEFAULT '{}',                 -- cores, logo, fonte
    monetization JSONB DEFAULT '{}',                -- {adsense: "pub-xxx", amazon_tag: "xxx-20", adcash_zone: "xxx"}
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Seeds iniciais
INSERT INTO tenants (slug, name, domain, niche, monetization) VALUES
    ('viralbarato', 'ViralBarato', 'viralbarato.com.br', 'reviews de produtos',
     '{"amazon_tag": "marcosmrego-20", "adcash_zone": "mdsdzatm7q"}'),
    ('mundonoprato', 'Mundo no Prato', 'mundonoprato.com.br', 'gastronomia',
     '{"amazon_tag": "marcosmrego-20", "adcash_zone": "11800602"}')
ON CONFLICT (slug) DO NOTHING;

-- ═══════════════════════════════════════════════════
-- CATEGORIES
-- ═══════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS categories (
    id          SERIAL PRIMARY KEY,
    tenant_id   INT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name        VARCHAR(100) NOT NULL,
    slug        VARCHAR(100) NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, slug),
    UNIQUE(id, tenant_id)
);

-- ═══════════════════════════════════════════════════
-- PRODUCTS (base de ASINs reais para afiliados)
-- ═══════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS products (
    id           SERIAL PRIMARY KEY,
    tenant_id    INT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    asin         VARCHAR(10) NOT NULL,             -- B09B8VGCR8
    title        VARCHAR(500) NOT NULL,
    description  TEXT,
    image_url    VARCHAR(1000),
    price        DECIMAL(10,2),
    price_updated_at TIMESTAMPTZ,
    category_id  INT,
    affiliate_url VARCHAR(1000) GENERATED ALWAYS AS (
        'https://www.amazon.com.br/dp/' || asin || '?tag=marcosmrego-20'
    ) STORED,
    active       BOOLEAN DEFAULT TRUE,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, asin),
    UNIQUE(id, tenant_id),
    FOREIGN KEY (category_id, tenant_id)
        REFERENCES categories(id, tenant_id)
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_products_tenant ON products(tenant_id);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category_id);
CREATE INDEX IF NOT EXISTS idx_products_active ON products(active) WHERE active = TRUE;

-- ═══════════════════════════════════════════════════
-- POSTS (review, artigo, receita)
-- ═══════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS posts (
    id              SERIAL PRIMARY KEY,
    tenant_id       INT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    title           VARCHAR(500) NOT NULL,
    slug            VARCHAR(500) NOT NULL,
    excerpt         TEXT,
    content         TEXT NOT NULL,                  -- markdown
    image_url       VARCHAR(1000),
    category_id     INT,
    product_id      INT,
    rating          DECIMAL(2,1) CHECK (rating >= 0 AND rating <= 5),
    pros            JSONB DEFAULT '[]',
    cons            JSONB DEFAULT '[]',
    status          VARCHAR(20) DEFAULT 'draft',    -- draft, published, archived
    seo_title       VARCHAR(500),
    seo_description TEXT,
    tags            JSONB DEFAULT '[]',
    published_at    TIMESTAMPTZ,
    created_by      VARCHAR(50),                   -- 'hermes', 'editor-viralbarato', etc
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, slug),
    UNIQUE(id, tenant_id),
    FOREIGN KEY (category_id, tenant_id)
        REFERENCES categories(id, tenant_id),
    FOREIGN KEY (product_id, tenant_id)
        REFERENCES products(id, tenant_id)
);

CREATE TABLE IF NOT EXISTS post_slug_redirects (
    tenant_id   INT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    old_slug    VARCHAR(500) NOT NULL,
    post_id     INT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (tenant_id, old_slug),
    FOREIGN KEY (post_id, tenant_id)
        REFERENCES posts(id, tenant_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_posts_tenant ON posts(tenant_id);
CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status);
CREATE INDEX IF NOT EXISTS idx_posts_published ON posts(tenant_id, published_at DESC) WHERE status = 'published';
CREATE INDEX IF NOT EXISTS idx_posts_category ON posts(category_id);
CREATE INDEX IF NOT EXISTS idx_posts_product ON posts(product_id);

-- ═══════════════════════════════════════════════════
-- USERS (newsletter + membros)
-- ═══════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    tenant_id       INT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email           VARCHAR(255) NOT NULL,
    name            VARCHAR(200),
    phone           VARCHAR(30),
    preferences     JSONB DEFAULT '{}',             -- {interests: ["eletronicos"], channels: ["telegram", "email"]}
    source          VARCHAR(100),                   -- 'newsletter', 'landing_page'
    status          VARCHAR(20) DEFAULT 'active',
    subscribed_at   TIMESTAMPTZ DEFAULT NOW(),
    unsubscribed_at TIMESTAMPTZ,
    UNIQUE(tenant_id, email),
    UNIQUE(id, tenant_id)
);

-- ═══════════════════════════════════════════════════
-- CLICKS (rastreamento de afiliados e anúncios)
-- ═══════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS clicks (
    id          BIGSERIAL PRIMARY KEY,
    tenant_id   INT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    product_id  INT,
    post_id     INT,
    user_id     INT,
    link_type   VARCHAR(20) NOT NULL,               -- 'amazon', 'adsense', 'adcash'
    source_url  VARCHAR(1000),
    ip_address  VARCHAR(50),
    user_agent  TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (product_id, tenant_id)
        REFERENCES products(id, tenant_id),
    FOREIGN KEY (post_id, tenant_id)
        REFERENCES posts(id, tenant_id),
    FOREIGN KEY (user_id, tenant_id)
        REFERENCES users(id, tenant_id)
);

CREATE INDEX IF NOT EXISTS idx_clicks_tenant ON clicks(tenant_id);
CREATE INDEX IF NOT EXISTS idx_clicks_product ON clicks(product_id);
CREATE INDEX IF NOT EXISTS idx_clicks_date ON clicks(created_at);

-- ═══════════════════════════════════════════════════
-- CAMPAIGNS (marketing)
-- ═══════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS campaigns (
    id              SERIAL PRIMARY KEY,
    tenant_id       INT REFERENCES tenants(id) ON DELETE CASCADE,
    name            VARCHAR(200) NOT NULL,
    type            VARCHAR(20) NOT NULL,           -- 'telegram', 'email', 'both'
    product_ids     JSONB DEFAULT '[]',
    subject         VARCHAR(500),
    message_template TEXT,
    discount_code   VARCHAR(100),
    status          VARCHAR(20) DEFAULT 'draft',    -- draft, scheduled, sending, sent
    scheduled_at    TIMESTAMPTZ,
    sent_at         TIMESTAMPTZ,
    created_by      VARCHAR(50),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS campaign_sends (
    id           BIGSERIAL PRIMARY KEY,
    campaign_id  INT REFERENCES campaigns(id) ON DELETE CASCADE,
    user_id      INT REFERENCES users(id),
    channel      VARCHAR(20) NOT NULL,              -- 'telegram', 'email'
    status       VARCHAR(20) DEFAULT 'pending',     -- pending, sent, failed, opened, clicked
    sent_at      TIMESTAMPTZ,
    opened_at    TIMESTAMPTZ,
    clicked_at   TIMESTAMPTZ
);

-- ═══════════════════════════════════════════════════
-- TICKETS (comunicação entre agentes)
-- ═══════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS tickets (
    id          SERIAL PRIMARY KEY,
    tenant_id   INT REFERENCES tenants(id) ON DELETE CASCADE,
    title       VARCHAR(300) NOT NULL,
    description TEXT,
    from_agent  VARCHAR(100),                       -- 'analytics-viralbarato'
    to_agent    VARCHAR(100),                       -- 'editorial-viralbarato'
    priority    VARCHAR(10) DEFAULT 'normal',       -- low, normal, high, urgent
    status      VARCHAR(20) DEFAULT 'open',         -- open, in_progress, resolved, closed
    resolved_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════
-- AGENT LOGS (rastreio de custos de tokens)
-- ═══════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS agent_logs (
    id          BIGSERIAL PRIMARY KEY,
    agent_name  VARCHAR(100) NOT NULL,
    tenant_id   INT REFERENCES tenants(id),
    task        VARCHAR(100) NOT NULL,              -- 'generate_post', 'send_campaign'
    model       VARCHAR(100),
    tokens_in   INT DEFAULT 0,
    tokens_out  INT DEFAULT 0,
    cost_est    DECIMAL(10,6) DEFAULT 0,           -- custo estimado em USD
    status      VARCHAR(20) DEFAULT 'success',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_logs_agent ON agent_logs(agent_name);
CREATE INDEX IF NOT EXISTS idx_agent_logs_date ON agent_logs(created_at);

-- ═══════════════════════════════════════════════════
-- VIEW: Posts com dados de produto
-- ═══════════════════════════════════════════════════
CREATE OR REPLACE VIEW vw_posts_enriched AS
SELECT
    p.id, p.tenant_id, p.title, p.slug, p.excerpt, p.content, p.image_url,
    p.rating, p.pros, p.cons, p.status, p.tags, p.published_at,
    c.name AS category_name, c.slug AS category_slug,
    pr.asin, pr.title AS product_title, pr.price, pr.image_url AS product_image,
    pr.affiliate_url,
    t.name AS tenant_name, t.slug AS tenant_slug, t.domain
FROM posts p
LEFT JOIN categories c ON p.category_id = c.id AND p.tenant_id = c.tenant_id
LEFT JOIN products pr ON p.product_id = pr.id AND p.tenant_id = pr.tenant_id
JOIN tenants t ON p.tenant_id = t.id;

-- ═══════════════════════════════════════════════════
-- VIEW: Métricas consolidadas por tenant
-- ═══════════════════════════════════════════════════
CREATE OR REPLACE VIEW vw_tenant_stats AS
SELECT
    t.id AS tenant_id,
    t.name,
    COUNT(DISTINCT po.id) FILTER (WHERE po.status = 'published') AS total_posts,
    COUNT(DISTINCT u.id) AS total_users,
    COUNT(DISTINCT cl.id) AS total_clicks,
    COUNT(DISTINCT ca.id) AS total_campaigns
FROM tenants t
LEFT JOIN posts po ON po.tenant_id = t.id
LEFT JOIN users u ON u.tenant_id = t.id
LEFT JOIN clicks cl ON cl.tenant_id = t.id
LEFT JOIN campaigns ca ON ca.tenant_id = t.id
GROUP BY t.id, t.name;
