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
from difflib import SequenceMatcher
from io import BytesIO
import unicodedata
from pathlib import Path
from contextlib import asynccontextmanager
from urllib.parse import urlparse
from datetime import date, datetime, timezone
from decimal import Decimal

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


def analytics_session_hash(value: str) -> str:
    """Pseudonimiza o identificador local sem persistir cookie ou IP bruto."""
    session_id = (value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._:-]{16,128}", session_id):
        raise HTTPException(status_code=422, detail="Invalid analytics session")
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()


def clean_analytics_value(value: Optional[str], max_length: int = 255) -> Optional[str]:
    cleaned = re.sub(r"[\x00-\x1f\x7f]", "", (value or "").strip())
    return cleaned[:max_length] or None


def analytics_host(value: Optional[str]) -> Optional[str]:
    cleaned = clean_analytics_value(value, 1000)
    if not cleaned:
        return None
    try:
        parsed = urlparse(cleaned)
    except ValueError:
        return None
    return (parsed.hostname or "").lower()[:255] or None


def build_performance_alerts(
    posts: List[Dict[str, Any]],
    finance_available: bool,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Transforma métricas em ações conservadoras, sem alterar conteúdo."""
    current = now or datetime.now(timezone.utc)
    alerts: List[Dict[str, Any]] = []
    priority_order = {"high": 0, "medium": 1, "low": 2}

    def add(post, code, priority, title, action):
        alerts.append({
            "code": code,
            "priority": priority,
            "post_id": post["post_id"],
            "tenant_slug": post["tenant_slug"],
            "post_title": post["title"],
            "title": title,
            "action": action,
        })

    for post in posts:
        published_at = post.get("published_at")
        age_days = (current - published_at).days if published_at else 0
        views = int(post.get("views") or 0)
        clicks = int(post.get("clicks") or 0)
        revenue = Decimal(str(post.get("revenue") or 0))

        if not post.get("has_affiliate_link"):
            add(post, "missing_affiliate", "medium", "Artigo sem link afiliado", "Revisar se existe um produto ou destino comercial adequado.")
        if age_days >= 3 and views == 0:
            add(post, "no_traffic", "medium", "Artigo sem tráfego após 3 dias", "Reforçar distribuição e verificar indexação e links internos.")
        if views >= 10 and clicks == 0:
            add(post, "no_clicks", "high", "Visitas sem clique afiliado", "Revisar relevância, posição e texto do CTA.")
        elif views >= 20 and float(post.get("ctr") or 0) < 2:
            add(post, "low_ctr", "medium", "CTR afiliado abaixo de 2%", "Testar CTA ou produto mais alinhado à intenção do artigo.")
        if finance_available and clicks >= 3 and revenue == 0:
            add(post, "clicks_without_revenue", "high", "Cliques sem receita registrada", "Conferir atribuição e relatório da plataforma afiliada.")

        valid_until = post.get("offer_valid_until")
        if valid_until:
            remaining = (valid_until - current).total_seconds()
            if remaining <= 0:
                add(post, "offer_expired", "high", "Oferta ou cupom expirado", "Validar uma nova oferta ou remover o destaque promocional.")
            elif remaining <= 3 * 86400:
                add(post, "offer_expiring", "medium", "Oferta vence em até 3 dias", "Revalidar preço, cupom e disponibilidade antes do vencimento.")

    return sorted(alerts, key=lambda item: (priority_order[item["priority"]], item["post_id"], item["code"]))


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


EDITORIAL_STOPWORDS = {
    "ainda", "alguns", "como", "com", "das", "dos", "entre", "mais",
    "para", "pela", "pelo", "porque", "qual", "quais", "sobre", "uma",
}
PLACEHOLDER_PATTERNS = (
    r"\blorem ipsum\b",
    r"\b(?-i:TODO)\b",
    r"\b(?-i:TBD)\b",
    r"\[(?:inserir|preencher|imagem|fonte|link)[^\]]*\]",
    r"\{\{[^}]+\}\}",
)


def _editorial_tokens(value: str) -> set[str]:
    normalized = unicodedata.normalize("NFKD", value).encode(
        "ascii", "ignore"
    ).decode("ascii").lower()
    return {
        token
        for token in re.findall(r"[a-z0-9]+", normalized)
        if len(token) >= 3 and token not in EDITORIAL_STOPWORDS
    }


def editorial_similarity(left: str, right: str) -> Dict[str, float]:
    left_normalized = " ".join(sorted(_editorial_tokens(left)))
    right_normalized = " ".join(sorted(_editorial_tokens(right)))
    left_tokens = set(left_normalized.split())
    right_tokens = set(right_normalized.split())
    union = left_tokens | right_tokens
    jaccard = len(left_tokens & right_tokens) / len(union) if union else 0.0
    sequence = (
        SequenceMatcher(None, left_normalized, right_normalized).ratio()
        if left_normalized and right_normalized
        else 0.0
    )
    return {"jaccard": round(jaccard, 4), "sequence": round(sequence, 4)}


def find_similar_topic(
    topic: str, candidates: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    closest = None
    for candidate in candidates:
        scores = editorial_similarity(topic, candidate.get("title") or "")
        is_similar = scores["jaccard"] >= 0.65 or scores["sequence"] >= 0.84
        if is_similar and (
            closest is None
            or max(scores.values()) > max(closest["scores"].values())
        ):
            closest = {
                "id": candidate.get("id"),
                "title": candidate.get("title"),
                "slug": candidate.get("slug"),
                "status": candidate.get("status"),
                "scores": scores,
            }
    return closest


def validate_editorial_structure(
    data: "PostCreate", tenant_slug: str
) -> Dict[str, Any]:
    title = data.title.strip()
    excerpt = (data.excerpt or "").strip()
    content = data.content.strip()
    seo_title = (data.seo_title or "").strip()
    seo_description = (data.seo_description or "").strip()
    word_count = len(re.findall(r"\b[\wÀ-ÿ'-]+\b", content))
    h2_count = len(re.findall(r"(?m)^##\s+\S", content))

    checks = (
        (20 <= len(title) <= 120, "Title must contain 20-120 characters"),
        (80 <= len(excerpt) <= 320, "Excerpt must contain 80-320 characters"),
        (len(content) >= 1000, "Content must contain at least 1000 characters"),
        (word_count >= 180, "Content must contain at least 180 words"),
        (h2_count >= 2, "Content must contain at least two H2 sections"),
        (20 <= len(seo_title) <= 70, "SEO title must contain 20-70 characters"),
        (
            80 <= len(seo_description) <= 170,
            "SEO description must contain 80-170 characters",
        ),
        (bool(data.category_slug), "Category is required"),
        (bool(data.image_url), "Image is required"),
    )
    for passed, detail in checks:
        if not passed:
            raise HTTPException(status_code=422, detail=detail)

    if any(re.search(pattern, content, re.IGNORECASE) for pattern in PLACEHOLDER_PATTERNS):
        raise HTTPException(
            status_code=422,
            detail="Content contains placeholders or unfinished text",
        )

    expected_prefix = f"/media/{tenant_slug}/"
    image_url = str(data.image_url)
    if not image_url.startswith(expected_prefix) or not image_url.endswith(".webp"):
        raise HTTPException(
            status_code=422,
            detail="Image must be a tenant-owned Bloom WebP",
        )
    relative_path = image_url.removeprefix("/media/")
    image_path = (MEDIA_ROOT / relative_path).resolve()
    tenant_media_root = (MEDIA_ROOT / tenant_slug).resolve()
    if tenant_media_root not in image_path.parents or not image_path.is_file():
        raise HTTPException(
            status_code=422,
            detail="Image is not persisted in Bloom media storage",
        )

    return {
        "structure_valid": True,
        "word_count": word_count,
        "h2_count": h2_count,
        "placeholders_absent": True,
        "image_webp_persisted": True,
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


class TopicSimilarityCheck(BaseModel):
    topic: str


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
    commerce_link_type: Optional[Literal["product", "search", "offer"]] = None
    commerce_url: Optional[str] = None
    coupon_code: Optional[str] = None
    offer_text: Optional[str] = None
    offer_valid_until: Optional[datetime] = None


class PostReviewDecision(BaseModel):
    decision: str
    reviewer: str = "editor"
    note: Optional[str] = None


class AnalyticsAttribution(BaseModel):
    session_id: str
    source_url: Optional[str] = None
    referrer: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_content: Optional[str] = None
    utm_term: Optional[str] = None


class PageViewCreate(AnalyticsAttribution):
    post_id: int
    path: str


class AffiliateClickCreate(AnalyticsAttribution):
    post_id: int


class FinancialEntryCreate(BaseModel):
    provider: Literal["amazon", "adsense", "adcash", "manual"]
    entry_type: Literal["revenue", "cost"]
    occurred_on: date
    amount: Decimal = Field(ge=0, max_digits=14, decimal_places=4)
    currency: str = "BRL"
    external_id: str = Field(min_length=3, max_length=200)
    post_id: Optional[int] = None
    description: Optional[str] = Field(default=None, max_length=500)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FinancialImportCreate(BaseModel):
    tenant_slug: str
    entries: List[FinancialEntryCreate] = Field(min_length=1, max_length=1000)


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


@app.post("/api/v1/{tenant_slug}/editorial/similarity")
async def check_topic_similarity(
    tenant_slug: str,
    data: TopicSimilarityCheck,
    authorization: Optional[str] = Header(default=None),
):
    require_content_token(authorization)
    topic = data.topic.strip()
    if len(topic) < 10 or len(topic) > 200:
        raise HTTPException(
            status_code=422,
            detail="Topic must contain 10-200 characters",
        )

    def _sync(tslug: str, proposed_topic: str):
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT p.id, p.title, p.slug, p.status
                FROM posts p
                JOIN tenants t ON t.id = p.tenant_id
                WHERE t.slug = %s
                  AND p.status IN ('draft', 'published', 'archived')
                ORDER BY p.updated_at DESC
                LIMIT 500
                """,
                (tslug,),
            )
            candidates = [dict(row) for row in cur.fetchall()]
            return find_similar_topic(proposed_topic, candidates), len(candidates)
        finally:
            conn.close()

    match, checked_count = await run_db_task(_sync, tenant_slug, topic)
    return {
        "similar": match is not None,
        "match": match,
        "checked_count": checked_count,
    }


