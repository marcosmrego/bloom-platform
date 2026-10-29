"""Apply Bloom product draft request queue migration."""

from pathlib import Path

import psycopg2

from db_config import get_db_config


def main() -> None:
    sql = Path(__file__).with_name("migrate_product_draft_requests.sql").read_text(
        encoding="utf-8"
    )
    conn = psycopg2.connect(**get_db_config())
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM product_draft_requests")
            (total,) = cur.fetchone()
        print(f"product_draft_requests=ready rows={total}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
