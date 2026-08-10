"""Apply the additive all-public-pages analytics migration."""

from pathlib import Path

import psycopg2

from db_config import get_db_config


def main() -> None:
    sql_path = Path(__file__).with_name("migrate_site_analytics.sql")
    conn = psycopg2.connect(**get_db_config())
    try:
        with conn.cursor() as cur:
            cur.execute(sql_path.read_text(encoding="utf-8"))
        conn.commit()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'page_views'
                  AND column_name = 'post_id'
                """
            )
            nullable = cur.fetchone()[0]
        if nullable != "YES":
            raise RuntimeError("page_views.post_id is not nullable")
        print("site_analytics=ready")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
