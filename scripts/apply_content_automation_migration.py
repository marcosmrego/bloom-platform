"""Apply the additive Bloom content automation migration."""

from pathlib import Path

import psycopg2

from db_config import get_db_config


def main() -> None:
    sql_path = Path(__file__).with_name("migrate_content_automation.sql")
    sql = sql_path.read_text(encoding="utf-8")
    conn = psycopg2.connect(**get_db_config())
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.content_jobs')")
            table_name = cur.fetchone()[0]
        if table_name != "content_jobs":
            raise RuntimeError("content_jobs was not created")
        print("content_jobs=ready")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
