import os


def get_db_config():
    password = os.getenv("DB_PASSWORD")
    if not password:
        raise RuntimeError("DB_PASSWORD must be set")
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "dbname": os.getenv("DB_NAME", "bloom"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": password,
    }


def get_tenant_id(cur, slug="viralbarato"):
    cur.execute("SELECT id FROM tenants WHERE slug = %s", (slug,))
    tenant = cur.fetchone()
    if not tenant:
        raise RuntimeError(f"Tenant not found: {slug}")
    return tenant[0]
