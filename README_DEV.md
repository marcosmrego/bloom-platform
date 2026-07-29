# Desenvolvimento local — BLOOM

Passos rápidos para levantar um ambiente local reproducível usando Docker Compose.

1) Copie `.env.example` para `.env` e ajuste `DB_PASSWORD`:

```powershell
cp .env.example .env
# edite .env e defina DB_PASSWORD
```

2) Subir os containers (build + serviços locais incluindo Postgres):

```powershell
docker compose up --build
```

3) Acessos úteis:
- Frontend: http://localhost:3001  (map: 3001:3000 no compose)
- API: http://localhost:8001       (map: 8001:8000 no compose)

4) Seed de dados (executar dentro do container `bloom-api` após o DB ficar pronto):

```powershell
docker compose exec bloom-api python seed.py
```

5) Criar um novo tenant localmente (opcional):

```powershell
docker compose exec bloom-api python create_blog.py --name "TenisBarato" --slug tenisbarato --domain tenisbarato.local --niche "reviews"
```

Notas rápidas:
- Este repositório já inclui `docker-compose.yml`. O arquivo `docker-compose.override.yml` adiciona um serviço Postgres para desenvolvimento local e atualiza as variáveis de ambiente do `bloom-api` para apontar para ele.
- Se você preferir rodar serviços sem Docker, veja `api/requirements.txt` e `frontend/package.json` e execute `uvicorn` / `npm run dev` manualmente.
