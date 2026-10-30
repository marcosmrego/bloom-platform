"""Register a Mercado Livre affiliate product from a name and an affiliate link."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

import httpx
from fastapi import HTTPException

from marketplaces import normalize_mercadolivre_id, validate_mercadolivre_destination
from mercadolivre_client import (
    MarketplaceUnavailable,
    MercadoLivreTokenManager,
    fetch_listing,
    name_matches_title,
    resolve_link,
)


@dataclass(frozen=True)
class MercadoLivreProduct:
    external_id: str
    title: str
    price: Optional[Decimal]
    image_url: Optional[str]
    permalink: str
    affiliate_link: str
    category_id: Optional[str]


async def register_mercadolivre_product(
    name: Optional[str],
    affiliate_link: str,
    client: httpx.AsyncClient,
    tokens: MercadoLivreTokenManager,
    item_id: Optional[str] = None,
) -> MercadoLivreProduct:
    """Resolve and verify the item behind an affiliate link before it is used."""
    page_title = None
    if item_id:
        resolved_id = normalize_mercadolivre_id(item_id)
    else:
        resolved = await resolve_link(client, affiliate_link)
        if not resolved:
            raise HTTPException(
                status_code=422,
                detail="Could not identify the item from the link; send the product item_id (MLB...)",
            )
        resolved_id, page_title = resolved.item_id, resolved.page_title
        if not name and not page_title:
            raise HTTPException(
                status_code=422,
                detail="Could not confirm the product from the link page; send the product name",
            )
    link = validate_mercadolivre_destination("product", affiliate_link, resolved_id)
    try:
        item = await fetch_listing(client, tokens, resolved_id)
    except MarketplaceUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if item.external_id != resolved_id:
        raise HTTPException(status_code=422, detail="Mercado Livre returned a different item")
    for label, wanted in (("product name", name), ("link page", page_title)):
        if wanted and not name_matches_title(wanted, item.title):
            raise HTTPException(
                status_code=422,
                detail=f"Link points to '{item.title}', which does not match the {label}",
            )
    if not item.available:
        raise HTTPException(status_code=422, detail="Listing is not available for sale")
    return MercadoLivreProduct(
        external_id=item.external_id,
        title=item.title,
        price=item.price,
        image_url=item.image_url,
        permalink=item.permalink,
        affiliate_link=link,
        category_id=item.category_id,
    )
