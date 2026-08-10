---
name: bloom-daily-ops
description: Orquestra a rotina diária segura do Bloom, delegando revisão editorial e auditoria operacional às skills competentes, sem aprovar, editar ou publicar conteúdo.
---

# Bloom Daily Ops

Execute uma rotina sequencial, idempotente e limitada. Atue como orquestrador,
aplicando diretamente os contratos das skills especialistas e consolidando o
resultado. Uma falha em uma etapa não autoriza atalhos nas demais. Não declare
uma etapa concluída sem executar as ferramentas obrigatórias e citar os dados
retornados por elas.

## Etapa 1 — revisão editorial (`bloom-reviewer`)

1. Aplique integralmente o contrato da skill `bloom-reviewer`.
2. Chame `bloom_editorial_review_backlog` uma vez para `viralbarato` e uma vez
   para `mundonoprato`, sempre com `limit=1`.
3. Revise no máximo um draft por tenant e chame
   `bloom_submit_editorial_review` para cada parecer concluído.
4. Envie apenas parecer estruturado. Não edite, aprove, rejeite, arquive nem
   publique.
5. Registre backlog vazio como resultado normal, mencionando explicitamente o
   tenant consultado.

## Etapa 2 — auditoria de desempenho (`bloom-operations`)

1. Chame `bloom_performance_metrics` com `days=7`, sem filtro de tenant.
2. Classifique os dados conforme a disciplina de evidência da skill
   `bloom-operations`.
3. Relate `site_views`, `article_views`, `other_page_views`, cliques, CTR,
   estado financeiro e alertas por prioridade. Use `pages` para destacar os
   caminhos e tenants com maior tráfego, diferenciando interesse na home ou em
   categorias de engajamento efetivo nos artigos.
4. Destaque posts afetados e a ação humana recomendada. Não conclua que um
   tenant está sem audiência apenas porque `article_views=0` quando existem
   acessos em outras páginas.
5. Não estime custos do Hermes a partir dessas métricas e não altere conteúdo,
   monetização, configuração ou agenda.

## Controles de execução

- Não crie drafts nesta rotina.
- Não execute monetização; ela possui cron próprio.
- Não repita uma submissão quando a API confirmar idempotência.
- Na primeira falha técnica repetida, encerre a etapa afetada e marque-a como
  `needs_operator`, continuando apenas etapas independentes.
- Nunca exponha tokens, cookies, prompts internos ou respostas privadas.
- Se qualquer ferramenta obrigatória não estiver disponível ou não tiver sido
  chamada, não use “concluído”: marque a etapa como `needs_operator` e informe
  exatamente qual chamada faltou.

## Saída consolidada

Produza os blocos:

1. `REVISÃO`: posts, relatório, recomendação e risco;
2. `DESEMPENHO 7D`: visitas, cliques, CTR e estado financeiro;
3. `ALERTAS`: contagem por prioridade, posts e ação recomendada;
4. `PENDÊNCIAS HUMANAS`: decisões editoriais e verificações necessárias;
5. `ESTADO`: `ok`, `attention` ou `needs_operator`.

Declare explicitamente que publicação e decisão final permanecem humanas.
Uma resposta genérica sem IDs/estado de backlog e sem os números retornados por
`bloom_performance_metrics` é inválida.
