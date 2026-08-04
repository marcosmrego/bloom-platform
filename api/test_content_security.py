import unittest
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from io import BytesIO
from unittest.mock import patch

from fastapi import HTTPException
from PIL import Image

import main
from main import (
    analytics_host,
    analytics_session_hash,
    clean_analytics_value,
    PostCreate,
    SourceEvidence,
    editorial_similarity,
    find_similar_topic,
    normalize_webp,
    post_request_hash,
    validate_editorial_sources,
    validate_editorial_structure,
    validate_idempotency_key,
    FinancialEntryCreate,
    FinancialImportCreate,
    build_performance_alerts,
)


class AnalyticsValidationTests(unittest.TestCase):
    def test_hashes_valid_session_without_storing_identifier(self):
        value = "550e8400-e29b-41d4-a716-446655440000"
        hashed = analytics_session_hash(value)
        self.assertEqual(len(hashed), 64)
        self.assertNotIn(value, hashed)

    def test_rejects_short_or_unsafe_session(self):
        for value in ("short", "contains spaces and symbols!", ""):
            with self.subTest(value=value):
                with self.assertRaises(HTTPException):
                    analytics_session_hash(value)

    def test_normalizes_attribution_and_hosts(self):
        self.assertEqual(analytics_host("https://TikTok.com/path?q=1"), "tiktok.com")
        self.assertIsNone(analytics_host("not-a-url"))
        self.assertEqual(clean_analytics_value("  social\x00media  "), "socialmedia")


class FinancialImportValidationTests(unittest.TestCase):
    def test_accepts_real_financial_entry(self):
        payload = FinancialImportCreate(
            tenant_slug="viralbarato",
            entries=[FinancialEntryCreate(
                provider="amazon",
                entry_type="revenue",
                occurred_on="2026-08-04",
                amount="12.34",
                external_id="amazon-order-123",
                post_id=58,
            )],
        )
        self.assertEqual(payload.entries[0].currency, "BRL")
        self.assertEqual(str(payload.entries[0].amount), "12.34")

    def test_rejects_negative_amount_or_unknown_provider(self):
        invalid = [
            {"provider": "amazon", "entry_type": "revenue", "amount": "-1"},
            {"provider": "unknown", "entry_type": "revenue", "amount": "1"},
        ]
        for values in invalid:
            with self.subTest(values=values):
                with self.assertRaises(Exception):
                    FinancialEntryCreate(
                        occurred_on="2026-08-04",
                        external_id="valid-id",
                        **values,
                    )


class PerformanceAlertTests(unittest.TestCase):
    def post(self, **overrides):
        values = {
            "post_id": 58,
            "tenant_slug": "viralbarato",
            "title": "Artigo em observação",
            "published_at": datetime(2026, 8, 1, tzinfo=timezone.utc),
            "has_affiliate_link": True,
            "offer_valid_until": None,
            "views": 12,
            "clicks": 0,
            "ctr": 0,
            "revenue": 0,
        }
        values.update(overrides)
        return values

    def test_prioritizes_visits_without_clicks(self):
        alerts = build_performance_alerts(
            [self.post()], False, datetime(2026, 8, 4, tzinfo=timezone.utc)
        )
        self.assertEqual(alerts[0]["code"], "no_clicks")
        self.assertEqual(alerts[0]["priority"], "high")

    def test_flags_expiring_offer_and_missing_affiliate(self):
        now = datetime(2026, 8, 4, tzinfo=timezone.utc)
        alerts = build_performance_alerts(
            [self.post(
                views=1,
                has_affiliate_link=False,
                offer_valid_until=now + timedelta(days=2),
            )],
            False,
            now,
        )
        self.assertEqual({item["code"] for item in alerts}, {"missing_affiliate", "offer_expiring"})

    def test_financial_alert_requires_available_finance_data(self):
        post = self.post(views=20, clicks=4, ctr=20)
        without_finance = build_performance_alerts([post], False)
        with_finance = build_performance_alerts([post], True)
        self.assertNotIn("clicks_without_revenue", {item["code"] for item in without_finance})
        self.assertIn("clicks_without_revenue", {item["code"] for item in with_finance})

    def test_does_not_call_old_posts_trafficless_before_tracking_baseline(self):
        alerts = build_performance_alerts(
            [self.post(views=0)], False, datetime(2026, 8, 4, tzinfo=timezone.utc)
        )
        self.assertNotIn("no_traffic", {item["code"] for item in alerts})

    def test_missing_affiliate_is_commercial_tenant_only(self):
        alerts = build_performance_alerts(
            [self.post(tenant_slug="mundonoprato", has_affiliate_link=False, views=1)],
            False,
            datetime(2026, 8, 4, tzinfo=timezone.utc),
        )
        self.assertNotIn("missing_affiliate", {item["code"] for item in alerts})


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


def source(url, source_type="secondary", evidence=None):
    return SourceEvidence(
        url=url,
        title="Fonte consultada",
        extracted_at="2026-07-30T12:00:00Z",
        evidence=(
            ["Evidência efetivamente extraída da página."]
            if evidence is None
            else evidence
        ),
        source_type=source_type,
    )


