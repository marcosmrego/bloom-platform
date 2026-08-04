"""Apply Bloom structured commerce and seasonality migration."""

from pathlib import Path

import psycopg2

from db_config import get_db_config


def main() -> None:
    sql = Path(__file__).with_name("migrate_commerce_seasonality.sql").read_text(
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
                SELECT to_regclass('public.post_commerce'),
                       to_regclass('public.seasonal_events'),
                       to_regclass('public.seasonal_product_targets')
                """
            )
            tables = cur.fetchone()
        if tables != (
            "post_commerce",
            "seasonal_events",
            "seasonal_product_targets",
        ):
            raise RuntimeError(f"commerce/seasonality tables not ready: {tables}")
        print("commerce_seasonality=ready")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
