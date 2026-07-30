"""
BLOOM API — Plataforma Multi-Tenant de Blogs com IA
FastAPI core: tenants, products, posts, categories, users, clicks, campaigns
"""
import os
import logging
import re
import secrets
import hashlib
import json
import tempfile
from io import BytesIO
import unicodedata
from pathlib import Path
from contextlib import asynccontextmanager
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, Request, HTTPException, Header, UploadFile, File
from fastapi.staticfiles import StaticFiles
import asyncio
from functools import partial
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from PIL import Image, UnidentifiedImageError
from typing import Optional, List, Dict, Any, Literal

# ── Config ────────────────────────────────────────
def get_db_password():
    """Lê senha de variável ou arquivo explicitamente configurado."""
    password_file = os.getenv("DB_PASSWORD_FILE")
    if password_file:
        return Path(password_file).read_text(encoding="utf-8").strip()
    return os.getenv("DB_PASSWORD", "")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "bloom"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": get_db_password(),
}

SLUG_MAX_LENGTH = 100
CONTENT_API_TOKEN = os.getenv("CONTENT_API_TOKEN", "").strip()
REVIEW_API_TOKEN = os.getenv("REVIEW_API_TOKEN", "").strip()
CONTENT_AUTOPUBLISH_ENABLED = os.getenv(
    "CONTENT_AUTOPUBLISH_ENABLED", "false"
).strip().lower() in {"1", "true", "yes", "on"}
MEDIA_ROOT = Path(
    os.getenv("MEDIA_ROOT", str(Path(tempfile.gettempdir()) / "bloom-media"))
).resolve()
MAX_IMAGE_BYTES = int(os.getenv("MAX_IMAGE_BYTES", str(10 * 1024 * 1024)))
MAX_IMAGE_PIXELS = int(os.getenv("MAX_IMAGE_PIXELS", "12000000"))


def slugify(value: str, max_length: int = SLUG_MAX_LENGTH) -> str:
    """Cria um segmento de URL ASCII, estável e sem pontuação reservada."""
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    slug = slug[:max_length].rstrip("-")
    if not slug:
        raise ValueError("Title or slug must contain at least one letter or number")
    return slug


def unique_post_slug(cur, tenant_id: int, value: str) -> str:
    """Garante unicidade do slug dentro do tenant."""
    base = slugify(value)
    candidate = base
    suffix = 2
    while True:
        cur.execute(
            "SELECT 1 FROM posts WHERE tenant_id = %s AND slug = %s",
            (tenant_id, candidate),
        )
        if not cur.fetchone():
            return candidate
        suffix_text = f"-{suffix}"
        candidate = f"{base[:SLUG_MAX_LENGTH - len(suffix_text)].rstrip('-')}{suffix_text}"
        suffix += 1


def require_content_token(authorization: Optional[str]) -> None:
    """Valida o token interno sem revelar se houve correspondência parcial."""
    if not CONTENT_API_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="Content automation API is not configured",
        )
    scheme, separator, supplied = (authorization or "").partition(" ")
    valid = (
        separator == " "
        and scheme.lower() == "bearer"
        and bool(supplied)
        and secrets.compare_digest(supplied, CONTENT_API_TOKEN)
    )
    if not valid:
        raise HTTPException(status_code=401, detail="Invalid automation token")


def require_review_token(authorization: Optional[str]) -> None:
    """Authenticate human editorial review with a separate credential."""
    if not REVIEW_API_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="Editorial review API is not configured",
        )
    scheme, separator, supplied = (authorization or "").partition(" ")
    valid = (
        separator == " "
        and scheme.lower() == "bearer"
        and bool(supplied)
        and secrets.compare_digest(supplied, REVIEW_API_TOKEN)
    )
    if not valid:
        raise HTTPException(status_code=401, detail="Invalid review token")


def validate_idempotency_key(value: Optional[str]) -> str:
    key = (value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}", key):
        raise HTTPException(
            status_code=422,
            detail="Idempotency-Key must contain 8-128 safe characters",
        )
    return key


