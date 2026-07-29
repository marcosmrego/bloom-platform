import unittest

from normalize_post_slugs import build_changes


class NormalizePostSlugsTests(unittest.TestCase):
    def test_preserves_canonical_slug_and_resolves_collision(self):
        rows = [
            (1, 1, "mundonoprato", "Histórias: do Café"),
            (2, 1, "mundonoprato", "historias-do-cafe"),
            (3, 2, "viralbarato", "Review: Produto"),
        ]

        self.assertCountEqual(
            build_changes(rows),
            [
                (1, 1, "mundonoprato", "Histórias: do Café", "historias-do-cafe-2"),
                (3, 2, "viralbarato", "Review: Produto", "review-produto"),
            ],
        )

    def test_allows_same_slug_in_different_tenants(self):
        rows = [
            (1, 1, "site-a", "Mesmo: título"),
            (2, 2, "site-b", "Mesmo: título"),
        ]

        self.assertCountEqual(
            build_changes(rows),
            [
                (1, 1, "site-a", "Mesmo: título", "mesmo-titulo"),
                (2, 2, "site-b", "Mesmo: título", "mesmo-titulo"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
