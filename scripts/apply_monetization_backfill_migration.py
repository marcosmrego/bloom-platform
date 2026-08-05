"""Apply the additive monetization proposal workflow migration."""

from pathlib import Path

import psycopg2

from db_config import get_db_config


def main() -> None:
    sql_path = Path(__file__).with_name("migrate_monetization_backfill.sql")
    conn = psycopg2.connect(**get_db_config())
    try:
        with conn.cursor() as cur:
            cur.execute(sql_path.read_text(encoding="utf-8"))
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.monetization_proposals')")
            table_name = cur.fetchone()[0]
        if table_name != "monetization_proposals":
            raise RuntimeError("monetization_proposals was not created")
        print("monetization_proposals=ready")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