@app.get("/api/v1/{tenant_slug}/editorial/seasonal-opportunities")
async def list_seasonal_opportunities(
    tenant_slug: str,
    as_of: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
):
    require_content_token(authorization)
    try:
        reference_date = date.fromisoformat(as_of) if as_of else date.today()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="as_of must use YYYY-MM-DD") from exc

    def _sync(tslug: str, reference: date):
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute("SELECT id FROM tenants WHERE slug = %s", (tslug,))
            tenant = cur.fetchone()
            if not tenant:
                return None
            cur.execute(
                """
                SELECT e.id, e.slug, e.name, e.event_date,
                       e.planning_start_date, e.publishing_end_date,
                       e.priority, e.audience_intent,
                       (e.event_date - %s::date) AS days_until,
                       st.id AS target_id, st.product_id, pr.asin,
                       pr.title AS product_title, st.search_query,
                       st.rationale, st.priority AS target_priority,
                       st.status AS target_status
                FROM seasonal_events e
                LEFT JOIN seasonal_product_targets st
                  ON st.event_id = e.id AND st.tenant_id = %s
                LEFT JOIN products pr
                  ON pr.id = st.product_id AND pr.tenant_id = st.tenant_id
                WHERE e.active = TRUE
                  AND %s::date BETWEEN e.planning_start_date AND e.event_date
                ORDER BY e.priority DESC, e.event_date, st.priority DESC
                """,
                (reference, tenant["id"], reference),
            )
            events: Dict[int, Dict[str, Any]] = {}
            for row in cur.fetchall():
                event_id = row["id"]
                event = events.setdefault(event_id, {
                    "id": event_id,
                    "slug": row["slug"],
                    "name": row["name"],
                    "event_date": row["event_date"],
                    "planning_start_date": row["planning_start_date"],
                    "publishing_end_date": row["publishing_end_date"],
                    "priority": row["priority"],
                    "audience_intent": row["audience_intent"],
                    "days_until": row["days_until"],
                    "inside_publishing_window": reference <= row["publishing_end_date"],
                    "targets": [],
                })
                if row["target_id"]:
                    event["targets"].append({
                        "id": row["target_id"],
                        "product_id": row["product_id"],
                        "asin": row["asin"],
                        "product_title": row["product_title"],
                        "search_query": row["search_query"],
                        "rationale": row["rationale"],
                        "priority": row["target_priority"],
                        "status": row["target_status"],
                    })
            return list(events.values())
        finally:
            conn.close()

    opportunities = await run_db_task(_sync, tenant_slug, reference_date)
    if opportunities is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {"as_of": reference_date, "items": opportunities}


