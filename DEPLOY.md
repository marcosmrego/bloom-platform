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
DB_HOST=hostname-interno-do-postgres
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

# Monetização (valores distintos por instância quando aplicável)
ADSENSE_CLIENT_ID=ca-pub-SEU_ID
ADCASH_HEAD_CODE=tag_exata_fornecida_pelo_painel
ADCASH_BODY_CODE=tag_ou_slot_opcional_fornecido_pelo_painel
ADS_TXT_EXTRA=linhas_ads_txt_fornecidas_pelas_redes

# Escolha um modo:
# - Instância multi-domínio: não defina BLOOM_TENANT; o hostname seleciona o site.
# - Instância dedicada: defina BLOOM_TENANT=viralbarato ou BLOOM_TENANT=mundonoprato.
#
# Nunca publique a mesma instância para os dois domínios com BLOOM_TENANT definido.
#
# Depois de configurar o AdSense:
# - Ative Auto ads no painel.
# - Publique a mensagem de consentimento em Privacy & messaging.
# - Valide /ads.txt em cada domínio.

## Ordem de migração de uma instalação existente
## ───────────────────────────────────────────────────
# 1. Faça backup do PostgreSQL.
# 2. Execute scripts/migrate_tenant_integrity.sql.
#    A transação aborta se encontrar referências entre tenants.
# 3. Simule a normalização:
#    python scripts/normalize_post_slugs.py
# 4. Revise a saída e aplique:
#    python scripts/normalize_post_slugs.py --apply
# 5. Faça o deploy da API e do frontend.
# 6. Rotacione qualquer credencial que já tenha sido versionada.
#
# Scripts de migração/importação também exigem BLOOM_API explícito.

## DNS Cloudflare
## ──────────────
# CNAME viralbarato.com.br → (IP do Coolify)
# CNAME mundonoprato.com.br → (IP do Coolify)