class EditorialSourceGateTests(unittest.TestCase):
    def post(self, **overrides):
        values = {
            "tenant_slug": "mundonoprato",
            "title": "Como escolher panelas para o dia a dia",
            "content": "Um guia prático para comparar materiais e tamanhos.",
            "sources": [
                source("https://example.org/guia"),
                source("https://example.net/manual"),
            ],
        }
        values.update(overrides)
        return PostCreate(**values)

    def test_accepts_two_unique_extracted_sources(self):
        result = validate_editorial_sources(self.post())

        self.assertTrue(result["sources_extracted"])
        self.assertEqual(result["unique_source_count"], 2)
        self.assertFalse(result["primary_source_required"])

    def test_rejects_less_than_two_sources(self):
        with self.assertRaises(HTTPException) as raised:
            validate_editorial_sources(
                self.post(sources=[source("https://example.org/guia")])
            )
        self.assertEqual(raised.exception.status_code, 422)

    def test_rejects_duplicate_or_evidenceless_sources(self):
        for sources in (
            [
                source("https://example.org/guia"),
                source("https://example.org/guia"),
            ],
            [
                source("https://example.org/guia", evidence=[""]),
                source("https://example.net/manual"),
            ],
        ):
            with self.subTest(sources=sources):
                with self.assertRaises(HTTPException) as raised:
                    validate_editorial_sources(self.post(sources=sources))
                self.assertEqual(raised.exception.status_code, 422)

    def test_health_content_requires_official_or_primary_source(self):
        health_post = self.post(
            title="Sódio e saúde na alimentação",
            content="Comparação nutricional entre ingredientes.",
        )
        with self.assertRaises(HTTPException) as raised:
            validate_editorial_sources(health_post)
        self.assertIn("official", raised.exception.detail)

        health_post.sources[0] = source(
            "https://www.gov.br/saude/guia", source_type="official"
        )
        result = validate_editorial_sources(health_post)
        self.assertTrue(result["primary_source_required"])
        self.assertTrue(result["primary_source_present"])


class SimilarityGateTests(unittest.TestCase):
    def test_detects_near_duplicate_topic(self):
        candidates = [
            {
                "id": 7,
                "title": "Como escolher a melhor panela de pressão",
                "slug": "escolher-melhor-panela-pressao",
                "status": "published",
            }
        ]
        match = find_similar_topic(
            "Como escolher a melhor panela de pressão para sua cozinha",
            candidates,
        )
        self.assertIsNotNone(match)
        self.assertEqual(match["id"], 7)

    def test_allows_distinct_topic(self):
        match = find_similar_topic(
            "Temperos frescos para cultivar na janela",
            [{"id": 1, "title": "Guia de panelas de ferro", "slug": "panelas"}],
        )
        self.assertIsNone(match)

    def test_similarity_is_accent_insensitive(self):
        scores = editorial_similarity(
            "Alimentação saudável com sódio reduzido",
            "Alimentacao saudavel com sodio reduzido",
        )
        self.assertEqual(scores["jaccard"], 1.0)


class EditorialStructureGateTests(unittest.TestCase):
    def valid_post(self, image_url):
        paragraph = " ".join(
            ["Conteúdo editorial original com informação útil ao leitor."] * 45
        )
        return PostCreate(
            tenant_slug="mundonoprato",
            title="Como organizar os utensílios de uma cozinha pequena",
            excerpt=(
                "Um guia prático para aproveitar melhor o espaço e manter os "
                "utensílios acessíveis no cotidiano."
            ),
            content=f"Introdução prática.\n\n## Planejamento\n\n{paragraph}\n\n## Organização\n\n{paragraph}",
            image_url=image_url,
            category_slug="cozinha",
            seo_title="Como organizar utensílios em cozinhas pequenas",
            seo_description=(
                "Aprenda a organizar utensílios em uma cozinha pequena com "
                "soluções práticas para aproveitar o espaço e facilitar a rotina."
            ),
            sources=[
                source("https://example.org/guia"),
                source("https://example.net/manual"),
            ],
        )

    def test_accepts_complete_structure_and_persisted_webp(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            media_root = Path(temp_dir)
            image = media_root / "mundonoprato" / "article.webp"
            image.parent.mkdir()
            image.write_bytes(b"RIFF-test-WEBP")
            with patch.object(main, "MEDIA_ROOT", media_root):
                result = validate_editorial_structure(
                    self.valid_post("/media/mundonoprato/article.webp"),
                    "mundonoprato",
                )
        self.assertTrue(result["structure_valid"])
        self.assertGreaterEqual(result["word_count"], 180)

    def test_rejects_placeholder_or_missing_image(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            media_root = Path(temp_dir)
            post = self.valid_post("/media/mundonoprato/missing.webp")
            post.content += "\n\nTODO"
            with patch.object(main, "MEDIA_ROOT", media_root):
                with self.assertRaises(HTTPException) as raised:
                    validate_editorial_structure(post, "mundonoprato")
        self.assertEqual(raised.exception.status_code, 422)

    def test_accepts_portuguese_word_todo_as_regular_content(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            media_root = Path(temp_dir)
            image = media_root / "mundonoprato" / "article.webp"
            image.parent.mkdir()
            image.write_bytes(b"RIFF-test-WEBP")
            post = self.valid_post("/media/mundonoprato/article.webp")
            post.content += "\n\nO guia vale para todo o processo de organização."
            with patch.object(main, "MEDIA_ROOT", media_root):
                result = validate_editorial_structure(post, "mundonoprato")
        self.assertTrue(result["placeholders_absent"])


if __name__ == "__main__":
    unittest.main()
