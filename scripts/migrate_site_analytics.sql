BEGIN;

ALTER TABLE page_views ALTER COLUMN post_id DROP NOT NULL;

ALTER TABLE page_views
    DROP CONSTRAINT IF EXISTS page_views_tenant_id_post_id_session_hash_view_date_key;

CREATE UNIQUE INDEX IF NOT EXISTS idx_page_views_unique_path_session_day
    ON page_views (tenant_id, COALESCE(post_id, 0), session_hash, view_date, path);

CREATE INDEX IF NOT EXISTS idx_page_views_tenant_path_date
    ON page_views (tenant_id, path, created_at DESC);

COMMIT;