def post_request_hash(data: "PostCreate") -> str:
    payload = json.dumps(
        data.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


SENSITIVE_EDITORIAL_TERMS = {
    "alergia",
    "caloria",
    "calorias",
    "colesterol",
    "diabetes",
    "dieta",
    "doença",
    "glicemia",
    "hipertensão",
    "minerais",
    "nutrição",
    "nutricional",
    "proteína",
    "saúde",
    "sódio",
    "vitamina",
}


def validate_editorial_sources(data: "PostCreate") -> Dict[str, Any]:
    """Bloqueia drafts sem evidência extraída suficiente ou fonte primária."""
    if len(data.sources) < 2:
        raise HTTPException(
            status_code=422,
            detail="At least two extracted sources are required",
        )

    normalized_urls = set()
    for source in data.sources:
        parsed = urlparse(source.url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise HTTPException(status_code=422, detail="Source URL must be HTTP(S)")
        normalized_url = parsed._replace(fragment="").geturl().rstrip("/")
        if normalized_url in normalized_urls:
            raise HTTPException(
                status_code=422,
                detail="Sources must contain at least two unique URLs",
            )
        normalized_urls.add(normalized_url)
        if not source.title.strip() or not source.extracted_at.strip():
            raise HTTPException(
                status_code=422,
                detail="Each source must include title and extraction timestamp",
            )
        evidence = [item.strip() for item in source.evidence if item.strip()]
        if not evidence:
            raise HTTPException(
                status_code=422,
                detail="Each source must include extracted evidence",
            )
        if any(len(item) > 500 for item in evidence):
            raise HTTPException(
                status_code=422,
                detail="Source evidence items must not exceed 500 characters",
            )

    searchable = slugify(f"{data.title} {data.excerpt or ''} {data.content}", 10000)
    sensitive_terms = sorted(
        term for term in SENSITIVE_EDITORIAL_TERMS if slugify(term) in searchable
    )
    has_primary_source = any(
        source.source_type in {"official", "primary"} for source in data.sources
    )
    if sensitive_terms and not has_primary_source:
        raise HTTPException(
            status_code=422,
            detail=(
                "Health or nutrition content requires at least one official "
                "or primary source"
            ),
        )

    return {
        "sources_extracted": True,
        "unique_source_count": len(normalized_urls),
        "sensitive_terms": sensitive_terms,
        "primary_source_required": bool(sensitive_terms),
        "primary_source_present": has_primary_source,
    }


def normalize_webp(content: bytes) -> bytes:
    """Valida uma imagem raster e devolve WebP sem metadados."""
    try:
        with Image.open(BytesIO(content)) as source:
            width, height = source.size
            if width < 640 or height < 360:
                raise ValueError("Image dimensions are too small")
            if width * height > MAX_IMAGE_PIXELS:
                raise ValueError("Image dimensions are too large")
            source.load()
            converted = source.convert("RGB")
            output = BytesIO()
            converted.save(
                output,
                format="WEBP",
                quality=84,
                method=6,
                exif=b"",
            )
            return output.getvalue()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Invalid raster image") from exc

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bloom")

# ── Database Pool (simple connection per request for now) ──
def get_db():
    """Retorna conexão com autocommit desligado."""
    conn = psycopg2.connect(**DB_CONFIG)
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    return conn


async def run_db_task(fn, *args, **kwargs):
    """Executa uma função bloqueante de DB em threadpool e retorna o resultado."""
    loop = asyncio.get_running_loop()
    p = partial(fn, *args, **kwargs)
    return await loop.run_in_executor(None, p)

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

MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(MEDIA_ROOT)), name="media")

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


class SourceEvidence(BaseModel):
    url: str
    title: str
    extracted_at: str
    evidence: List[str]
    source_type: Literal["official", "primary", "secondary"]


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
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    sources: List[SourceEvidence] = Field(default_factory=list)
    status: str = "draft"
    created_by: str = "hermes"


class PostReviewUpdate(BaseModel):
    title: Optional[str] = None
    excerpt: Optional[str] = None
    content: Optional[str] = None
    image_url: Optional[str] = None
    category_slug: Optional[str] = None
    product_asin: Optional[str] = None
    rating: Optional[float] = None
    pros: Optional[List[str]] = None
    cons: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None


class PostReviewDecision(BaseModel):
    decision: str
    reviewer: str = "editor"
    note: Optional[str] = None


class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    page_size: int

