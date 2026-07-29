-- Auditoria somente leitura. Todas as consultas devem retornar zero linhas,
-- exceto as seções de imagens e slugs, que servem como relatório editorial.

-- Categorias ligadas a outro tenant.
SELECT p.id, p.tenant_id AS post_tenant, c.tenant_id AS category_tenant
FROM posts p
JOIN categories c ON c.id = p.category_id
WHERE p.tenant_id IS DISTINCT FROM c.tenant_id;

SELECT pr.id, pr.tenant_id AS product_tenant, c.tenant_id AS category_tenant
FROM products pr
JOIN categories c ON c.id = pr.category_id
WHERE pr.tenant_id IS DISTINCT FROM c.tenant_id;

-- Produtos ligados a posts de outro tenant.
SELECT p.id, p.tenant_id AS post_tenant, pr.tenant_id AS product_tenant
FROM posts p
JOIN products pr ON pr.id = p.product_id
WHERE p.tenant_id IS DISTINCT FROM pr.tenant_id;

-- Métricas ligadas a entidades de outro tenant.
SELECT cl.id, cl.tenant_id, pr.tenant_id AS product_tenant,
       p.tenant_id AS post_tenant, u.tenant_id AS user_tenant
FROM clicks cl
LEFT JOIN products pr ON pr.id = cl.product_id
LEFT JOIN posts p ON p.id = cl.post_id
LEFT JOIN users u ON u.id = cl.user_id
WHERE (cl.product_id IS NOT NULL AND cl.tenant_id IS DISTINCT FROM pr.tenant_id)
   OR (cl.post_id IS NOT NULL AND cl.tenant_id IS DISTINCT FROM p.tenant_id)
   OR (cl.user_id IS NOT NULL AND cl.tenant_id IS DISTINCT FROM u.tenant_id);

-- Imagens ausentes.
SELECT t.slug AS tenant, p.id, p.slug, p.title
FROM posts p
JOIN tenants t ON t.id = p.tenant_id
LEFT JOIN products pr ON pr.id = p.product_id AND pr.tenant_id = p.tenant_id
WHERE NULLIF(BTRIM(p.image_url), '') IS NULL
  AND NULLIF(BTRIM(pr.image_url), '') IS NULL
ORDER BY t.slug, p.id;

-- Imagens editoriais repetidas em artigos diferentes.
SELECT t.slug AS tenant, p.image_url, COUNT(*) AS post_count,
       ARRAY_AGG(p.slug ORDER BY p.id) AS post_slugs
FROM posts p
JOIN tenants t ON t.id = p.tenant_id
WHERE NULLIF(BTRIM(p.image_url), '') IS NOT NULL
GROUP BY t.slug, p.image_url
HAVING COUNT(*) > 1
ORDER BY post_count DESC;

-- Slugs que não seguem o formato canônico.
SELECT t.slug AS tenant, p.id, p.slug, p.title
FROM posts p
JOIN tenants t ON t.id = p.tenant_id
WHERE p.slug !~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'
ORDER BY t.slug, p.id;
