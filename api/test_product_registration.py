import asyncio
import unittest
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import HTTPException

from mercadolivre_client import MercadoLivreCredentials, MercadoLivreTokenManager, StoredTokens
from product_registration import register_mercadolivre_product

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
SHORT_LINK = "https://meli.la/2AbCdEf"
LISTING = "https://produto.mercadolivre.com.br/MLB-3456789012-organizador-de-cabos-_JM"
ITEM = {
    "id": "MLB3456789012",
    "title": "Organizador De Cabos Mesa Escritorio",
    "price": 29.9,
    "permalink": LISTING,
    "status": "active",
    "available_quantity": 5,
    "category_id": "MLB1648",
    "pictures": [{"secure_url": "https://http2.mlstatic.com/D_1.jpg"}],
}


class FixedStore:
    async def load(self):
        return StoredTokens("live", "refresh", NOW + timedelta(hours=2))

    async def save(self, tokens):
        raise AssertionError("token must not be refreshed")


def register(name, link, item=ITEM, item_status=200, item_id=None, short_target=LISTING, catalog=None, catalog_status=404):
    def handler(request):
        url = str(request.url)
        if request.url.host == "meli.la":
            return httpx.Response(302, headers={"location": short_target})
        if request.url.path.startswith("/products/"):
            return httpx.Response(catalog_status, json=catalog or {})
        if request.url.path.startswith("/items/"):
            return httpx.Response(item_status, json=item)
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tokens = MercadoLivreTokenManager(
        MercadoLivreCredentials("1", "s", "https://x.test"), FixedStore(), client, now=lambda: NOW
    )
    return asyncio.run(register_mercadolivre_product(name, link, client, tokens, item_id=item_id))


class RegisterMercadoLivreProductTests(unittest.TestCase):
    def test_registers_from_short_link(self):
        product = register("organizador de cabos", SHORT_LINK)
        self.assertEqual(product.external_id, "MLB3456789012")
        self.assertEqual(product.affiliate_link, SHORT_LINK)
        self.assertEqual(product.title, ITEM["title"])
        self.assertEqual(str(product.price), "29.90")
        self.assertEqual(product.image_url, "https://http2.mlstatic.com/D_1.jpg")

    def test_explicit_item_id_replaces_link_resolution(self):
        product = register("organizador de cabos", SHORT_LINK, item_id="MLB-3456789012", short_target="https://www.mercadolivre.com.br/social/x")
        self.assertEqual(product.external_id, "MLB3456789012")

    def test_unresolvable_link_asks_for_the_item_id(self):
        with self.assertRaises(HTTPException) as ctx:
            register("organizador de cabos", SHORT_LINK, short_target="https://www.mercadolivre.com.br/social/x")
        self.assertEqual(ctx.exception.status_code, 422)

    def test_rejects_link_that_points_to_another_product(self):
        with self.assertRaises(HTTPException) as ctx:
            register("fone bluetooth", SHORT_LINK)
        self.assertEqual(ctx.exception.status_code, 422)

    def test_rejects_long_link_whose_id_differs_from_given_id(self):
        with self.assertRaises(HTTPException) as ctx:
            register("organizador de cabos", LISTING, item_id="MLB19876543")
        self.assertEqual(ctx.exception.status_code, 422)

    def test_rejects_unavailable_listing(self):
        with self.assertRaises(HTTPException) as ctx:
            register("organizador de cabos", SHORT_LINK, item=dict(ITEM, status="paused"))
        self.assertEqual(ctx.exception.status_code, 422)

    def test_marketplace_failure_is_a_bad_gateway(self):
        with self.assertRaises(HTTPException) as ctx:
            register("organizador de cabos", SHORT_LINK, item_status=500)
        self.assertEqual(ctx.exception.status_code, 502)

    def test_rejects_foreign_affiliate_link(self):
        with self.assertRaises(HTTPException) as ctx:
            register("organizador de cabos", "https://evil.test/MLB-3456789012")
        self.assertEqual(ctx.exception.status_code, 422)

    def test_registers_catalog_product_from_product_code(self):
        catalog = {
            "id": "MLB24447228",
            "name": "Chaleira De Vidro 1200ml Com Infusor",
            "status": "active",
            "pictures": [{"url": "https://http2.mlstatic.com/D_1.jpg"}],
            "results": [{"item_id": "MLB3714053599", "price": 38.98, "condition": "new", "category_id": "MLB107481"}],
        }
        product = register(
            "Chaleira de vidro 1200ml com infusor", SHORT_LINK, item_id="MLB24447228",
            catalog=catalog, catalog_status=200,
        )
        self.assertEqual(product.external_id, "MLB24447228")
        self.assertEqual(str(product.price), "38.98")
        self.assertEqual(product.permalink, "https://www.mercadolivre.com.br/p/MLB24447228")
        self.assertEqual(product.affiliate_link, SHORT_LINK)

    def test_catalog_product_without_listing_is_rejected(self):
        catalog = {"id": "MLB24447228", "name": "Chaleira De Vidro", "status": "active", "pictures": [], "results": []}
        with self.assertRaises(HTTPException) as ctx:
            register("chaleira de vidro", SHORT_LINK, item_id="MLB24447228", catalog=catalog, catalog_status=200)
        self.assertEqual(ctx.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
