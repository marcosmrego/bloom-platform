# BLOOM — Deploy no Coolify
# ========================

# Você precisa de 2 apps no Coolify:

## App 1: bloom-api
## ─────────────────
# - Name: bloom-api
# - Build Pack: Dockerfile
# - Dockerfile path: /api/Dockerfile
# - Port: 8000

# Env vars:
DB_HOST=212.85.22.227
DB_PORT=5432
DB_NAME=bloom
DB_USER=postgres
DB_PASSWORD=sua_senha_do_postgres

## App 2: bloom-frontend
## ─────────────────────
# - Name: bloom-frontend
# - Build Pack: Dockerfile
# - Dockerfile path: /frontend/Dockerfile
# - Port: 3000

# Env vars:
BLOOM_API=http://bloom-api:8000
PORT=3000

## DNS Cloudflare
## ──────────────
# CNAME viralbarato.com.br → (IP do Coolify)
# CNAME mundonoprato.com.br → (IP do Coolify)
