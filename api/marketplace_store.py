"""Postgres persistence for marketplace tokens and Mercado Livre products."""

from typing import Any, Awaitable, Callable, Dict, Optional

from mercadolivre_client import StoredTokens
from product_registration import MercadoLivreProduct

PROVIDER = "mercadolivre"


class PostgresTokenStore:
    """Persists OAuth tokens so a rotated refresh token survives restarts."""

    def __init__(self, get_db: Callable[[], Any], run_db: Callable[..., Awaitable[Any]]) -> None:
        self._get_db = get_db
        self._run_db = run_db

    async def load(self) -> Optional[StoredTokens]:
        return await self._run_db(self._load)

    async def save(self, tokens: StoredTokens) -> None:
        await self._run_db(self._save, tokens)

    def _load(self) -> Optional[StoredTokens]:
        conn = self._get_db()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT access_token, refresh_token, expires_at FROM marketplace_tokens WHERE provider = %s",
                (PROVIDER,),
            )
            row = cur.fetchone()
            return StoredTokens(row["access_token"], row["refresh_token"], row["expires_at"]) if row else None
        finally:
            conn.close()

    def _save(self, tokens: StoredTokens) -> None:
        conn = self._get_db()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO marketplace_tokens (provider, access_token, refresh_token, expires_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (provider) DO UPDATE SET
                    access_token = EXCLUDED.access_token,
                    refresh_token = EXCLUDED.refresh_token,
                    expires_at = EXCLUDED.expires_at,
                    updated_at = NOW()
                """,
                (PROVIDER, tokens.access_token, tokens.refresh_token, tokens.expires_at),
            )
            conn.commit()
        finally:
            conn.close()


def upsert_mercadolivre_product(
    get_db: Callable[[], Any], tenant_slug: str, product: MercadoLivreProduct
) -> Optional[Dict[str, Any]]:
    """Insert or refresh a Mercado Livre product; None when the tenant is unknown."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM tenants WHERE slug = %s", (tenant_slug,))
        tenant = cur.fetchone()
        if not tenant:
            return None
        cur.execute(
            """
            INSERT INTO products (
                tenant_id, marketplace, external_id, title, image_url,
                price, price_updated_at, affiliate_link, active
            ) VALUES (%s, 'mercadolivre', %s, %s, %s, %s, NOW(), %s, TRUE)
            ON CONFLICT (tenant_id, marketplace, external_id) DO UPDATE SET
                title = EXCLUDED.title,
                image_url = EXCLUDED.image_url,
                price = EXCLUDED.price,
                price_updated_at = NOW(),
                affiliate_link = EXCLUDED.affiliate_link,
                active = TRUE,
                updated_at = NOW()
            RETURNING id, external_id
            """,
            (
                tenant["id"],
                product.external_id,
                product.title[:500],
                product.image_url,
                product.price,
                product.affiliate_link,
            ),
        )
        saved = cur.fetchone()
        conn.commit()
        return dict(saved)
    finally:
        conn.close()
