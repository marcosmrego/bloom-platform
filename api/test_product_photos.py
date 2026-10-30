import asyncio
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient
from PIL import Image

import main
from product_photos import MAX_PHOTO_BYTES, ProductPhotoError, fetch_product_photo, is_product_photo_url

PHOTO_URL = "https://http2.mlstatic.com/D_NQ_NP_673950-MLA99394598783_112025-F.jpg"
URL = "/api/v1/viralbarato/editorial/products/MLB24117280/photo"
AUTH = {"Authorization": "Bearer test-secret"}


def jpeg(width=859, height=1200):
    buffer = BytesIO()
    Image.new("RGB", (width, height), (240, 240, 240)).save(buffer, format="JPEG")
    return buffer.getvalue()


def fetch(url=PHOTO_URL, status=200, content_type="image/jpeg", body=None, headers=None):
    payload = jpeg() if body is None else body

    def handler(request):
        return httpx.Response(status, content=payload, headers=headers or {"content-type": content_type})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return asyncio.run(fetch_product_photo(client, url))


class PhotoUrlTests(unittest.TestCase):
    def test_accepts_only_https_mercadolivre_image_hosts(self):
        self.assertTrue(is_product_photo_url(PHOTO_URL))
        self.assertTrue(is_product_photo_url("https://mlstatic.com/a.jpg"))
        for bad in (
            "http://http2.mlstatic.com/a.jpg",
            "https://evilmlstatic.com/a.jpg",
            "https://mlstatic.com.evil.test/a.jpg",
            "https://user@http2.mlstatic.com/a.jpg",
            "https://http2.mlstatic.com:8443/a.jpg",
            "https://127.0.0.1/a.jpg",
            "",
        ):
            self.assertFalse(is_product_photo_url(bad), bad)


class FetchProductPhotoTests(unittest.TestCase):
    def test_returns_the_image_bytes(self):
        self.assertEqual(fetch(body=b"\xff\xd8abc"), b"\xff\xd8abc")

    def test_upgrades_http_cdn_urls_to_https(self):
        seen = []

        def handler(request):
            seen.append(str(request.url))
            return httpx.Response(200, content=b"img", headers={"content-type": "image/jpeg"})

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        asyncio.run(fetch_product_photo(client, "http://http2.mlstatic.com/a.jpg"))
        self.assertEqual(seen, ["https://http2.mlstatic.com/a.jpg"])

    def test_rejects_foreign_hosts_without_a_request(self):
        with self.assertRaises(ProductPhotoError):
            fetch(url="https://evil.test/a.jpg")

    def test_rejects_redirects(self):
        with self.assertRaises(ProductPhotoError):
            fetch(status=302, headers={"location": "https://evil.test/a.jpg"})

    def test_rejects_error_status(self):
        with self.assertRaises(ProductPhotoError):
            fetch(status=404)

    def test_rejects_non_image_content(self):
        with self.assertRaises(ProductPhotoError):
            fetch(content_type="text/html", body=b"<html>")

    def test_rejects_oversized_image(self):
        with self.assertRaises(ProductPhotoError):
            fetch(body=b"x" * (MAX_PHOTO_BYTES + 1))


class ProductPhotoEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        for patcher in (
            patch.object(main, "CONTENT_API_TOKEN", "test-secret"),
            patch.object(main, "MEDIA_ROOT", Path(self.media.name)),
            patch.object(main, "get_mercadolivre_runtime", return_value=main.MercadoLivreRuntime(None, None)),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def post(self, url=URL, photo=PHOTO_URL, fetched=None, headers=AUTH):
        fetch_mock = AsyncMock(return_value=jpeg()) if fetched is None else fetched
        with patch.object(main, "run_db_task", AsyncMock(return_value=photo)), patch.object(
            main, "fetch_product_photo", fetch_mock
        ):
            return self.client.post(url, headers=headers)

    def test_requires_automation_token(self):
        self.assertEqual(self.post(headers={}).status_code, 401)

    def test_only_viralbarato_is_enabled(self):
        self.assertEqual(self.post(url=URL.replace("viralbarato", "mundonoprato")).status_code, 422)

    def test_rejects_invalid_item_ids(self):
        self.assertEqual(self.post(url=URL.replace("MLB24117280", "abc")).status_code, 422)

    def test_unknown_product_is_not_found(self):
        self.assertEqual(self.post(photo=None).status_code, 404)

    def test_stores_the_photo_as_webp_under_the_product_folder(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertRegex(body["image_url"], r"^/media/viralbarato/product/[0-9a-f]{64}\.webp$")
        stored = Path(self.media.name) / body["image_url"].removeprefix("/media/")
        self.assertTrue(stored.is_file())
        with Image.open(stored) as image:
            self.assertEqual(image.format, "WEBP")
            self.assertEqual(image.size, (859, 1200))
        self.assertEqual(body["credit"], "Mercado Livre")

    def test_same_photo_is_stored_once(self):
        first = self.post().json()["image_url"]
        self.assertEqual(self.post().json()["image_url"], first)

    def test_marketplace_failure_is_a_bad_gateway(self):
        failing = AsyncMock(side_effect=ProductPhotoError("boom"))
        self.assertEqual(self.post(fetched=failing).status_code, 502)

    def test_small_square_listing_photo_is_accepted(self):
        response = self.post(fetched=AsyncMock(return_value=jpeg(500, 500)))
        self.assertEqual(response.status_code, 200)

    def test_works_without_marketplace_credentials(self):
        with patch.object(main, "get_mercadolivre_runtime", side_effect=AssertionError("must not be used")):
            self.assertEqual(self.post().status_code, 200)

    def test_unusable_image_is_rejected(self):
        self.assertEqual(self.post(fetched=AsyncMock(return_value=jpeg(100, 100))).status_code, 422)


class MediaUploadRegressionTests(unittest.TestCase):
    def test_upload_keeps_its_response_shape_and_path(self):
        client = TestClient(main.app)
        with tempfile.TemporaryDirectory() as media, patch.object(main, "CONTENT_API_TOKEN", "test-secret"), patch.object(
            main, "MEDIA_ROOT", Path(media)
        ), patch.object(main, "run_db_task", AsyncMock(return_value=True)):
            response = client.post(
                "/api/v1/viralbarato/media", headers=AUTH, files={"image": ("a.jpg", jpeg(800, 600), "image/jpeg")}
            )
            body = response.json()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(set(body), {"status", "sha256", "image_url", "bytes"})
            self.assertRegex(body["image_url"], r"^/media/viralbarato/[0-9a-f]{64}\.webp$")
            self.assertTrue((Path(media) / body["image_url"].removeprefix("/media/")).is_file())

    def test_persist_rejects_unsafe_folder_names(self):
        for bad in ("../x", "a/b", ""):
            if bad:
                with self.assertRaises(ValueError):
                    main.persist_webp("viralbarato", b"x", subdir=bad)


if __name__ == "__main__":
    unittest.main()
