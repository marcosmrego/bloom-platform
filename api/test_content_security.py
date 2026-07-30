import unittest
from io import BytesIO
from unittest.mock import patch

from fastapi import HTTPException
from PIL import Image

import main
from main import (
    PostCreate,
    normalize_webp,
    post_request_hash,
    validate_idempotency_key,
)


class ContentTokenTests(unittest.TestCase):
    def test_accepts_matching_bearer_token(self):
        with patch.object(main, "CONTENT_API_TOKEN", "test-secret"):
            main.require_content_token("Bearer test-secret")

    def test_rejects_missing_or_wrong_token(self):
        with patch.object(main, "CONTENT_API_TOKEN", "test-secret"):
            for value in (None, "", "Basic test-secret", "Bearer wrong"):
                with self.subTest(value=value):
                    with self.assertRaises(HTTPException) as raised:
                        main.require_content_token(value)
                    self.assertEqual(raised.exception.status_code, 401)

    def test_reports_unconfigured_automation_api(self):
        with patch.object(main, "CONTENT_API_TOKEN", ""):
            with self.assertRaises(HTTPException) as raised:
                main.require_content_token("Bearer anything")
            self.assertEqual(raised.exception.status_code, 503)

    def test_review_token_is_separate_from_automation_token(self):
        with (
            patch.object(main, "CONTENT_API_TOKEN", "automation-secret"),
            patch.object(main, "REVIEW_API_TOKEN", "review-secret"),
        ):
            main.require_review_token("Bearer review-secret")
            with self.assertRaises(HTTPException) as raised:
                main.require_review_token("Bearer automation-secret")
            self.assertEqual(raised.exception.status_code, 401)

    def test_reports_unconfigured_review_api(self):
        with patch.object(main, "REVIEW_API_TOKEN", ""):
            with self.assertRaises(HTTPException) as raised:
                main.require_review_token("Bearer anything")
            self.assertEqual(raised.exception.status_code, 503)


class IdempotencyTests(unittest.TestCase):
    def test_accepts_safe_key(self):
        self.assertEqual(
            validate_idempotency_key("bloom:viralbarato:2026-07-30"),
            "bloom:viralbarato:2026-07-30",
        )

    def test_rejects_short_or_unsafe_key(self):
        for value in (None, "", "short", "contains spaces"):
            with self.subTest(value=value):
                with self.assertRaises(HTTPException) as raised:
                    validate_idempotency_key(value)
                self.assertEqual(raised.exception.status_code, 422)

    def test_payload_hash_is_stable_and_sensitive_to_content(self):
        first = PostCreate(
            tenant_slug="viralbarato",
            title="Título",
            content="Conteúdo",
        )
        same = PostCreate(
            content="Conteúdo",
            title="Título",
            tenant_slug="viralbarato",
        )
        changed = PostCreate(
            tenant_slug="viralbarato",
            title="Título",
            content="Outro conteúdo",
        )

        self.assertEqual(post_request_hash(first), post_request_hash(same))
        self.assertNotEqual(post_request_hash(first), post_request_hash(changed))


class MediaNormalizationTests(unittest.TestCase):
    def test_converts_png_to_webp(self):
        source = BytesIO()
        Image.new("RGB", (1200, 630), color=(30, 90, 140)).save(source, "PNG")

        result = normalize_webp(source.getvalue())

        self.assertEqual(result[:4], b"RIFF")
        self.assertEqual(result[8:12], b"WEBP")

    def test_rejects_invalid_or_tiny_images(self):
        with self.assertRaisesRegex(ValueError, "Invalid raster image"):
            normalize_webp(b"not-an-image")

        source = BytesIO()
        Image.new("RGB", (100, 100)).save(source, "PNG")
        with self.assertRaisesRegex(ValueError, "too small"):
            normalize_webp(source.getvalue())


if __name__ == "__main__":
    unittest.main()
