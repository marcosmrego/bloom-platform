---
name: bloom-daily-ops
description: Orquestra a rotina diária segura do Bloom, delegando revisão editorial e auditoria operacional às skills competentes, sem aprovar, editar ou publicar conteúdo.
---

# Bloom Daily Ops

Execute uma rotina sequencial, idempotente e limitada. Atue como orquestrador:
delegue cada etapa à skill indicada e consolide o resultado. Uma falha em uma
etapa não autoriza atalhos nas demais.

## Etapa 1 — revisão editorial (`bloom-reviewer`)

1. Execute integralmente o fluxo da skill `bloom-reviewer`.
2. Consulte os dois tenants e revise no máximo um draft por tenant.
3. Envie apenas parecer estruturado. Não edite, aprove, rejeite, arquive nem
   publique.
4. Registre backlog vazio como resultado normal.

## Etapa 2 — auditoria de desempenho (`bloom-operations`)

1. Chame `bloom_performance_metrics` com `days=7`, sem filtro de tenant.
2. Classifique os dados conforme a disciplina de evidência da skill
   `bloom-operations`.
3. Relate resumo de visitas, cliques, CTR, estado financeiro e alertas por
   prioridade. Destaque posts afetados e a ação humana recomendada.
4. Não estime custos do Hermes a partir dessas métricas e não altere conteúdo,
   monetização, configuração ou agenda.

## Controles de execução

- Não crie drafts nesta rotina.
- Não execute monetização; ela possui cron próprio.
- Não repita uma submissão quando a API confirmar idempotência.
- Na primeira falha técnica repetida, encerre a etapa afetada e marque-a como
  `needs_operator`, continuando apenas etapas independentes.
- Nunca exponha tokens, cookies, prompts internos ou respostas privadas.

## Saída consolidada

Produza os blocos:

1. `REVISÃO`: posts, relatório, recomendação e risco;
2. `DESEMPENHO 7D`: visitas, cliques, CTR e estado financeiro;
3. `ALERTAS`: contagem por prioridade, posts e ação recomendada;
4. `PENDÊNCIAS HUMANAS`: decisões editoriais e verificações necessárias;
5. `ESTADO`: `ok`, `attention` ou `needs_operator`.

Declare explicitamente que publicação e decisão final permanecem humanas.
