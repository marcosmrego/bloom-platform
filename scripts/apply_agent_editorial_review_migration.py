"""Apply the additive first-pass agent editorial review migration."""

from pathlib import Path

import psycopg2

from db_config import get_db_config


def main() -> None:
    sql_path = Path(__file__).with_name("migrate_agent_editorial_reviews.sql")
    conn = psycopg2.connect(**get_db_config())
    try:
        with conn.cursor() as cur:
            cur.execute(sql_path.read_text(encoding="utf-8"))
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.agent_editorial_reviews')")
            table_name = cur.fetchone()[0]
        if table_name != "agent_editorial_reviews":
            raise RuntimeError("agent_editorial_reviews was not created")
        print("agent_editorial_reviews=ready")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
