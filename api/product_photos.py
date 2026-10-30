"""Download the main photo of a Mercado Livre product from its image CDN."""

from typing import Optional
from urllib.parse import urlparse

import httpx

PHOTO_HOST = "mlstatic.com"
MAX_PHOTO_BYTES = 5 * 1024 * 1024
PHOTO_CREDIT = "Mercado Livre"
PRODUCT_PHOTO_MIN_SIDE = 300


class ProductPhotoError(Exception):
    """The product photo could not be fetched safely."""


def is_product_photo_url(url: Optional[str]) -> bool:
    parsed = urlparse((url or "").strip())
    host = parsed.hostname or ""
    return (
        parsed.scheme == "https"
        and parsed.username is None
        and parsed.port in (None, 443)
        and (host == PHOTO_HOST or host.endswith("." + PHOTO_HOST))
    )


def _prefer_https(url: str) -> str:
    """The catalog API sometimes returns http:// CDN URLs; the CDN serves the same image over https."""
    candidate = (url or "").strip()
    if candidate.startswith("http://") and is_product_photo_url("https://" + candidate[len("http://"):]):
        return "https://" + candidate[len("http://"):]
    return candidate


async def fetch_product_photo(client: httpx.AsyncClient, url: str) -> bytes:
    """Fetch an image from the Mercado Livre CDN only, without redirects, capped in size."""
    url = _prefer_https(url)
    if not is_product_photo_url(url):
        raise ProductPhotoError("Photo URL is not a Mercado Livre image")
    try:
        async with client.stream("GET", url, follow_redirects=False) as response:
            if response.status_code != 200:
                raise ProductPhotoError(f"Photo request returned HTTP {response.status_code}")
            if not response.headers.get("content-type", "").startswith("image/"):
                raise ProductPhotoError("Photo response is not an image")
            chunks, size = [], 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > MAX_PHOTO_BYTES:
                    raise ProductPhotoError("Photo is too large")
                chunks.append(chunk)
    except httpx.HTTPError as exc:
        raise ProductPhotoError("Photo could not be downloaded") from exc
    return b"".join(chunks)
