"""Marketplace-specific affiliate destination rules (Mercado Livre)."""

import re
from typing import Optional
from urllib.parse import urlparse

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
