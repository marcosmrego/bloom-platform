import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx

from mercadolivre_client import (
    MarketplaceUnavailable,
    MercadoLivreCredentials,
    MercadoLivreItem,
    MercadoLivreTokenManager,
    fetch_item,
    name_matches_title,
    parse_item,
    resolve_item_id,
)

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
CREDENTIALS = MercadoLivreCredentials(client_id="123", client_secret="shh", redirect_uri="https://x.test/cb")
ITEM_PAYLOAD = {
    "id": "MLB3456789012",
    "title": "Organizador De Cabos Mesa Escritorio",
    "price": 29.9,
    "permalink": "https://produto.mercadolivre.com.br/MLB-3456789012-organizador-de-cabos-_JM",
    "status": "active",
    "available_quantity": 12,
    "category_id": "MLB1648",
    "pictures": [{"secure_url": "https://http2.mlstatic.com/D_1.jpg"}],
}


class MemoryTokenStore:
    def __init__(self, tokens=None):
        self.tokens = tokens
        self.saved = []

    async def load(self):
        return self.tokens

    async def save(self, tokens):
        self.tokens = tokens
        self.saved.append(tokens)


def run(coro):
    return asyncio.run(coro)


def token_manager(store, handler, seed=("seed-access", "seed-refresh")):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return MercadoLivreTokenManager(
        CREDENTIALS, store, client, seed_tokens=seed, now=lambda: NOW
    )


class TokenManagerTests(unittest.TestCase):
    def test_uses_stored_token_while_valid(self):
        from mercadolivre_client import StoredTokens

        store = MemoryTokenStore(StoredTokens("live", "refresh", NOW + timedelta(hours=3)))

        def handler(request):
            raise AssertionError("must not refresh a valid token")

        self.assertEqual(run(token_manager(store, handler).access_token()), "live")

    def test_refreshes_expired_token_and_persists_rotated_refresh_token(self):
        from mercadolivre_client import StoredTokens

        store = MemoryTokenStore(StoredTokens("old", "refresh-1", NOW - timedelta(minutes=1)))
        seen = {}

        def handler(request):
            seen["body"] = dict(httpx.QueryParams(request.content.decode()))
            return httpx.Response(
                200, json={"access_token": "new", "refresh_token": "refresh-2", "expires_in": 21600}
            )

        self.assertEqual(run(token_manager(store, handler).access_token()), "new")
        self.assertEqual(seen["body"]["grant_type"], "refresh_token")
        self.assertEqual(seen["body"]["refresh_token"], "refresh-1")
        self.assertEqual(store.tokens.refresh_token, "refresh-2")
        self.assertEqual(store.tokens.expires_at, NOW + timedelta(seconds=21600))

    def test_bootstraps_from_seed_when_store_is_empty(self):
        store = MemoryTokenStore(None)

        def handler(request):
            return httpx.Response(
                200, json={"access_token": "n", "refresh_token": "r2", "expires_in": 100}
            )

        self.assertEqual(run(token_manager(store, handler).access_token()), "n")
        self.assertEqual(store.tokens.refresh_token, "r2")

    def test_unavailable_without_any_refresh_token(self):
        store = MemoryTokenStore(None)
        with self.assertRaises(MarketplaceUnavailable):
            run(token_manager(store, lambda r: httpx.Response(500), seed=("a", "")).access_token())

    def test_refresh_failure_is_reported_without_leaking_secrets(self):
        from mercadolivre_client import StoredTokens

        store = MemoryTokenStore(StoredTokens("old", "refresh-1", NOW - timedelta(minutes=1)))
        with self.assertRaises(MarketplaceUnavailable) as ctx:
            run(token_manager(store, lambda r: httpx.Response(400, json={"error": "invalid_grant"})).access_token())
        self.assertNotIn("refresh-1", str(ctx.exception))
        self.assertNotIn("shh", str(ctx.exception))


