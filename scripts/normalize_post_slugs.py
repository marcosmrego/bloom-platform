#!/usr/bin/env python3
import argparse
import re
import unicodedata

import psycopg2

from db_config import get_db_config

MAX_LENGTH = 100


def slugify(value):
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    slug = slug[:MAX_LENGTH].rstrip("-")
    if not slug:
        raise ValueError(f"Cannot normalize slug: {value!r}")
    return slug


def build_changes(rows):
    used = set()
    changes = []
    # Preserve already-canonical slugs before allocating replacements.
    ordered = sorted(rows, key=lambda row: (slugify(row[3]) != row[3], row[0], row[1]))
    for post_id, tenant_id, tenant_slug, old_slug in ordered:
        base = slugify(old_slug)
        candidate = base
        suffix = 2
        while (tenant_id, candidate) in used:
            suffix_text = f"-{suffix}"
            candidate = f"{base[:MAX_LENGTH - len(suffix_text)].rstrip('-')}{suffix_text}"
            suffix += 1
        used.add((tenant_id, candidate))
        if candidate != old_slug:
            changes.append((post_id, tenant_id, tenant_slug, old_slug, candidate))
    return changes


def main():
    parser = argparse.ArgumentParser(description="Normalize post slugs and preserve old aliases.")
    parser.add_argument("--apply", action="store_true", help="Commit changes. Default is dry-run.")
    args = parser.parse_args()

    conn = psycopg2.connect(**get_db_config())
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT p.id, p.tenant_id, t.slug, p.slug
            FROM posts p
            JOIN tenants t ON t.id = p.tenant_id
            ORDER BY p.tenant_id, p.id
        """)
        changes = build_changes(cur.fetchall())

        for _, _, tenant_slug, old_slug, new_slug in changes:
            print(f"{tenant_slug}: {old_slug!r} -> {new_slug!r}")

        if not args.apply:
            conn.rollback()
            print(f"Dry-run: {len(changes)} slug(s) would change.")
            return

        for post_id, tenant_id, _, old_slug, new_slug in changes:
            cur.execute(
                """
                INSERT INTO post_slug_redirects (tenant_id, old_slug, post_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (tenant_id, old_slug)
                DO UPDATE SET post_id = EXCLUDED.post_id
                """,
                (tenant_id, old_slug, post_id),
            )
            cur.execute(
                "UPDATE posts SET slug = %s, updated_at = NOW() WHERE id = %s AND tenant_id = %s",
                (new_slug, post_id, tenant_id),
            )
        conn.commit()
        print(f"Applied: {len(changes)} slug(s) changed.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
