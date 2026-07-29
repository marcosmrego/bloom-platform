# Bloom Platform — retomada de produção

## Baseline observado

Consulta pública realizada em 28/07/2026:

- `https://mundonoprato.com.br/`: HTTP 200 e marca Mundo no Prato.
- `https://mundonoprato.com.br/categoria/historias`: HTTP 200, mas ainda contém
  `ViralBarato` e `reviews`.
- `https://viralbarato.com.br/`: HTTP 200 e marca ViralBarato.
- API pública atual responde em HTTP, mas apresenta erro de confiança TLS no HTTPS.
- Mundo no Prato: 16 posts publicados e 16 slugs fora do formato canônico.
- ViralBarato: 30 posts publicados e 30 slugs fora do formato canônico.
- ViralBarato: os 30 posts não possuem `post.image_url` nem `product_image`.
- Mundo no Prato: quatro URLs editoriais são reutilizadas, afetando 13 posts.

## Ordem segura

1. Obter acesso administrativo explícito ao PostgreSQL/Coolify.
2. Rotacionar a senha PostgreSQL que esteve versionada e atualizar os secrets.
3. Fazer backup verificável com `pg_dump` antes de qualquer migração.
4. Executar `scripts/audit_content.sql` e guardar a saída.
5. Corrigir manualmente qualquer referência cruzada encontrada.
6. Executar `scripts/migrate_tenant_integrity.sql`.
7. Executar `python scripts/normalize_post_slugs.py` sem `--apply`.
8. Revisar o plano e executar novamente com `--apply`.
9. Corrigir/backfill das imagens repetidas ou ausentes.
10. Publicar API e frontend.
11. Validar home, categorias, artigos, aliases 301, imagens e isolamento nos dois domínios.
12. Corrigir o certificado/rota HTTPS da API e desativar o endpoint HTTP público quando possível.

## Evidência mínima pós-deploy

- `/categoria/historias` contém Mundo no Prato e `artigos`, sem ViralBarato/reviews.
- Todos os slugs publicados seguem `^[a-z0-9]+(?:-[a-z0-9]+)*$`.
- URLs antigas retornam 301 para o slug canônico.
- Nenhuma relação de categoria, produto, usuário ou click cruza tenants.
- Artigos distintos não usam imagens genéricas repetidas sem decisão editorial.
- `mundonoprato.com.br` nunca retorna dados/branding do ViralBarato e vice-versa.
