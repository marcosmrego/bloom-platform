"""
BLOOM API — Plataforma Multi-Tenant de Blogs com IA
FastAPI core: tenants, products, posts, categories, users, clicks, campaigns
"""
import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

# ── Config ────────────────────────────────────────
def get_db_password():
    """Lê senha do vault (fallback: fluxo .env)"""
    vault = Path("/opt/data/vault/credentials/postgres_password.txt")
    if vault.exists():
        return vault.read_text().strip()
    env = Path("/opt/data/fluxo-de-investimentos-v2/.env")
    if env.exists():
        for raw_line in env.read_text().split("\n"):
            if "=" in raw_line and raw_line.split("=")[0].strip() == "DB_PASSWORD":
                return raw_line.split("=", 1)[1].strip()
    return os.getenv("DB_PASSWORD", "")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "212.85.22.227"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "bloom"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": get_db_password(),
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bloom")

# ── Database Pool (simple connection per request for now) ──
def get_db():
    """Retorna conexão com autocommit desligado."""
    conn = psycopg2.connect(**DB_CONFIG)
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    return conn

# ── FastAPI App ───────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🌸 Bloom API started")
    yield
    logger.info("Bloom API shutting down")

app = FastAPI(
    title="Bloom API",
    version="1.0.0",
    description="Plataforma multi-tenant de blogs com IA",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Health ─────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "service": "bloom-api"}

# ── Pydantic Models ────────────────────────────────
class TenantResponse(BaseModel):
    id: int
    slug: str
    name: str
    domain: str
    niche: Optional[str] = None
    status: str

class CategoryResponse(BaseModel):
    id: int
    tenant_id: int
    name: str
    slug: str

class ProductResponse(BaseModel):
    id: int
    tenant_id: int
    asin: str
    title: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    price: Optional[float] = None
    category_id: Optional[int] = None
    affiliate_url: Optional[str] = None
    active: bool

class PostResponse(BaseModel):
    id: int
    tenant_id: int
    title: str
    slug: str
    excerpt: Optional[str] = None
    image_url: Optional[str] = None
    category_name: Optional[str] = None
    category_slug: Optional[str] = None
    rating: Optional[float] = None
    pros: Optional[Any] = None
    cons: Optional[Any] = None
    status: str
    tags: Optional[Any] = None
    product_title: Optional[str] = None
    product_price: Optional[float] = None
    product_image: Optional[str] = None
    affiliate_url: Optional[str] = None
    published_at: Optional[str] = None

class PostDetailResponse(PostResponse):
    content: str
    tenant_name: str
    tenant_slug: str
    domain: str

class PostCreate(BaseModel):
    tenant_slug: str
    title: str
    slug: Optional[str] = None
    excerpt: Optional[str] = None
    content: str
    image_url: Optional[str] = None
    category_slug: Optional[str] = None
    product_asin: Optional[str] = None
    rating: Optional[float] = None
    pros: Optional[List[str]] = None
    cons: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    status: str = "draft"
    created_by: str = "hermes"

class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    page_size: int

# ── TENANTS ────────────────────────────────────────
@app.get("/api/v1/tenants")
async def list_tenants():
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM tenants WHERE status = 'active' ORDER BY name")
        tenants = cur.fetchall()
        return {"items": [dict(t) for t in tenants]}
    finally:
        conn.close()

@app.get("/api/v1/tenants/{slug}")
async def get_tenant(slug: str):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM tenants WHERE slug = %s", (slug,))
        t = cur.fetchone()
        if not t:
            return {"error": "Tenant not found"}, 404
        return dict(t)
    finally:
        conn.close()

# ── CATEGORIES ─────────────────────────────────────
@app.get("/api/v1/{tenant_slug}/categories")
async def list_categories(tenant_slug: str):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT c.* FROM categories c
            JOIN tenants t ON c.tenant_id = t.id
            WHERE t.slug = %s
            ORDER BY c.name
        """, (tenant_slug,))
        cats = cur.fetchall()
        return {"items": [dict(c) for c in cats]}
    finally:
        conn.close()

# ── PRODUCTS ───────────────────────────────────────
@app.get("/api/v1/{tenant_slug}/products")
async def list_products(
    tenant_slug: str,
    category: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    conn = get_db()
    try:
        cur = conn.cursor()
        params = [tenant_slug]
        where = "WHERE t.slug = %s AND pr.active = true"

        if category:
            where += " AND c.slug = %s"
            params.append(category)

        # Count
        cur.execute(f"SELECT COUNT(*) as total FROM products pr JOIN tenants t ON pr.tenant_id = t.id LEFT JOIN categories c ON pr.category_id = c.id {where}", params)
        total = cur.fetchone()["total"]

        # Fetch
        offset = (page - 1) * page_size
        cur.execute(f"""
            SELECT pr.*, c.name as category_name, t.name as tenant_name
            FROM products pr
            JOIN tenants t ON pr.tenant_id = t.id
            LEFT JOIN categories c ON pr.category_id = c.id
            {where}
            ORDER BY pr.created_at DESC
            LIMIT %s OFFSET %s
        """, params + [page_size, offset])
        items = [dict(row) for row in cur.fetchall()]

        return {"items": items, "total": total, "page": page, "page_size": page_size}
    finally:
        conn.close()

# ── POSTS ──────────────────────────────────────────
@app.get("/api/v1/{tenant_slug}/posts")
async def list_posts(
    tenant_slug: str,
    category: Optional[str] = None,
    page: int = 1,
    page_size: int = 12,
):
    conn = get_db()
    try:
        cur = conn.cursor()
        params = [tenant_slug]
        where = "WHERE t.slug = %s AND p.status = 'published'"

        if category:
            where += " AND p.category_slug = %s"
            params.append(category)

        cur.execute(f"SELECT COUNT(*) as total FROM vw_posts_enriched p JOIN tenants t ON p.tenant_id = t.id {where}", params)
        total = cur.fetchone()["total"]

        offset = (page - 1) * page_size
        cur.execute(f"""
            SELECT p.* FROM vw_posts_enriched p
            JOIN tenants t ON p.tenant_id = t.id
            {where}
            ORDER BY p.published_at DESC
            LIMIT %s OFFSET %s
        """, params + [page_size, offset])
        items = [dict(row) for row in cur.fetchall()]

        return {"items": items, "total": total, "page": page, "page_size": page_size}
    finally:
        conn.close()

@app.get("/api/v1/{tenant_slug}/posts/{slug}")
async def get_post(tenant_slug: str, slug: str):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT p.*, t.name as tenant_name, t.slug as tenant_slug, t.domain
            FROM vw_posts_enriched p
            JOIN tenants t ON p.tenant_id = t.id
            WHERE t.slug = %s AND p.slug = %s AND p.status = 'published'
        """, (tenant_slug, slug))
        post = cur.fetchone()
        if not post:
            return {"error": "Post not found"}, 404
        return dict(post)
    finally:
        conn.close()

