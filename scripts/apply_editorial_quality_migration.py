"""Apply the additive Bloom editorial quality migration."""

from pathlib import Path

import psycopg2

from db_config import get_db_config


def main() -> None:
    sql_path = Path(__file__).with_name("migrate_editorial_quality.sql")
    sql = sql_path.read_text(encoding="utf-8")
    conn = psycopg2.connect(**get_db_config())
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'posts'
                  AND column_name IN ('source_evidence', 'quality_gates')
                ORDER BY column_name
                """
            )
            columns = [row[0] for row in cur.fetchall()]
        if columns != ["quality_gates", "source_evidence"]:
            raise RuntimeError("Editorial quality columns were not created")
        print("editorial_quality=ready")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
