import unittest

from fastapi import HTTPException

from marketplaces import (
    normalize_mercadolivre_id,
    validate_mercadolivre_destination,
)

SHORT_LINK = "https://meli.la/2AbCdEf"
LISTING_URL = "https://produto.mercadolivre.com.br/MLB-3456789012-organizador-de-cabos-_JM"
CATALOG_URL = "https://www.mercadolivre.com.br/organizador-de-cabos/p/MLB19876543"


class NormalizeMercadoLivreIdTests(unittest.TestCase):
    def test_accepts_dashed_and_plain_forms(self):
        self.assertEqual(normalize_mercadolivre_id("MLB-3456789012"), "MLB3456789012")
        self.assertEqual(normalize_mercadolivre_id(" mlb3456789012 "), "MLB3456789012")

    def test_rejects_other_shapes(self):
        for value in ("", None, "B0ABCDE123", "MLA123456789", "MLB12", "MLB-abc"):
            with self.subTest(value=value):
                with self.assertRaises(HTTPException):
                    normalize_mercadolivre_id(value)


class MercadoLivreDestinationTests(unittest.TestCase):
    def test_accepts_short_affiliate_link_for_product(self):
        self.assertEqual(
            validate_mercadolivre_destination("product", SHORT_LINK, "MLB3456789012"),
            SHORT_LINK,
        )

    def test_accepts_listing_and_catalog_urls_with_matching_id(self):
        self.assertEqual(
            validate_mercadolivre_destination("product", LISTING_URL, "MLB3456789012"),
            LISTING_URL,
        )
        self.assertEqual(
            validate_mercadolivre_destination("product", CATALOG_URL, "MLB-19876543"),
            CATALOG_URL,
        )

    def test_rejects_id_that_differs_from_url(self):
        with self.assertRaises(HTTPException):
            validate_mercadolivre_destination("product", LISTING_URL, "MLB19876543")

    def test_rejects_untrusted_hosts_and_schemes(self):
        invalid = (
            "http://meli.la/2AbCdEf",
            "https://evilmercadolivre.com.br/MLB-3456789012",
            "https://mercadolivre.com.br.evil.com/MLB-3456789012",
            "https://mercadolivre.com.br@evil.com/MLB-3456789012",
            "https://meli.la:8443/2AbCdEf",
            "https://www.amazon.com.br/dp/B0ABCDE123?tag=marcosmrego-20",
            "",
        )
        for url in invalid:
            with self.subTest(url=url):
                with self.assertRaises(HTTPException):
                    validate_mercadolivre_destination("product", url, "MLB3456789012")

    def test_product_requires_valid_id(self):
        with self.assertRaises(HTTPException):
            validate_mercadolivre_destination("product", SHORT_LINK, None)

    def test_only_product_links_are_supported(self):
        for link_type in ("search", "offer", "other"):
            with self.subTest(link_type=link_type):
                with self.assertRaises(HTTPException):
                    validate_mercadolivre_destination(link_type, SHORT_LINK, "MLB3456789012")

    def test_no_match_cannot_smuggle_destination(self):
        self.assertIsNone(validate_mercadolivre_destination("no_match", None, None))
        with self.assertRaises(HTTPException):
            validate_mercadolivre_destination("no_match", SHORT_LINK, None)


if __name__ == "__main__":
    unittest.main()