@app.post("/api/v1/{tenant_slug}/posts")
async def create_post(tenant_slug: str, data: PostCreate):
    conn = get_db()
    try:
        cur = conn.cursor()

        # Resolve tenant_id
        cur.execute("SELECT id FROM tenants WHERE slug = %s", (tenant_slug,))
        t = cur.fetchone()
        if not t:
            return {"error": "Tenant not found"}, 404
        tenant_id = t["id"]

        # Resolve category_id (opcional)
        category_id = None
        if data.category_slug:
            cur.execute("SELECT id FROM categories WHERE tenant_id = %s AND slug = %s", (tenant_id, data.category_slug))
            cat = cur.fetchone()
            if cat:
                category_id = cat["id"]

        # Resolve product_id (opcional)
        product_id = None
        if data.product_asin:
            cur.execute("SELECT id FROM products WHERE tenant_id = %s AND asin = %s", (tenant_id, data.product_asin))
            prod = cur.fetchone()
            if prod:
                product_id = prod["id"]

        # Auto-generate slug if not provided
        slug = data.slug or data.title.lower().replace(" ", "-")[:100]

        cur.execute("""
            INSERT INTO posts (tenant_id, title, slug, excerpt, content, image_url,
                category_id, product_id, rating, pros, cons, status, tags, created_by,
                published_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                CASE WHEN %s = 'published' THEN NOW() ELSE NULL END)
            RETURNING id
        """, (
            tenant_id, data.title, slug, data.excerpt, data.content,
            data.image_url, category_id, product_id, data.rating,
            psycopg2.extras.Json(data.pros or []),
            psycopg2.extras.Json(data.cons or []),
            data.status,
            psycopg2.extras.Json(data.tags or []),
            data.created_by, data.status,
        ))
        post_id = cur.fetchone()["id"]
        conn.commit()

        return {"status": "created", "id": post_id, "slug": slug}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}, 500
    finally:
        conn.close()

# ── CLICKS ─────────────────────────────────────────
@app.post("/api/v1/{tenant_slug}/clicks")
async def register_click(
    tenant_slug: str,
    product_id: Optional[int] = None,
    post_id: Optional[int] = None,
    link_type: str = "amazon",
    source_url: Optional[str] = None,
):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM tenants WHERE slug = %s", (tenant_slug,))
        t = cur.fetchone()
        if not t:
            return {"error": "Tenant not found"}, 404

        import ipaddress
        ip = "0.0.0.0"  # seria request.client.host com FastAPI real

        cur.execute("""
            INSERT INTO clicks (tenant_id, product_id, post_id, link_type, source_url, ip_address)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (t["id"], product_id, post_id, link_type, source_url, ip))
        conn.commit()
        return {"status": "registered"}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}, 500
    finally:
        conn.close()

# ── USERS ──────────────────────────────────────────
@app.post("/api/v1/{tenant_slug}/users/subscribe")
async def subscribe_user(
    tenant_slug: str,
    email: str,
    name: Optional[str] = None,
    source: str = "newsletter",
):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM tenants WHERE slug = %s", (tenant_slug,))
        t = cur.fetchone()
        if not t:
            return {"error": "Tenant not found"}, 404

        cur.execute("""
            INSERT INTO users (tenant_id, email, name, source)
            VALUES (%s,%s,%s,%s)
            ON CONFLICT (tenant_id, email) DO UPDATE SET status = 'active', name = COALESCE(EXCLUDED.name, users.name)
            RETURNING id
        """, (t["id"], email, name, source))
        user_id = cur.fetchone()["id"]
        conn.commit()
        return {"status": "subscribed", "user_id": user_id}
    except Exception as e:
        conn.rollback()
        return {"error": str(e)}, 500
    finally:
        conn.close()

# ── STATS ──────────────────────────────────────────
@app.get("/api/v1/{tenant_slug}/stats")
async def tenant_stats(tenant_slug: str):
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM vw_tenant_stats
            WHERE tenant_id = (SELECT id FROM tenants WHERE slug = %s)
        """, (tenant_slug,))
        stats = cur.fetchone()
        if not stats:
            return {"error": "Tenant not found"}, 404
        return dict(stats)
    finally:
        conn.close()

# ── MAIN ───────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