class ParseItemTests(unittest.TestCase):
    def test_parses_active_item(self):
        item = parse_item(ITEM_PAYLOAD)
        self.assertEqual(
            item,
            MercadoLivreItem(
                external_id="MLB3456789012",
                title="Organizador De Cabos Mesa Escritorio",
                price=Decimal("29.90"),
                permalink=ITEM_PAYLOAD["permalink"],
                image_url="https://http2.mlstatic.com/D_1.jpg",
                available=True,
                category_id="MLB1648",
            ),
        )

    def test_paused_or_empty_stock_is_unavailable(self):
        self.assertFalse(parse_item(dict(ITEM_PAYLOAD, status="paused")).available)
        self.assertFalse(parse_item(dict(ITEM_PAYLOAD, available_quantity=0)).available)

    def test_rejects_malformed_payload(self):
        for bad in ({}, dict(ITEM_PAYLOAD, id="MLA1"), dict(ITEM_PAYLOAD, title=""),
                    dict(ITEM_PAYLOAD, permalink="http://evil.test/x")):
            with self.subTest(bad=bad):
                with self.assertRaises(MarketplaceUnavailable):
                    parse_item(bad)

    def test_missing_price_becomes_none(self):
        self.assertIsNone(parse_item(dict(ITEM_PAYLOAD, price=None)).price)


class FetchItemTests(unittest.TestCase):
    def test_sends_bearer_and_parses(self):
        from mercadolivre_client import StoredTokens

        store = MemoryTokenStore(StoredTokens("live", "r", NOW + timedelta(hours=1)))
        seen = {}

        def handler(request):
            seen["auth"] = request.headers["authorization"]
            seen["path"] = request.url.path
            return httpx.Response(200, json=ITEM_PAYLOAD)

        manager = token_manager(store, handler)
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        item = run(fetch_item(client, manager, "MLB3456789012"))
        self.assertEqual(seen["auth"], "Bearer live")
        self.assertEqual(seen["path"], "/items/MLB3456789012")
        self.assertEqual(item.external_id, "MLB3456789012")

    def test_missing_item_is_unavailable(self):
        from mercadolivre_client import StoredTokens

        store = MemoryTokenStore(StoredTokens("live", "r", NOW + timedelta(hours=1)))
        manager = token_manager(store, lambda r: httpx.Response(404))
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(404)))
        with self.assertRaises(MarketplaceUnavailable):
            run(fetch_item(client, manager, "MLB3456789012"))


class ResolveItemIdTests(unittest.TestCase):
    def resolve(self, routes):
        def handler(request):
            return routes[str(request.url)](request)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return run(resolve_item_id(client, "https://meli.la/2AbCdEf"))

    def test_follows_redirects_to_item_url(self):
        routes = {
            "https://meli.la/2AbCdEf": lambda r: httpx.Response(
                302, headers={"location": "https://www.mercadolivre.com.br/social/x?ref=1"}
            ),
            "https://www.mercadolivre.com.br/social/x?ref=1": lambda r: httpx.Response(
                302, headers={"location": "https://produto.mercadolivre.com.br/MLB-3456789012-organizador-_JM"}
            ),
            "https://produto.mercadolivre.com.br/MLB-3456789012-organizador-_JM": lambda r: httpx.Response(200),
        }
        self.assertEqual(self.resolve(routes), "MLB3456789012")

    def test_returns_none_when_no_item_id_is_present(self):
        routes = {
            "https://meli.la/2AbCdEf": lambda r: httpx.Response(200, text="<html>sem item</html>"),
        }
        self.assertIsNone(self.resolve(routes))

    def test_never_follows_redirects_to_foreign_hosts(self):
        calls = []

        def evil(request):
            calls.append(str(request.url))
            return httpx.Response(200)

        routes = {
            "https://meli.la/2AbCdEf": lambda r: httpx.Response(302, headers={"location": "https://evil.test/MLB-3456789012"}),
            "https://evil.test/MLB-3456789012": evil,
        }
        self.assertIsNone(self.resolve(routes))
        self.assertEqual(calls, [])

    def test_stops_after_too_many_redirects(self):
        routes = {
            "https://meli.la/2AbCdEf": lambda r: httpx.Response(302, headers={"location": "https://meli.la/2AbCdEf"}),
        }
        self.assertIsNone(self.resolve(routes))


class NameMatchTests(unittest.TestCase):
    def test_accepts_overlapping_names_ignoring_accents_and_case(self):
        self.assertTrue(name_matches_title("organizador de cabos", "Organizador De Cabos Mesa Escritório"))

    def test_rejects_unrelated_names(self):
        self.assertFalse(name_matches_title("fone bluetooth", "Organizador De Cabos Mesa Escritorio"))


if __name__ == "__main__":
    unittest.main()
