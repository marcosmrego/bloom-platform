import unittest
from unittest.mock import Mock

from main import slugify, unique_post_slug


class SlugifyTests(unittest.TestCase):
    def test_normalizes_accents_and_reserved_punctuation(self):
        self.assertEqual(
            slugify("Histórias: sabores / Café?"),
            "historias-sabores-cafe",
        )

    def test_collapses_separators(self):
        self.assertEqual(slugify("  A---B ___ C  "), "a-b-c")

    def test_rejects_empty_result(self):
        with self.assertRaises(ValueError):
            slugify("?! 💥")

    def test_limits_length_without_trailing_separator(self):
        result = slugify("a" * 99 + " b", max_length=100)
        self.assertEqual(len(result), 99)
        self.assertFalse(result.endswith("-"))


class UniquePostSlugTests(unittest.TestCase):
    def test_adds_incrementing_suffix_within_tenant(self):
        cursor = Mock()
        cursor.fetchone.side_effect = [(1,), (1,), None]

        result = unique_post_slug(cursor, 7, "Café: especial")

        self.assertEqual(result, "cafe-especial-3")
        self.assertEqual(cursor.execute.call_count, 3)
        cursor.execute.assert_any_call(
            "SELECT 1 FROM posts WHERE tenant_id = %s AND slug = %s",
            (7, "cafe-especial"),
        )


if __name__ == "__main__":
    unittest.main()
