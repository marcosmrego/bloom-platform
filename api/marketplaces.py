"""Marketplace-specific affiliate destination rules (Mercado Livre)."""

import re
from typing import Optional
from urllib.parse import parse_qs, urlparse

from fastapi import HTTPException

MERCADOLIVRE_SHORT_HOST = "meli.la"
MERCADOLIVRE_DOMAIN = "mercadolivre.com.br"
_ID_PATTERN = re.compile(r"MLB-?(\d{6,})", re.IGNORECASE)


def normalize_mercadolivre_id(value: Optional[str]) -> str:
    """Return the canonical MLB<digits> item id or raise 422."""
    match = re.fullmatch(r"MLB-?(\d{6,})", (value or "").strip(), re.IGNORECASE)
    if not match:
        raise HTTPException(status_code=422, detail="Invalid Mercado Livre item id")
    return f"MLB{match.group(1)}"


def is_mercadolivre_host(hostname: Optional[str]) -> bool:
    if not hostname:
        return False
    return hostname == MERCADOLIVRE_SHORT_HOST or hostname == MERCADOLIVRE_DOMAIN or hostname.endswith(
        "." + MERCADOLIVRE_DOMAIN
    )


def validate_mercadolivre_destination(
    link_type: str, destination_url: Optional[str], external_id: Optional[str] = None
) -> Optional[str]:
    """Validate a Mercado Livre affiliate destination without following it.

    Short affiliate links (meli.la) carry no item id, so they are matched
    against the item only when the product is registered and resolved.
    """
    if link_type == "no_match":
        if destination_url or external_id:
            raise HTTPException(status_code=422, detail="No-match proposals cannot include a destination")
        return None
    if link_type != "product":
        raise HTTPException(status_code=422, detail="Mercado Livre supports product links only")
    url = (destination_url or "").strip()
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.port is not None
        or not is_mercadolivre_host(parsed.hostname)
    ):
        raise HTTPException(status_code=422, detail="Destination must be an HTTPS Mercado Livre URL")
    item_id = normalize_mercadolivre_id(external_id)
    if parsed.hostname != MERCADOLIVRE_SHORT_HOST:
        path_ids = [f"MLB{digits}" for digits in _ID_PATTERN.findall(parsed.path)]
        if not path_ids or path_ids[0] != item_id:
            raise HTTPException(status_code=422, detail="Destination URL does not match the item id")
    return url


AMAZON_HOSTS = frozenset({"amazon.com.br", "www.amazon.com.br"})


def classify_commerce_url(url: Optional[str], amazon_tag: str) -> str:
    """Return the marketplace ('amazon' or 'mercadolivre') of a trusted commerce URL."""
    candidate = (url or "").strip()
    parsed = urlparse(candidate)
    if parsed.scheme != "https" or parsed.username is not None or parsed.port is not None:
        raise HTTPException(status_code=422, detail="Commerce URL must be a plain HTTPS URL")
    if parsed.hostname in AMAZON_HOSTS:
        if parse_qs(parsed.query).get("tag") != [amazon_tag]:
            raise HTTPException(
                status_code=422, detail="Commerce URL must contain the configured affiliate tag"
            )
        return "amazon"
    if is_mercadolivre_host(parsed.hostname):
        return "mercadolivre"
    raise HTTPException(
        status_code=422,
        detail="Commerce URL must be an amazon.com.br or Mercado Livre HTTPS URL",
    )