# ── TENANTS ────────────────────────────────────────
@app.get("/api/v1/tenants")
async def list_tenants():
    def _sync():
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM tenants WHERE status = 'active' ORDER BY name")
            tenants = cur.fetchall()
            return {"items": [dict(t) for t in tenants]}
        finally:
            conn.close()

    return await run_db_task(_sync)

@app.get("/api/v1/tenants/{slug}")
async def get_tenant(slug: str):
    def _sync(slug_val: str):
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM tenants WHERE slug = %s", (slug_val,))
            t = cur.fetchone()
            return t
        finally:
            conn.close()

    t = await run_db_task(_sync, slug)
    if not t:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return dict(t)

# ── CATEGORIES ─────────────────────────────────────
@app.get("/api/v1/{tenant_slug}/categories")
async def list_categories(tenant_slug: str):
    def _sync(tslug: str):
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT c.* FROM categories c
                JOIN tenants t ON c.tenant_id = t.id
                WHERE t.slug = %s
                ORDER BY c.name
            """, (tslug,))
            cats = cur.fetchall()
            return {"items": [dict(c) for c in cats]}
        finally:
            conn.close()

    return await run_db_task(_sync, tenant_slug)

# ── PRODUCTS ───────────────────────────────────────
@app.get("/api/v1/{tenant_slug}/products")
async def list_products(
    tenant_slug: str,
    category: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    def _sync(tslug: str, category_q: Optional[str], page_q: int, page_size_q: int):
        conn = get_db()
        try:
            cur = conn.cursor()
            params = [tslug]
            where = "WHERE t.slug = %s AND pr.active = true"

            if category_q:
                where += " AND c.slug = %s"
                params.append(category_q)

            # Count
            cur.execute(f"SELECT COUNT(*) as total FROM products pr JOIN tenants t ON pr.tenant_id = t.id LEFT JOIN categories c ON pr.category_id = c.id {where}", params)
            total = cur.fetchone()["total"]

            # Fetch
            offset = (page_q - 1) * page_size_q
            cur.execute(f"""
                SELECT pr.*, c.name as category_name, t.name as tenant_name
                FROM products pr
                JOIN tenants t ON pr.tenant_id = t.id
                LEFT JOIN categories c ON pr.category_id = c.id
                {where}
                ORDER BY pr.created_at DESC
                LIMIT %s OFFSET %s
            """, params + [page_size_q, offset])
            items = [dict(row) for row in cur.fetchall()]

            return {"items": items, "total": total, "page": page_q, "page_size": page_size_q}
        finally:
            conn.close()

    return await run_db_task(_sync, tenant_slug, category, page, page_size)

# ── POSTS ──────────────────────────────────────────
@app.get("/api/v1/{tenant_slug}/posts")
async def list_posts(
    tenant_slug: str,
    category: Optional[str] = None,
    page: int = 1,
    page_size: int = 12,
):
    def _sync(tslug: str, category_q: Optional[str], page_q: int, page_size_q: int):
        conn = get_db()
        try:
            cur = conn.cursor()
            params = [tslug]
            where = "WHERE t.slug = %s AND p.status = 'published'"

            if category_q:
                where += " AND p.category_slug = %s"
                params.append(category_q)

            cur.execute(f"SELECT COUNT(*) as total FROM vw_posts_enriched p JOIN tenants t ON p.tenant_id = t.id {where}", params)
            total = cur.fetchone()["total"]

            offset = (page_q - 1) * page_size_q
            cur.execute(f"""
                SELECT p.* FROM vw_posts_enriched p
                JOIN tenants t ON p.tenant_id = t.id
                {where}
                ORDER BY p.published_at DESC
                LIMIT %s OFFSET %s
            """, params + [page_size_q, offset])
            items = [dict(row) for row in cur.fetchall()]

            return {"items": items, "total": total, "page": page_q, "page_size": page_size_q}
        finally:
            conn.close()

    return await run_db_task(_sync, tenant_slug, category, page, page_size)

@app.get("/api/v1/{tenant_slug}/posts/{slug}")
async def get_post(tenant_slug: str, slug: str):
    def _sync(tslug: str, s: str):
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT p.*, t.name as tenant_name, t.slug as tenant_slug, t.domain
                FROM vw_posts_enriched p
                JOIN tenants t ON p.tenant_id = t.id
                WHERE t.slug = %s AND p.slug = %s AND p.status = 'published'
            """, (tslug, s))
            post = cur.fetchone()
            if post:
                return post

            # Compatibilidade com slugs antigos após a normalização.
            try:
                cur.execute("""
                    SELECT p.*, t.name as tenant_name, t.slug as tenant_slug, t.domain
                    FROM post_slug_redirects r
                    JOIN vw_posts_enriched p
                      ON p.id = r.post_id AND p.tenant_id = r.tenant_id
                    JOIN tenants t ON p.tenant_id = t.id
                    WHERE t.slug = %s AND r.old_slug = %s AND p.status = 'published'
                """, (tslug, s))
                return cur.fetchone()
            except psycopg2.errors.UndefinedTable:
                conn.rollback()
                return None
        finally:
            conn.close()

    post = await run_db_task(_sync, tenant_slug, slug)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return dict(post)

