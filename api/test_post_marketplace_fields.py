import unittest

from pydantic import ValidationError

from main import PostCreate

BASE = {
    "tenant_slug": "viralbarato",
    "title": "Organizador de cabos para mesa",
    "content": "conteúdo",
}


class PostCreateMarketplaceFieldsTests(unittest.TestCase):
    def test_accepts_a_mercadolivre_item_id(self):
        post = PostCreate(**BASE, product_external_id="MLB-3456789012")
        self.assertEqual(post.product_external_id, "MLB3456789012")

    def test_asin_and_item_id_are_mutually_exclusive(self):
        with self.assertRaises(ValidationError):
            PostCreate(**BASE, product_asin="B0ABCDE123", product_external_id="MLB3456789012")

    def test_rejects_malformed_item_id(self):
        for value in ("B0ABCDE123", "MLB12", "MLA3456789012", "MLB-abc"):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    PostCreate(**BASE, product_external_id=value)

    def test_item_id_changes_the_request_hash(self):
        from main import post_request_hash

        plain = PostCreate(**BASE)
        linked = PostCreate(**BASE, product_external_id="MLB3456789012")
        self.assertNotEqual(post_request_hash(plain), post_request_hash(linked))


if __name__ == "__main__":
    unittest.main()