@app.post("/api/v1/{tenant_slug}/posts")
async def create_post(
    tenant_slug: str,
    data: PostCreate,
    authorization: Optional[str] = Header(default=None),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    require_content_token(authorization)
    safe_key = validate_idempotency_key(idempotency_key)
    quality_gates = {
        **validate_editorial_sources(data),
        **validate_editorial_structure(data, tenant_slug),
    }
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
                SELECT id, title, slug, status
                FROM posts
                WHERE tenant_id = %s
                  AND status IN ('draft', 'published', 'archived')
                ORDER BY updated_at DESC
                LIMIT 500
                """,
                (tenant_id,),
            )
            similar = find_similar_topic(d.title, [dict(row) for row in cur.fetchall()])
            if similar:
                return {
                    "error": "Topic is too similar to existing content",
                    "match": similar,
                }, 422
            gates["similarity_valid"] = True
            gates["similarity_thresholds"] = {
                "jaccard": 0.65,
                "sequence": 0.84,
            }

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
            COALESCE(pc.destination_url, pr.affiliate_url) AS affiliate_url,
            pc.link_type AS commerce_link_type,
            pc.destination_url AS commerce_url,
            pc.coupon_code,
            pc.offer_text,
            pc.valid_until AS offer_valid_until,
            pc.verified_at AS offer_verified_at,
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
        LEFT JOIN post_commerce pc
          ON pc.post_id = p.id AND pc.tenant_id = p.tenant_id
    """


@app.get("/api/v1/editorial/review/metrics")
async def get_editorial_metrics(
    tenant_slug: Optional[str] = None,
    days: int = 30,
    authorization: Optional[str] = Header(default=None),
):
    require_review_token(authorization)
    if days not in {7, 30, 90}:
        raise HTTPException(status_code=422, detail="Days must be 7, 30 or 90")

    def _sync(tslug: Optional[str], period_days: int):
        conn = get_db()
        try:
            cur = conn.cursor()
            params: List[Any] = [period_days, period_days, period_days]
            tenant_filter = ""
            if tslug:
                tenant_filter = "AND p.tenant_slug = %s"
                params.append(tslug)
            cur.execute(
                f"""
                WITH view_totals AS (
                    SELECT tenant_id, post_id, COUNT(*) AS views
                    FROM page_views
                    WHERE created_at >= NOW() - (%s * INTERVAL '1 day')
                    GROUP BY tenant_id, post_id
                ), click_totals AS (
                    SELECT tenant_id, post_id, COUNT(*) AS clicks
                    FROM clicks
                    WHERE created_at >= NOW() - (%s * INTERVAL '1 day')
                      AND post_id IS NOT NULL
                    GROUP BY tenant_id, post_id
                ), finance_totals AS (
                    SELECT tenant_id, post_id,
                           SUM(amount) FILTER (WHERE entry_type = 'revenue' AND currency = 'BRL') AS revenue,
                           SUM(amount) FILTER (WHERE entry_type = 'cost' AND currency = 'BRL') AS cost
                    FROM financial_entries
                    WHERE occurred_on >= CURRENT_DATE - (%s * INTERVAL '1 day')
                      AND post_id IS NOT NULL
                    GROUP BY tenant_id, post_id
                )
                SELECT p.id AS post_id, p.tenant_slug, p.tenant_name,
                       p.title, p.slug, p.published_at, p.affiliate_url IS NOT NULL AS has_affiliate_link,
                       p.offer_valid_until,
                       COALESCE(v.views, 0) AS views,
                       COALESCE(c.clicks, 0) AS clicks,
                       CASE WHEN COALESCE(v.views, 0) = 0 THEN 0
                            ELSE ROUND((COALESCE(c.clicks, 0)::numeric / v.views) * 100, 2)
                       END AS ctr,
                       COALESCE(f.revenue, 0) AS revenue,
                       COALESCE(f.cost, 0) AS cost,
                       COALESCE(f.revenue, 0) - COALESCE(f.cost, 0) AS result
                FROM vw_posts_enriched p
                LEFT JOIN view_totals v ON v.tenant_id = p.tenant_id AND v.post_id = p.id
                LEFT JOIN click_totals c ON c.tenant_id = p.tenant_id AND c.post_id = p.id
                LEFT JOIN finance_totals f ON f.tenant_id = p.tenant_id AND f.post_id = p.id
                WHERE p.status = 'published' {tenant_filter}
                ORDER BY views DESC, clicks DESC, p.published_at DESC NULLS LAST
                """,
                params,
            )
            posts = [dict(row) for row in cur.fetchall()]
            summary = {
                "published_posts": len(posts),
                "views": sum(row["views"] for row in posts),
                "clicks": sum(row["clicks"] for row in posts),
            }
            summary["ctr"] = round(
                (summary["clicks"] / summary["views"] * 100) if summary["views"] else 0,
                2,
            )

            source_params: List[Any] = [period_days]
            source_filter = ""
            if tslug:
                source_filter = "AND t.slug = %s"
                source_params.append(tslug)
            cur.execute(
                f"""
                SELECT COALESCE(NULLIF(pv.utm_source, ''), NULLIF(pv.referrer_host, ''), 'direct') AS source,
                       COUNT(*) AS views
                FROM page_views pv
                JOIN tenants t ON t.id = pv.tenant_id
                WHERE pv.created_at >= NOW() - (%s * INTERVAL '1 day') {source_filter}
                GROUP BY source
                ORDER BY views DESC, source
                LIMIT 10
                """,
                source_params,
            )
            sources = [dict(row) for row in cur.fetchall()]
            finance_params: List[Any] = [period_days]
            finance_filter = ""
            if tslug:
                finance_filter = "AND t.slug = %s"
                finance_params.append(tslug)
            cur.execute(
                f"""
                SELECT fe.provider, fe.currency,
                       SUM(fe.amount) FILTER (WHERE fe.entry_type = 'revenue') AS revenue,
                       SUM(fe.amount) FILTER (WHERE fe.entry_type = 'cost') AS cost,
                       SUM(fe.amount) FILTER (WHERE fe.post_id IS NULL AND fe.entry_type = 'revenue') AS unattributed_revenue
                FROM financial_entries fe
                JOIN tenants t ON t.id = fe.tenant_id
                WHERE fe.occurred_on >= CURRENT_DATE - (%s * INTERVAL '1 day') {finance_filter}
                GROUP BY fe.provider, fe.currency
                ORDER BY fe.provider, fe.currency
                """,
                finance_params,
            )
            finance_rows = [dict(row) for row in cur.fetchall()]
            brl_revenue = sum((row["revenue"] or Decimal("0")) for row in finance_rows if row["currency"] == "BRL")
            brl_cost = sum((row["cost"] or Decimal("0")) for row in finance_rows if row["currency"] == "BRL")
            brl_unattributed = sum((row["unattributed_revenue"] or Decimal("0")) for row in finance_rows if row["currency"] == "BRL")
            alerts = build_performance_alerts(posts, bool(finance_rows))
            return {
                "period_days": period_days,
                "tenant_slug": tslug,
                "summary": summary,
                "posts": posts,
                "sources": sources,
                "alerts": alerts,
                "alert_summary": {
                    "total": len(alerts),
                    "high": sum(1 for alert in alerts if alert["priority"] == "high"),
                    "medium": sum(1 for alert in alerts if alert["priority"] == "medium"),
                    "low": sum(1 for alert in alerts if alert["priority"] == "low"),
                },
                "finance": {
                    "status": "available" if finance_rows else "awaiting_import",
                    "currency": "BRL",
                    "revenue": brl_revenue,
                    "cost": brl_cost,
                    "result": brl_revenue - brl_cost,
                    "unattributed_revenue": brl_unattributed,
                    "providers": finance_rows,
                },
            }
        finally:
            conn.close()

    return await run_db_task(_sync, tenant_slug, days)


@app.post("/api/v1/editorial/review/revenue/import")
async def import_financial_entries(
    data: FinancialImportCreate,
    authorization: Optional[str] = Header(default=None),
):
    require_review_token(authorization)

    def _sync(payload: FinancialImportCreate):
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute("SELECT id FROM tenants WHERE slug = %s AND status = 'active'", (payload.tenant_slug,))
            tenant = cur.fetchone()
            if not tenant:
                raise HTTPException(status_code=404, detail="Tenant not found")
            tenant_id = tenant["id"]
            post_ids = {entry.post_id for entry in payload.entries if entry.post_id is not None}
            if post_ids:
                cur.execute(
                    "SELECT id FROM posts WHERE tenant_id = %s AND id = ANY(%s)",
                    (tenant_id, list(post_ids)),
                )
                found = {row["id"] for row in cur.fetchall()}
                missing = sorted(post_ids - found)
                if missing:
                    raise HTTPException(status_code=422, detail=f"Posts do not belong to tenant: {missing}")
            inserted = 0
            updated = 0
            for entry in payload.entries:
                currency = entry.currency.strip().upper()
                if not re.fullmatch(r"[A-Z]{3}", currency):
                    raise HTTPException(status_code=422, detail="Currency must be a three-letter ISO code")
                cur.execute(
                    """
                    INSERT INTO financial_entries
                        (tenant_id, post_id, provider, entry_type, occurred_on, amount,
                         currency, external_id, description, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (tenant_id, provider, external_id) DO UPDATE SET
                        post_id = EXCLUDED.post_id,
                        entry_type = EXCLUDED.entry_type,
                        occurred_on = EXCLUDED.occurred_on,
                        amount = EXCLUDED.amount,
                        currency = EXCLUDED.currency,
                        description = EXCLUDED.description,
                        metadata = EXCLUDED.metadata,
                        imported_at = NOW()
                    RETURNING (xmax = 0) AS inserted
                    """,
                    (
                        tenant_id, entry.post_id, entry.provider, entry.entry_type,
                        entry.occurred_on, entry.amount, currency, entry.external_id.strip(),
                        entry.description, json.dumps(entry.metadata, ensure_ascii=False),
                    ),
                )
                if cur.fetchone()["inserted"]:
                    inserted += 1
                else:
                    updated += 1
            conn.commit()
            return {"status": "imported", "inserted": inserted, "updated": updated, "total": len(payload.entries)}
        except HTTPException:
            conn.rollback()
            raise
        except Exception:
            conn.rollback()
            logging.exception("Financial import failed")
            raise HTTPException(status_code=500, detail="Financial import failed")
        finally:
            conn.close()

    return await run_db_task(_sync, data)


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
    commerce_fields = {
        "commerce_link_type", "commerce_url", "coupon_code", "offer_text",
        "offer_valid_until",
    }
    commerce_changed = bool(commerce_fields.intersection(supplied))
    if supplied.get("commerce_link_type"):
        commerce_url = (supplied.get("commerce_url") or "").strip()
        parsed_commerce_url = urlparse(commerce_url)
        if parsed_commerce_url.scheme != "https" or parsed_commerce_url.hostname not in {
            "amazon.com.br", "www.amazon.com.br"
        }:
            raise HTTPException(
                status_code=422,
                detail="Commerce URL must be an HTTPS amazon.com.br URL",
            )
        if "tag=marcosmrego-20" not in parsed_commerce_url.query:
            raise HTTPException(
                status_code=422,
                detail="Commerce URL must contain the configured affiliate tag",
            )
        if supplied["commerce_link_type"] == "offer" and not (
            supplied.get("offer_text") or ""
        ).strip():
            raise HTTPException(status_code=422, detail="Offer text is required")
        valid_until = supplied.get("offer_valid_until")
        if valid_until:
            comparable_until = valid_until
            if comparable_until.tzinfo is None:
                comparable_until = comparable_until.replace(tzinfo=timezone.utc)
            if comparable_until <= datetime.now(timezone.utc):
                raise HTTPException(status_code=422, detail="Offer validity must be in the future")
        if supplied["commerce_link_type"] == "product" and not (
            supplied.get("product_asin") or ""
        ).strip():
            raise HTTPException(status_code=422, detail="Product link requires an ASIN")

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

            if commerce_changed:
                link_type = changes.get("commerce_link_type")
                if not link_type:
                    cur.execute(
                        "DELETE FROM post_commerce WHERE post_id = %s AND tenant_id = %s",
                        (target_id, tenant_id),
                    )
                else:
                    commerce_product_id = product_id if "product_asin" in changes else None
                    if "product_asin" not in changes:
                        cur.execute(
                            "SELECT product_id FROM posts WHERE id = %s AND tenant_id = %s",
                            (target_id, tenant_id),
                        )
                        commerce_product_id = cur.fetchone()["product_id"]
                    if link_type == "product" and not commerce_product_id:
                        return {"error": "Product link requires an associated ASIN"}, 422
                    cur.execute(
                        """
                        INSERT INTO post_commerce (
                            tenant_id, post_id, link_type, product_id,
                            destination_url, coupon_code, offer_text,
                            valid_until, verified_at, status
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW(),'active')
                        ON CONFLICT (post_id) DO UPDATE SET
                            link_type = EXCLUDED.link_type,
                            product_id = EXCLUDED.product_id,
                            destination_url = EXCLUDED.destination_url,
                            coupon_code = EXCLUDED.coupon_code,
                            offer_text = EXCLUDED.offer_text,
                            valid_until = EXCLUDED.valid_until,
                            verified_at = NOW(),
                            status = 'active',
                            updated_at = NOW()
                        """,
                        (
                            tenant_id, target_id, link_type, commerce_product_id,
                            changes.get("commerce_url"),
                            (changes.get("coupon_code") or "").strip() or None,
                            (changes.get("offer_text") or "").strip() or None,
                            changes.get("offer_valid_until") or None,
                        ),
                    )

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
def _analytics_fields(data: AnalyticsAttribution) -> Dict[str, Optional[str]]:
    return {
        "session_hash": analytics_session_hash(data.session_id),
        "referrer_host": analytics_host(data.referrer),
        "utm_source": clean_analytics_value(data.utm_source),
        "utm_medium": clean_analytics_value(data.utm_medium),
        "utm_campaign": clean_analytics_value(data.utm_campaign),
        "utm_content": clean_analytics_value(data.utm_content),
        "utm_term": clean_analytics_value(data.utm_term),
    }


@app.post("/api/v1/{tenant_slug}/analytics/page-view")
async def register_page_view(tenant_slug: str, data: PageViewCreate):
    fields = _analytics_fields(data)
    path = clean_analytics_value(data.path, 500)
    if not path or not path.startswith("/") or path.startswith("//"):
        raise HTTPException(status_code=422, detail="Invalid analytics path")

    def _sync(tslug: str, payload: PageViewCreate, normalized: Dict[str, Optional[str]], safe_path: str):
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT p.id, p.tenant_id, t.domain
                FROM posts p JOIN tenants t ON t.id = p.tenant_id
                WHERE t.slug = %s AND p.id = %s AND p.status = 'published'
                """,
                (tslug, payload.post_id),
            )
            post = cur.fetchone()
            if not post:
                return {"error": "Published post not found"}, 404
            source_host = analytics_host(payload.source_url)
            if source_host and source_host not in {post["domain"], f"www.{post['domain']}"}:
                return {"error": "Source URL does not match tenant"}, 422
            cur.execute(
                """
                INSERT INTO page_views
                    (tenant_id, post_id, session_hash, path, referrer_host,
                     utm_source, utm_medium, utm_campaign, utm_content, utm_term)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (tenant_id, post_id, session_hash, view_date) DO NOTHING
                RETURNING id
                """,
                (
                    post["tenant_id"], payload.post_id, normalized["session_hash"],
                    safe_path, normalized["referrer_host"], normalized["utm_source"],
                    normalized["utm_medium"], normalized["utm_campaign"],
                    normalized["utm_content"], normalized["utm_term"],
                ),
            )
            inserted = bool(cur.fetchone())
            conn.commit()
            return {"status": "registered" if inserted else "deduplicated"}
        except Exception:
            conn.rollback()
            logger.exception("Page view registration failed")
            return {"error": "Analytics ingestion failed"}, 500
        finally:
            conn.close()

    result = await run_db_task(_sync, tenant_slug, data, fields, path)
    if isinstance(result, tuple):
        raise HTTPException(status_code=result[1], detail=result[0]["error"])
    return result


@app.post("/api/v1/{tenant_slug}/analytics/affiliate-click")
async def register_affiliate_click(tenant_slug: str, data: AffiliateClickCreate):
    fields = _analytics_fields(data)

    def _sync(tslug: str, payload: AffiliateClickCreate, normalized: Dict[str, Optional[str]]):
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT p.id, p.tenant_id, p.product_id, t.domain,
                       v.affiliate_url, COALESCE(v.commerce_link_type, 'product') AS link_type
                FROM posts p
                JOIN tenants t ON t.id = p.tenant_id
                JOIN vw_posts_enriched v ON v.id = p.id AND v.tenant_id = p.tenant_id
                WHERE t.slug = %s AND p.id = %s AND p.status = 'published'
                """,
                (tslug, payload.post_id),
            )
            post = cur.fetchone()
            if not post or not post["affiliate_url"]:
                return {"error": "Active affiliate destination not found"}, 404
            source_host = analytics_host(payload.source_url)
            if source_host and source_host not in {post["domain"], f"www.{post['domain']}"}:
                return {"error": "Source URL does not match tenant"}, 422
            cur.execute(
                """
                INSERT INTO clicks
                    (tenant_id, product_id, post_id, link_type, source_url,
                     session_hash, referrer_host, destination_host,
                     utm_source, utm_medium, utm_campaign, utm_content, utm_term)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    post["tenant_id"], post["product_id"], payload.post_id,
                    post["link_type"], clean_analytics_value(payload.source_url, 1000),
                    normalized["session_hash"], normalized["referrer_host"],
                    analytics_host(post["affiliate_url"]), normalized["utm_source"],
                    normalized["utm_medium"], normalized["utm_campaign"],
                    normalized["utm_content"], normalized["utm_term"],
                ),
            )
            conn.commit()
            return {"status": "registered", "destination_url": post["affiliate_url"]}
        except Exception:
            conn.rollback()
            logger.exception("Affiliate click registration failed")
            return {"error": "Analytics ingestion failed"}, 500
        finally:
            conn.close()

    result = await run_db_task(_sync, tenant_slug, data, fields)
    if isinstance(result, tuple):
        raise HTTPException(status_code=result[1], detail=result[0]["error"])
    return result


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