@app.post("/api/v1/{tenant_slug}/posts")
async def create_post(
    tenant_slug: str,
    data: PostCreate,
    authorization: Optional[str] = Header(default=None),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    require_content_token(authorization)
    safe_key = validate_idempotency_key(idempotency_key)
    quality_gates = validate_editorial_sources(data)
    request_hash = post_request_hash(data)

    if data.status not in {"draft", "published"}:
        raise HTTPException(status_code=422, detail="Unsupported post status")
    if data.status == "published" and not CONTENT_AUTOPUBLISH_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="Automatic publishing is disabled; create a draft instead",
        )

    def _sync(
        tslug: str,
        d: PostCreate,
        idem_key: str,
        payload_hash: str,
        gates: Dict[str, Any],
    ):
        conn = get_db()
        try:
            cur = conn.cursor()

            # Resolve tenant_id
            cur.execute("SELECT id FROM tenants WHERE slug = %s", (tslug,))
            t = cur.fetchone()
            if not t:
                return {"error": "Tenant not found"}, 404
            tenant_id = t["id"]

            cur.execute(
                """
                INSERT INTO content_jobs
                    (tenant_id, idempotency_key, request_hash, status)
                VALUES (%s, %s, %s, 'running')
                ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
                RETURNING id
                """,
                (tenant_id, idem_key, payload_hash),
            )
            inserted_job = cur.fetchone()
            if not inserted_job:
                cur.execute(
                    """
                    SELECT request_hash, status, post_id
                    FROM content_jobs
                    WHERE tenant_id = %s AND idempotency_key = %s
                    FOR UPDATE
                    """,
                    (tenant_id, idem_key),
                )
                existing_job = cur.fetchone()
                if existing_job["request_hash"] != payload_hash:
                    return {
                        "error": "Idempotency-Key was already used for another payload"
                    }, 409
                if existing_job["status"] == "completed":
                    cur.execute(
                        "SELECT slug FROM posts WHERE id = %s AND tenant_id = %s",
                        (existing_job["post_id"], tenant_id),
                    )
                    existing_post = cur.fetchone()
                    conn.commit()
                    return {
                        "status": "created",
                        "id": existing_job["post_id"],
                        "slug": existing_post["slug"] if existing_post else None,
                        "replayed": True,
                    }
                return {"error": "An execution with this key is already running"}, 409

            # Resolve category_id. Referências informadas devem ser exatas.
            category_id = None
            if d.category_slug:
                cur.execute("SELECT id FROM categories WHERE tenant_id = %s AND slug = %s", (tenant_id, d.category_slug))
                cat = cur.fetchone()
                if not cat:
                    return {"error": "Category not found for tenant"}, 422
                category_id = cat["id"]

            # Resolve product_id. ASIN informado nunca é ignorado silenciosamente.
            product_id = None
            if d.product_asin:
                cur.execute("SELECT id FROM products WHERE tenant_id = %s AND asin = %s", (tenant_id, d.product_asin))
                prod = cur.fetchone()
                if not prod:
                    return {"error": "Product ASIN not found for tenant"}, 422
                product_id = prod["id"]

            # Normaliza slugs fornecidos e resolve colisões dentro do tenant.
            try:
                slug = unique_post_slug(cur, tenant_id, d.slug or d.title)
            except ValueError as exc:
                return {"error": str(exc)}, 422

            cur.execute("""
                INSERT INTO posts (tenant_id, title, slug, excerpt, content, image_url,
                    category_id, product_id, rating, pros, cons, status, tags, created_by,
                    seo_title, seo_description, source_evidence, quality_gates,
                    published_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,
                    CASE WHEN %s = 'published' THEN NOW() ELSE NULL END)
                RETURNING id
            """, (
                tenant_id, d.title, slug, d.excerpt, d.content,
                d.image_url, category_id, product_id, d.rating,
                psycopg2.extras.Json(d.pros or []),
                psycopg2.extras.Json(d.cons or []),
                d.status,
                psycopg2.extras.Json(d.tags or []),
                d.created_by, d.seo_title, d.seo_description,
                psycopg2.extras.Json(
                    [source.model_dump(mode="json") for source in d.sources]
                ),
                psycopg2.extras.Json(gates),
                d.status,
            ))
            post_id = cur.fetchone()["id"]
            cur.execute(
                """
                UPDATE content_jobs
                SET status = 'completed', post_id = %s, updated_at = NOW()
                WHERE tenant_id = %s AND idempotency_key = %s
                """,
                (post_id, tenant_id, idem_key),
            )
            conn.commit()

            return {
                "status": "created",
                "id": post_id,
                "slug": slug,
                "replayed": False,
            }
        except Exception as e:
            conn.rollback()
            logger.exception("Content automation failed for tenant=%s", tslug)
            return {"error": "Internal content automation error"}, 500
        finally:
            conn.close()

    result = await run_db_task(
        _sync, tenant_slug, data, safe_key, request_hash, quality_gates
    )
    # propagate HTTP-like errors
    if isinstance(result, tuple) and result[1] == 404:
        raise HTTPException(status_code=404, detail=result[0].get('error'))
    if isinstance(result, tuple) and result[1] == 422:
        raise HTTPException(status_code=422, detail=result[0].get('error'))
    if isinstance(result, tuple) and result[1] == 409:
        raise HTTPException(status_code=409, detail=result[0].get('error'))
    if isinstance(result, tuple) and result[1] == 500:
        raise HTTPException(status_code=500, detail=result[0].get('error'))
    return result


