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


SOCIAL_TARGET = "https://www.mercadolivre.com.br/social/afiliado?matt_word=afiliado"


def social_page(title, *product_ids):
    ids = "".join(f'"product_id":"{pid}",' for pid in product_ids)
    return f'<html><head><meta property="og:title" content="{title}"/></head><body>{{{ids}}}</body></html>'


def register(name, link, item=ITEM, item_status=200, item_id=None, short_target=LISTING, catalog=None, catalog_status=404, social_body=""):
    def handler(request):
        url = str(request.url)
        if request.url.host == "meli.la":
            return httpx.Response(302, headers={"location": short_target})
        if request.url.path.startswith("/social/"):
            return httpx.Response(200, text=social_body)
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


CATALOG = {
    "id": "MLB24117280",
    "name": "Fone De Ouvido Headphone Dapon H02D Bluetooth 5.1 Over-ear 22h Preto",
    "status": "active",
    "pictures": [{"url": "https://http2.mlstatic.com/D_2.jpg"}],
    "results": [{"item_id": "MLB3714053599", "price": 76.53, "condition": "new", "category_id": "MLB1000"}],
}


class RegisterFromSocialPageTests(unittest.TestCase):
    def register_social(self, name=None, body=None, **extra):
        page = body if body is not None else social_page(
            "Fone De Ouvido Headphone Dapon H02D Bluetooth 5.1 Over-ear 22h Preto - R$ 76,53",
            "MLB24117280", "MLB76575845",
        )
        return register(
            name, SHORT_LINK, short_target=SOCIAL_TARGET, social_body=page,
            catalog=CATALOG, catalog_status=200, **extra,
        )

    def test_registers_from_the_link_alone(self):
        product = self.register_social()
        self.assertEqual(product.external_id, "MLB24117280")
        self.assertEqual(product.title, CATALOG["name"])
        self.assertEqual(product.affiliate_link, SHORT_LINK)

    def test_uses_the_first_product_not_the_recommended_ones(self):
        self.assertEqual(self.register_social().external_id, "MLB24117280")

    def test_given_name_is_still_checked_against_the_listing(self):
        product = self.register_social(name="fone dapon h02d bluetooth")
        self.assertEqual(product.external_id, "MLB24117280")
        with self.assertRaises(HTTPException) as ctx:
            self.register_social(name="liquidificador mondial")
        self.assertEqual(ctx.exception.status_code, 422)

    def test_rejects_page_whose_title_disagrees_with_the_listing(self):
        body = social_page("Liquidificador Mondial 800W Preto - R$ 99,00", "MLB24117280")
        with self.assertRaises(HTTPException) as ctx:
            self.register_social(body=body)
        self.assertEqual(ctx.exception.status_code, 422)

    def test_page_without_a_product_asks_for_the_item_id(self):
        with self.assertRaises(HTTPException) as ctx:
            self.register_social(body="<html>nada</html>")
        self.assertEqual(ctx.exception.status_code, 422)

    def test_page_without_a_title_needs_the_name(self):
        body = social_page("", "MLB24117280")
        with self.assertRaises(HTTPException) as ctx:
            self.register_social(body=body)
        self.assertEqual(ctx.exception.status_code, 422)
        product = self.register_social(name="fone dapon h02d", body=body)
        self.assertEqual(product.external_id, "MLB24117280")

    def test_title_is_read_whatever_the_attribute_order_or_quotes(self):
        body = "<meta content='Fone Dapon H02D Bluetooth - R$ 76,53' property='og:title'>" + '{"product_id":"MLB24117280"}'
        self.assertEqual(self.register_social(body=body).external_id, "MLB24117280")

    def test_html_entities_in_the_title_are_decoded(self):
        body = social_page("Fone Dapon &amp; H02D Bluetooth", "MLB24117280")
        self.assertEqual(self.register_social(body=body).external_id, "MLB24117280")

    def test_oversized_page_is_not_read(self):
        padding = "x" * (3 * 1024 * 1024)
        body = social_page("Fone Dapon H02D", "MLB24117280") + padding
        with self.assertRaises(HTTPException) as ctx:
            self.register_social(body=body)
        self.assertEqual(ctx.exception.status_code, 422)

    def test_link_with_explicit_port_is_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            register(None, "https://meli.la:8443/2AbCdEf", short_target=SOCIAL_TARGET)
        self.assertEqual(ctx.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
