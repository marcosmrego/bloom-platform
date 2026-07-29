# Hermes: automação editorial diária

## Decisão

O Hermes roda como um worker independente na VPS. Ele não recebe acesso para
executar SQL editorial livre. A publicação acontece por um comando/API
restrito, depois de um pacote estruturado passar por validações bloqueantes.

O agendamento dispara uma execução, não “um post”. Cada execução tem identidade
única, estado, tentativas, evidências e resultado. Isso torna o processo
idempotente e auditável.

## Cadência inicial

- Uma execução diária, alternando os tenants.
- Começar em `draft_only=true` por sete dias.
- Após a calibração, habilitar autopublicação por tenant.
- Limite: no máximo um post publicado por tenant em 24 horas.
- Jitter de alguns minutos para evitar colisão com backups e deploys.

## Estados do job

`queued -> researching -> drafting -> validating -> ready -> published`

Saídas alternativas:

- `rejected`: falhou em um gate editorial.
- `failed`: erro técnico após retries limitados.
- `needs_review`: ambiguidade de produto, fonte ou política.

## Pacote produzido pelo Hermes

Antes de publicar, o Hermes grava um JSON com:

- tenant e pauta;
- título, slug, excerpt e conteúdo Markdown;
- categoria, tags, SEO title e SEO description;
- fontes consultadas, data da consulta e afirmações sustentadas;
- produto/ASIN somente quando houver correspondência exata;
- prompt e metadados da imagem;
- fingerprints de título, pauta e conteúdo;
- versão do prompt, modelo, custo e duração.

## Gates bloqueantes

1. Tenant permitido e categoria pertencente ao tenant.
2. Slug normalizado e ainda não utilizado.
3. Similaridade contra posts publicados e arquivados abaixo do limite.
4. Conteúdo mínimo, estrutura mínima e ausência de texto de teste.
5. Nenhuma alegação de uso próprio sem evidência.
6. Preço nunca tratado como permanente.
7. ASIN validado no destino real; divergência remove o botão e exige revisão.
8. Imagem WebP local, exclusiva e servida com HTTP 200.
9. SEO title, description, canonical e dados estruturados válidos.
10. Publicação atômica: post, asset e log concluem juntos ou nada é publicado.

## Componentes recomendados

- `hermes-worker`: processo Python na VPS.
- `hermes schedule`: entrada executada pelo cron/Coolify Scheduled Task.
- `content_jobs`: estado e idempotência.
- `content_topics`: histórico de pautas e fingerprints.
- `content_sources`: fontes e data de verificação.
- `content_artifacts`: pacote JSON, validações e caminho da imagem.
- endpoint interno de publicação autenticado com token de escopo limitado.
- alerta por webhook quando houver `failed`, `needs_review` ou ausência de job.

## Segurança operacional

- Usuário PostgreSQL próprio para o Hermes; nunca `postgres`.
- Secrets somente em variáveis runtime do worker.
- Sem porta pública para o worker.
- Egress permitido apenas para API Bloom, provedor de IA, fontes HTTP e
  armazenamento necessário.
- Timeout por etapa, retries com backoff e orçamento diário de tokens/custo.
- Logs sem tokens, senhas, cookies ou conteúdo integral de respostas privadas.

## Implantação em fases

1. Criar tabelas de controle e usuário restrito.
2. Implementar worker, schemas e gates determinísticos.
3. Executar sete dias em modo rascunho.
4. Revisar falsos positivos, qualidade e custo.
5. Ativar publicação automática para um tenant.
6. Depois de mais sete dias estáveis, habilitar o segundo tenant.