def _review_post_query() -> str:
    return """
        SELECT
            p.id, p.tenant_id, t.slug AS tenant_slug, t.name AS tenant_name,
            p.title, p.slug, p.excerpt, p.content, p.image_url,
            c.slug AS category_slug, c.name AS category_name,
            pr.asin AS product_asin, pr.title AS product_title,
            p.rating, p.pros, p.cons, p.tags, p.seo_title,
            p.seo_description, p.source_evidence, p.quality_gates,
            p.status, p.created_by, p.created_at,
            p.updated_at, p.published_at
        FROM posts p
        JOIN tenants t ON t.id = p.tenant_id
        LEFT JOIN categories c
          ON c.id = p.category_id AND c.tenant_id = p.tenant_id
        LEFT JOIN products pr
          ON pr.id = p.product_id AND pr.tenant_id = p.tenant_id
    """


@app.get("/api/v1/editorial/review/posts")
async def list_review_posts(
    tenant_slug: Optional[str] = None,
    status: str = "draft",
    page: int = 1,
    page_size: int = 30,
    authorization: Optional[str] = Header(default=None),
):
    require_review_token(authorization)
    if status not in {"draft", "published", "archived"}:
        raise HTTPException(status_code=422, detail="Unsupported post status")
    if page < 1 or page_size < 1 or page_size > 100:
        raise HTTPException(status_code=422, detail="Invalid pagination")

    def _sync(
        tenant_filter: Optional[str],
        status_filter: str,
        page_q: int,
        page_size_q: int,
    ):
        conn = get_db()
        try:
            cur = conn.cursor()
            conditions = ["p.status = %s"]
            params: List[Any] = [status_filter]
            if tenant_filter:
                conditions.append("t.slug = %s")
                params.append(tenant_filter)
            where = " AND ".join(conditions)
            cur.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM posts p
                JOIN tenants t ON t.id = p.tenant_id
                WHERE {where}
                """,
                params,
            )
            total = cur.fetchone()["total"]
            offset = (page_q - 1) * page_size_q
            cur.execute(
                _review_post_query()
                + f"""
                WHERE {where}
                ORDER BY p.updated_at DESC, p.id DESC
                LIMIT %s OFFSET %s
                """,
                params + [page_size_q, offset],
            )
            return {
                "items": [dict(row) for row in cur.fetchall()],
                "total": total,
                "page": page_q,
                "page_size": page_size_q,
            }
        finally:
            conn.close()

    return await run_db_task(
        _sync, tenant_slug, status, page, page_size
    )


@app.get("/api/v1/editorial/review/posts/{post_id}")
async def get_review_post(
    post_id: int,
    authorization: Optional[str] = Header(default=None),
):
    require_review_token(authorization)

    def _sync(target_id: int):
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute(
                _review_post_query() + " WHERE p.id = %s",
                (target_id,),
            )
            post = cur.fetchone()
            if not post:
                return None
            cur.execute(
                """
                SELECT action, reviewer, note, created_at
                FROM post_reviews
                WHERE post_id = %s
                ORDER BY created_at DESC, id DESC
                """,
                (target_id,),
            )
            result = dict(post)
            result["reviews"] = [dict(row) for row in cur.fetchall()]
            return result
        finally:
            conn.close()

    post = await run_db_task(_sync, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


@app.patch("/api/v1/editorial/review/posts/{post_id}")
async def update_review_post(
    post_id: int,
    data: PostReviewUpdate,
    authorization: Optional[str] = Header(default=None),
    x_reviewer: Optional[str] = Header(default=None, alias="X-Reviewer"),
):
    require_review_token(authorization)
    reviewer = (x_reviewer or "editor").strip()[:100] or "editor"
    supplied = data.model_dump(exclude_unset=True)
    if not supplied:
        raise HTTPException(status_code=422, detail="No fields supplied")
    if "title" in supplied and not (supplied["title"] or "").strip():
        raise HTTPException(status_code=422, detail="Title cannot be empty")
    if "content" in supplied and not (supplied["content"] or "").strip():
        raise HTTPException(status_code=422, detail="Content cannot be empty")
    if data.rating is not None and not 0 <= data.rating <= 5:
        raise HTTPException(status_code=422, detail="Rating must be between 0 and 5")

    scalar_columns = {
        "title": "title",
        "excerpt": "excerpt",
        "content": "content",
        "image_url": "image_url",
        "rating": "rating",
        "seo_title": "seo_title",
        "seo_description": "seo_description",
    }

    def _sync(target_id: int, changes: Dict[str, Any], reviewer_name: str):
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT tenant_id, status FROM posts WHERE id = %s FOR UPDATE",
                (target_id,),
            )
            post = cur.fetchone()
            if not post:
                return {"error": "Post not found"}, 404
            if post["status"] != "draft":
                return {"error": "Only draft posts can be edited"}, 409

            tenant_id = post["tenant_id"]
            assignments = []
            values: List[Any] = []
            for field, column in scalar_columns.items():
                if field in changes:
                    assignments.append(f"{column} = %s")
                    values.append(changes[field])

            for field in ("pros", "cons", "tags"):
                if field in changes:
                    assignments.append(f"{field} = %s")
                    values.append(psycopg2.extras.Json(changes[field] or []))

            if "category_slug" in changes:
                category_id = None
                if changes["category_slug"]:
                    cur.execute(
                        """
                        SELECT id FROM categories
                        WHERE tenant_id = %s AND slug = %s
                        """,
                        (tenant_id, changes["category_slug"]),
                    )
                    category = cur.fetchone()
                    if not category:
                        return {"error": "Category not found for tenant"}, 422
                    category_id = category["id"]
                assignments.append("category_id = %s")
                values.append(category_id)

            if "product_asin" in changes:
                product_id = None
                if changes["product_asin"]:
                    cur.execute(
                        """
                        SELECT id FROM products
                        WHERE tenant_id = %s AND asin = %s
                        """,
                        (tenant_id, changes["product_asin"]),
                    )
                    product = cur.fetchone()
                    if not product:
                        return {"error": "Product ASIN not found for tenant"}, 422
                    product_id = product["id"]
                assignments.append("product_id = %s")
                values.append(product_id)

            assignments.append("updated_at = NOW()")
            cur.execute(
                f"""
                UPDATE posts
                SET {", ".join(assignments)}
                WHERE id = %s AND tenant_id = %s
                """,
                values + [target_id, tenant_id],
            )
            cur.execute(
                """
                INSERT INTO post_reviews
                    (tenant_id, post_id, action, reviewer, note)
                VALUES (%s, %s, 'updated', %s, %s)
                """,
                (
                    tenant_id,
                    target_id,
                    reviewer_name,
                    "Campos alterados: " + ", ".join(sorted(changes)),
                ),
            )
            conn.commit()
            return {"status": "updated", "id": target_id}
        except Exception:
            conn.rollback()
            logger.exception("Editorial update failed for post=%s", target_id)
            return {"error": "Internal editorial review error"}, 500
        finally:
            conn.close()

    result = await run_db_task(_sync, post_id, supplied, reviewer)
    if isinstance(result, tuple):
        raise HTTPException(status_code=result[1], detail=result[0]["error"])
    return result


@app.post("/api/v1/editorial/review/posts/{post_id}/decision")
async def decide_review_post(
    post_id: int,
    data: PostReviewDecision,
    authorization: Optional[str] = Header(default=None),
):
    require_review_token(authorization)
    decision = data.decision.strip().lower()
    if decision not in {"approve", "reject"}:
        raise HTTPException(status_code=422, detail="Unsupported review decision")
    reviewer = data.reviewer.strip()[:100]
    if not reviewer:
        raise HTTPException(status_code=422, detail="Reviewer is required")

    def _sync(target_id: int, action: str, reviewer_name: str, note: Optional[str]):
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT tenant_id, status, title, content
                FROM posts
                WHERE id = %s
                FOR UPDATE
                """,
                (target_id,),
            )
            post = cur.fetchone()
            if not post:
                return {"error": "Post not found"}, 404
            if post["status"] != "draft":
                return {"error": "Post is no longer awaiting review"}, 409
            if action == "approve" and (
                not post["title"].strip() or not post["content"].strip()
            ):
                return {"error": "Draft is incomplete"}, 422

            new_status = "published" if action == "approve" else "archived"
            audit_action = "approved" if action == "approve" else "rejected"
            cur.execute(
                """
                UPDATE posts
                SET status = %s,
                    published_at = CASE
                        WHEN %s = 'published' THEN NOW()
                        ELSE published_at
                    END,
                    updated_at = NOW()
                WHERE id = %s AND tenant_id = %s
                """,
                (new_status, new_status, target_id, post["tenant_id"]),
            )
            cur.execute(
                """
                INSERT INTO post_reviews
                    (tenant_id, post_id, action, reviewer, note)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    post["tenant_id"],
                    target_id,
                    audit_action,
                    reviewer_name,
                    (note or "").strip() or None,
                ),
            )
            conn.commit()
            return {
                "status": new_status,
                "id": target_id,
                "decision": action,
            }
        except Exception:
            conn.rollback()
            logger.exception("Editorial decision failed for post=%s", target_id)
            return {"error": "Internal editorial review error"}, 500
        finally:
            conn.close()

    result = await run_db_task(
        _sync, post_id, decision, reviewer, data.note
    )
    if isinstance(result, tuple):
        raise HTTPException(status_code=result[1], detail=result[0]["error"])
    return result


@app.post("/api/v1/{tenant_slug}/media")
async def upload_post_media(
    tenant_slug: str,
    image: UploadFile = File(...),
    authorization: Optional[str] = Header(default=None),
):
    """Persiste uma imagem WebP deduplicada para uso pelos posts do tenant."""
    require_content_token(authorization)
    if image.content_type not in {
        "image/png",
        "image/jpeg",
        "image/webp",
        "application/octet-stream",
    }:
        raise HTTPException(status_code=415, detail="Unsupported image type")

    content = await image.read(MAX_IMAGE_BYTES + 1)
    await image.close()
    if not content or len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image is empty or too large")
    try:
        webp_content = normalize_webp(content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    def _tenant_exists(tslug: str) -> bool:
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT 1 FROM tenants WHERE slug = %s AND status = 'active'",
                (tslug,),
            )
            return bool(cur.fetchone())
        finally:
            conn.close()

    if not await run_db_task(_tenant_exists, tenant_slug):
        raise HTTPException(status_code=404, detail="Tenant not found")

    digest = hashlib.sha256(webp_content).hexdigest()
    tenant_dir = MEDIA_ROOT / tenant_slug
    tenant_dir.mkdir(parents=True, exist_ok=True)
    final_path = tenant_dir / f"{digest}.webp"
    if not final_path.exists():
        temporary_path = tenant_dir / (
            f".{digest}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
        )
        temporary_path.write_bytes(webp_content)
        try:
            temporary_path.replace(final_path)
        finally:
            temporary_path.unlink(missing_ok=True)

    return {
        "status": "stored",
        "sha256": digest,
        "image_url": f"/media/{tenant_slug}/{digest}.webp",
        "bytes": len(webp_content),
    }

# ── CLICKS ─────────────────────────────────────────
@app.post("/api/v1/{tenant_slug}/clicks")
async def register_click(
    tenant_slug: str,
    product_id: Optional[int] = None,
    post_id: Optional[int] = None,
    link_type: str = "amazon",
    source_url: Optional[str] = None,
):
    def _sync(tslug: str, product_id_q: Optional[int], post_id_q: Optional[int], link_type_q: str, source_url_q: Optional[str]):
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute("SELECT id FROM tenants WHERE slug = %s", (tslug,))
            t = cur.fetchone()
            if not t:
                return {"error": "Tenant not found"}, 404

            if product_id_q is not None:
                cur.execute(
                    "SELECT 1 FROM products WHERE id = %s AND tenant_id = %s",
                    (product_id_q, t["id"]),
                )
                if not cur.fetchone():
                    return {"error": "Product does not belong to tenant"}, 422

            if post_id_q is not None:
                cur.execute(
                    "SELECT 1 FROM posts WHERE id = %s AND tenant_id = %s",
                    (post_id_q, t["id"]),
                )
                if not cur.fetchone():
                    return {"error": "Post does not belong to tenant"}, 422

            ip = "0.0.0.0"

            cur.execute("""
                INSERT INTO clicks (tenant_id, product_id, post_id, link_type, source_url, ip_address)
                VALUES (%s,%s,%s,%s,%s,%s)
            """, (t["id"], product_id_q, post_id_q, link_type_q, source_url_q, ip))
            conn.commit()
            return {"status": "registered"}
        except Exception as e:
            conn.rollback()
            return {"error": str(e)}, 500
        finally:
            conn.close()

    result = await run_db_task(_sync, tenant_slug, product_id, post_id, link_type, source_url)
    if isinstance(result, tuple) and result[1] == 404:
        raise HTTPException(status_code=404, detail=result[0].get('error'))
    if isinstance(result, tuple) and result[1] == 422:
        raise HTTPException(status_code=422, detail=result[0].get('error'))
    if isinstance(result, tuple) and result[1] == 500:
        raise HTTPException(status_code=500, detail=result[0].get('error'))
    return result

# ── USERS ──────────────────────────────────────────
@app.post("/api/v1/{tenant_slug}/users/subscribe")
async def subscribe_user(
    tenant_slug: str,
    email: str,
    name: Optional[str] = None,
    source: str = "newsletter",
):
    def _sync(tslug: str, email_q: str, name_q: Optional[str], source_q: str):
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute("SELECT id FROM tenants WHERE slug = %s", (tslug,))
            t = cur.fetchone()
            if not t:
                return {"error": "Tenant not found"}, 404

            cur.execute("""
                INSERT INTO users (tenant_id, email, name, source)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT (tenant_id, email) DO UPDATE SET status = 'active', name = COALESCE(EXCLUDED.name, users.name)
                RETURNING id
            """, (t["id"], email_q, name_q, source_q))
            user_id = cur.fetchone()["id"]
            conn.commit()
            return {"status": "subscribed", "user_id": user_id}
        except Exception as e:
            conn.rollback()
            return {"error": str(e)}, 500
        finally:
            conn.close()

    result = await run_db_task(_sync, tenant_slug, email, name, source)
    if isinstance(result, tuple) and result[1] == 404:
        raise HTTPException(status_code=404, detail=result[0].get('error'))
    if isinstance(result, tuple) and result[1] == 500:
        raise HTTPException(status_code=500, detail=result[0].get('error'))
    return result

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
