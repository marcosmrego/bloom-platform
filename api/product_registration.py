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
    resolve_item_id,
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
    name: str,
    affiliate_link: str,
    client: httpx.AsyncClient,
    tokens: MercadoLivreTokenManager,
    item_id: Optional[str] = None,
) -> MercadoLivreProduct:
    """Resolve and verify the item behind an affiliate link before it is used."""
    if item_id:
        resolved_id = normalize_mercadolivre_id(item_id)
    else:
        resolved_id = await resolve_item_id(client, affiliate_link)
        if not resolved_id:
            raise HTTPException(
                status_code=422,
                detail="Could not identify the item from the link; send the product item_id (MLB...)",
            )
    link = validate_mercadolivre_destination("product", affiliate_link, resolved_id)
    try:
        item = await fetch_listing(client, tokens, resolved_id)
    except MarketplaceUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if item.external_id != resolved_id:
        raise HTTPException(status_code=422, detail="Mercado Livre returned a different item")
    if not name_matches_title(name, item.title):
        raise HTTPException(
            status_code=422,
            detail=f"Link points to '{item.title}', which does not match the product name",
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
