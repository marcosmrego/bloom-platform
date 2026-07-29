#!/usr/bin/env python3
import argparse
import hashlib
from urllib.parse import quote

import psycopg2

from db_config import get_db_config


IMAGE_BASE = "https://image.pollinations.ai/prompt/"


def build_image_url(tenant_slug: str, post_id: int, title: str, category_slug: str | None) -> str:
    if tenant_slug == "mundonoprato":
        return f"/images/posts/mundonoprato/post-{post_id}.webp"

    if tenant_slug == "viralbarato":
        prompt = (
            f"professional ecommerce product photography, {title}, "
            "single product, clean neutral background, realistic, no text, no logo"
        )
    seed_source = f"{tenant_slug}:{post_id}:{title}".encode("utf-8")
    seed = int(hashlib.sha256(seed_source).hexdigest()[:8], 16)
    return (
        f"{IMAGE_BASE}{quote(prompt, safe='')}"
        f"?width=1200&height=630&nologo=true&seed={seed}"
    )


def find_targets(cur):
    cur.execute(
        """
        SELECT t.slug, p.id, p.title, c.slug, p.image_url
        FROM posts p
        JOIN tenants t ON t.id = p.tenant_id
        LEFT JOIN categories c
          ON c.id = p.category_id AND c.tenant_id = p.tenant_id
        WHERE (
            t.slug = 'viralbarato'
            AND NULLIF(BTRIM(p.image_url), '') IS NULL
        ) OR (
            t.slug = 'mundonoprato'
            AND p.image_url !~ '^/images/posts/mundonoprato/post-[0-9]+[.]webp$'
        )
        ORDER BY t.slug, p.id
        """
    )
    return cur.fetchall()


def main():
    parser = argparse.ArgumentParser(
        description="Backfill missing ViralBarato images and replace duplicated Mundo no Prato images."
    )
    parser.add_argument("--apply", action="store_true", help="Commit updates. Default is dry-run.")
    args = parser.parse_args()

    conn = psycopg2.connect(**get_db_config())
    try:
        with conn.cursor() as cur:
            targets = find_targets(cur)
            for tenant_slug, post_id, title, category_slug, old_url in targets:
                new_url = build_image_url(tenant_slug, post_id, title, category_slug)
                action = "missing" if not old_url else "replace"
                print(f"{tenant_slug} post={post_id} ({action}): {new_url}")
                if args.apply:
                    cur.execute(
                        """
                        UPDATE posts
                        SET image_url = %s, updated_at = NOW()
                        WHERE id = %s
                          AND tenant_id = (SELECT id FROM tenants WHERE slug = %s)
                        """,
                        (new_url, post_id, tenant_slug),
                    )

        if args.apply:
            conn.commit()
            print(f"Applied: {len(targets)} post image(s) updated.")
        else:
            conn.rollback()
            print(f"Dry-run: {len(targets)} post image(s) would change.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
