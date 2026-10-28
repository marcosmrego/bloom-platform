"""Apply Bloom multi-marketplace products migration."""

from pathlib import Path

import psycopg2

from db_config import get_db_config


def main() -> None:
    sql = Path(__file__).with_name("migrate_marketplaces.sql").read_text(
        encoding="utf-8"
    )
    conn = psycopg2.connect(**get_db_config())
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FILTER (WHERE marketplace = 'amazon' AND external_id = asin),
                       COUNT(*) FILTER (WHERE external_id IS NULL)
                FROM products
                """
            )
            backfilled, missing = cur.fetchone()
        if missing:
            raise RuntimeError(f"{missing} products without external_id")
        print(f"marketplaces=ready amazon_backfilled={backfilled}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
