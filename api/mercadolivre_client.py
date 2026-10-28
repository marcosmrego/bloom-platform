"""Mercado Livre API client: OAuth token lifecycle, item lookup, short-link resolution."""

import asyncio
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Awaitable, Callable, Optional, Protocol, Tuple
from urllib.parse import parse_qs, urljoin, urlparse

import httpx

from marketplaces import is_mercadolivre_host

API_BASE = "https://api.mercadolibre.com"
TOKEN_URL = f"{API_BASE}/oauth/token"
TOKEN_EXPIRY_MARGIN = timedelta(seconds=60)
MAX_REDIRECTS = 5
MIN_NAME_OVERLAP = 0.5
_ITEM_ID = re.compile(r"MLB-?(\d{6,})", re.IGNORECASE)
_STOPWORDS = frozenset({"para", "com", "sem", "kit", "uma", "por", "dos", "das"})


class MarketplaceUnavailable(Exception):
    """The marketplace could not provide trustworthy data."""


@dataclass(frozen=True)
class MercadoLivreCredentials:
    client_id: str
    client_secret: str
    redirect_uri: str


@dataclass(frozen=True)
class StoredTokens:
    access_token: str
    refresh_token: str
    expires_at: datetime


@dataclass(frozen=True)
class MercadoLivreItem:
    external_id: str
    title: str
    price: Optional[Decimal]
    permalink: str
    image_url: Optional[str]
    available: bool
    category_id: Optional[str]


class TokenStore(Protocol):
    async def load(self) -> Optional[StoredTokens]: ...

    async def save(self, tokens: StoredTokens) -> None: ...


class MercadoLivreTokenManager:
    """Keeps a valid access token, persisting each rotated refresh token."""

    def __init__(
        self,
        credentials: MercadoLivreCredentials,
        store: TokenStore,
        client: httpx.AsyncClient,
        seed_tokens: Tuple[str, str] = ("", ""),
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._credentials = credentials
        self._store = store
        self._client = client
        self._seed_refresh_token = seed_tokens[1]
        self._now = now
        self._lock = asyncio.Lock()

    async def access_token(self) -> str:
        async with self._lock:
            tokens = await self._store.load()
            if tokens and tokens.expires_at - TOKEN_EXPIRY_MARGIN > self._now():
                return tokens.access_token
            refresh_token = tokens.refresh_token if tokens else self._seed_refresh_token
            if not refresh_token:
                raise MarketplaceUnavailable("Mercado Livre refresh token is not configured")
            refreshed = await self._refresh(refresh_token)
            await self._store.save(refreshed)
            return refreshed.access_token

    async def _refresh(self, refresh_token: str) -> StoredTokens:
        try:
            response = await self._client.post(
                TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": self._credentials.client_id,
                    "client_secret": self._credentials.client_secret,
                    "refresh_token": refresh_token,
                },
                headers={"Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise MarketplaceUnavailable(f"Mercado Livre token refresh failed: {type(exc).__name__}") from exc
        if response.status_code != 200:
            raise MarketplaceUnavailable(
                f"Mercado Livre token refresh failed (HTTP {response.status_code})"
            )
        payload = response.json()
        try:
            return StoredTokens(
                access_token=payload["access_token"],
                refresh_token=payload.get("refresh_token") or refresh_token,
                expires_at=self._now() + timedelta(seconds=int(payload["expires_in"])),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise MarketplaceUnavailable("Mercado Livre token response is malformed") from exc


def parse_item(payload: dict) -> MercadoLivreItem:
    item_id = str(payload.get("id") or "")
    title = str(payload.get("title") or "").strip()
    permalink = str(payload.get("permalink") or "")
    parsed = urlparse(permalink)
    if (
        not re.fullmatch(r"MLB\d{6,}", item_id)
        or not title
        or parsed.scheme != "https"
        or not is_mercadolivre_host(parsed.hostname)
    ):
        raise MarketplaceUnavailable("Mercado Livre item payload is malformed")
    price = payload.get("price")
    pictures = payload.get("pictures") or []
    return MercadoLivreItem(
        external_id=item_id,
        title=title,
        price=Decimal(str(price)).quantize(Decimal("0.01")) if price is not None else None,
        permalink=permalink,
        image_url=(pictures[0].get("secure_url") if pictures else None),
        available=payload.get("status") == "active" and (payload.get("available_quantity") or 0) > 0,
        category_id=payload.get("category_id"),
    )


async def fetch_item(
    client: httpx.AsyncClient, tokens: MercadoLivreTokenManager, item_id: str
) -> MercadoLivreItem:
    token = await tokens.access_token()
    try:
        response = await client.get(
            f"{API_BASE}/items/{item_id}", headers={"Authorization": f"Bearer {token}"}
        )
    except httpx.HTTPError as exc:
        raise MarketplaceUnavailable(f"Mercado Livre item lookup failed: {type(exc).__name__}") from exc
    if response.status_code != 200:
        raise MarketplaceUnavailable(f"Mercado Livre item lookup failed (HTTP {response.status_code})")
    return parse_item(response.json())


def _item_id_from_url(url: str) -> Optional[str]:
    parsed = urlparse(url)
    match = _ITEM_ID.search(parsed.path)
    if not match:
        query = parse_qs(parsed.query)
        match = next(
            (m for key in ("item_id", "wid") for v in query.get(key, []) if (m := _ITEM_ID.fullmatch(v))),
            None,
        )
    return f"MLB{match.group(1)}" if match else None


async def resolve_item_id(client: httpx.AsyncClient, link: str) -> Optional[str]:
    """Follow an affiliate short link through Mercado Livre hosts only."""
    url = link
    for _ in range(MAX_REDIRECTS + 1):
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.username is not None or not is_mercadolivre_host(parsed.hostname):
            return None
        item_id = _item_id_from_url(url)
        if item_id:
            return item_id
        try:
            response = await client.get(url, follow_redirects=False)
        except httpx.HTTPError:
            return None
        location = response.headers.get("location")
        if response.status_code not in (301, 302, 303, 307, 308) or not location:
            return None
        url = urljoin(url, location)
    return None


def _tokens(text: str) -> frozenset:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return frozenset(
        word for word in re.findall(r"[a-z0-9]+", ascii_text.lower())
        if len(word) >= 3 and word not in _STOPWORDS
    )


def name_matches_title(name: str, title: str) -> bool:
    """Guard against a link that points to a different product than the name given."""
    wanted = _tokens(name)
    if not wanted:
        return False
    return len(wanted & _tokens(title)) / len(wanted) >= MIN_NAME_OVERLAP
