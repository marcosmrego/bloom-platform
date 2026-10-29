"""Queue of draft requests created in the panel and consumed by the Hermes cron."""

from typing import Any, Callable, Dict, List, Optional

TENANT = "viralbarato"
STALE_MINUTES = 30
MAX_ATTEMPTS = 3
ERROR_MAX_LENGTH = 500
CATALOG_URL = "https://www.mercadolivre.com.br/p/{external_id}"


def enqueue(get_db: Callable[[], Any], product_id: int) -> Optional[Dict[str, Any]]:
    """Queue a draft for a Mercado Livre product; reuse the active request if one exists."""
    for _ in range(2):
        result = _enqueue_once(get_db, product_id)
        if result != RETRY:
            return result
    return None


RETRY: Dict[str, Any] = {"retry": True}


def _enqueue_once(get_db: Callable[[], Any], product_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT pr.id, pr.tenant_id
            FROM products pr JOIN tenants t ON t.id = pr.tenant_id
            WHERE pr.id = %s AND pr.marketplace = 'mercadolivre' AND t.slug = %s
            """,
            (product_id, TENANT),
        )
        product = cur.fetchone()
        if not product:
            return None
        cur.execute(
            """
            INSERT INTO product_draft_requests (tenant_id, product_id)
            VALUES (%s, %s)
            ON CONFLICT (product_id) WHERE status IN ('pending', 'running') DO NOTHING
            RETURNING id, status
            """,
            (product["tenant_id"], product_id),
        )
        created = cur.fetchone()
        if created:
            conn.commit()
            return {**dict(created), "created": True}
        cur.execute(
            """
            SELECT id, status FROM product_draft_requests
            WHERE product_id = %s AND status IN ('pending', 'running')
            """,
            (product_id,),
        )
        active = cur.fetchone()
        if not active:
            return RETRY
        return {**dict(active), "created": False}
    finally:
        conn.close()


def claim(get_db: Callable[[], Any], tenant_slug: str) -> Optional[Dict[str, Any]]:
    """Hand the oldest pending request to a worker, reclaiming abandoned ones."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE product_draft_requests r
            SET status = 'failed', finished_at = NOW(),
                error = 'Tempo esgotado após várias tentativas'
            FROM tenants t
            WHERE t.id = r.tenant_id AND t.slug = %s AND r.status = 'running'
              AND r.attempts >= %s
              AND r.claimed_at < NOW() - make_interval(mins => %s)
            """,
            (tenant_slug, MAX_ATTEMPTS, STALE_MINUTES),
        )
        cur.execute(
            """
            UPDATE product_draft_requests
            SET status = 'running', claimed_at = NOW(), attempts = attempts + 1
            WHERE id = (
                SELECT r.id
                FROM product_draft_requests r JOIN tenants t ON t.id = r.tenant_id
                WHERE t.slug = %s
                  AND (r.status = 'pending'
                       OR (r.status = 'running'
                           AND r.claimed_at < NOW() - make_interval(mins => %s)))
                ORDER BY r.requested_at
                LIMIT 1
                FOR UPDATE OF r SKIP LOCKED
            )
            RETURNING id, product_id
            """,
            (tenant_slug, STALE_MINUTES),
        )
        claimed = cur.fetchone()
        if not claimed:
            conn.commit()
            return None
        cur.execute(
            "SELECT external_id, title, price, image_url FROM products WHERE id = %s",
            (claimed["product_id"],),
        )
        product = cur.fetchone()
        conn.commit()
        return {
            "request_id": claimed["id"],
            "product_id": claimed["product_id"],
            "external_id": product["external_id"],
            "title": product["title"],
            "price": str(product["price"]) if product["price"] is not None else None,
            "image_url": product["image_url"],
            "permalink": CATALOG_URL.format(external_id=product["external_id"]),
        }
    finally:
        conn.close()


def finish(
    get_db: Callable[[], Any],
    tenant_slug: str,
    request_id: int,
    status: str,
    post_id: Optional[int],
    error: Optional[str],
) -> str:
    """Record the outcome of a running request.

    Returns "ok", "not_running" (unknown or not running for the tenant) or
    "invalid_post" (completed without a post of the tenant).
    """
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT r.id, r.tenant_id
            FROM product_draft_requests r JOIN tenants t ON t.id = r.tenant_id
            WHERE r.id = %s AND t.slug = %s AND r.status = 'running'
            FOR UPDATE OF r
            """,
            (request_id, tenant_slug),
        )
        request = cur.fetchone()
        if not request:
            return "not_running"
        if status == "completed":
            cur.execute(
                "SELECT id FROM posts WHERE id = %s AND tenant_id = %s",
                (post_id, request["tenant_id"]),
            )
            if not cur.fetchone():
                return "invalid_post"
        cur.execute(
            """
            UPDATE product_draft_requests
            SET status = %s, post_id = %s, error = %s, finished_at = NOW()
            WHERE id = %s
            """,
            (
                status,
                post_id if status == "completed" else None,
                (error or "")[:ERROR_MAX_LENGTH] or None,
                request_id,
            ),
        )
        conn.commit()
        return "ok"
    finally:
        conn.close()


def list_recent(get_db: Callable[[], Any], limit: int = 15) -> List[Dict[str, Any]]:
    """Latest requests with product and draft info for the panel."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT r.id, r.product_id, r.status, r.error, r.post_id,
                   r.requested_at, r.finished_at,
                   pr.title AS product_title, pr.external_id,
                   p.slug AS post_slug, p.status AS post_status
            FROM product_draft_requests r
            JOIN tenants t ON t.id = r.tenant_id
            JOIN products pr ON pr.id = r.product_id AND pr.tenant_id = r.tenant_id
            LEFT JOIN posts p ON p.id = r.post_id
            WHERE t.slug = %s
            ORDER BY r.requested_at DESC
            LIMIT %s
            """,
            (TENANT, limit),
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()
