# Estado operacional validado

Snapshot validado pelo operador contra repositório e produção em 05/08/2026.

- O repositório usa a branch `master`.
- A API e o frontend editorial estão implantados no Coolify e operacionais.
- A API implantada está no commit `252a969`. O commit `24e3b03` alterou apenas
  o limite da skill de monetização e foi instalado no perfil Bloom.
- O post 58 existe e está publicado no tenant `viralbarato`: “Philips
  Multigroom MG5950/15 no Dia dos Pais”, ASIN `B0CHF1DBTL`, com destino afiliado
  validado.
- Havia cinco propostas de monetização: proposta 1 aprovada como `no_match`;
  propostas 2, 3, 4 e 5 pendentes. Consultar a API para obter o estado atual em
  vez de repetir esse snapshot como fato presente.
- O painel editorial de revisão das propostas está implantado em
  `/admin/metrics`.
- `BLOOM_API_URL` e `BLOOM_CONTENT_API_TOKEN` estão funcionais no perfil. Nunca
  expor seus valores. Diagnosticar uma falha futura pelo erro observado, não por
  esta confirmação histórica.
- O cron editorial tem schedule `15 12 * * *` UTC. Um output às 12:24 é horário
  efetivo da execução, não o schedule.
- Os crons antigos do perfil `default` permanecem pausados deliberadamente para
  evitar produção duplicada. Não recomendar reativá-los como redundância sem
  eleição, health check e idempotência entre produtores.
- Não existe medição confirmada de custo diário dos crons. O valor de
  US$ 0,50/dia citado anteriormente é uma hipótese sem base suficiente.
- O manifesto `plugin.yaml` versão 1.3.0 inclui a ferramenta somente-leitura
  `bloom_performance_metrics`, além das ferramentas editoriais já registradas.
- O revisor editorial de primeira passagem está implementado pela skill
  `bloom-reviewer`. Ele lê drafts e envia pareceres estruturados; não edita,
  aprova, rejeita, arquiva nem publica. Alterações humanas invalidam o parecer
  corrente, e a decisão final registra concordância para avaliação futura.
- O cron `bloom-editorial-first-pass-review` (`ef4df3064a9c`) executa diariamente
  às `13:10 UTC`, depois do cron de drafts e antes do backfill de monetização.
- O piloto de 05/08/2026 revisou o post 59 e criou o relatório 1 com
  recomendação `pass`, risco `low` e seis checks aprovados. O post permaneceu em
  `draft`; esse resultado continua aguardando decisão humana.
- Em 10/08/2026, o cron antigo `bloom-editorial-first-pass-review`
  (`ef4df3064a9c`) foi pausado e preservado para rollback. Ele foi substituído
  pelo cron `bloom-daily-editorial-ops` (`dabd5e1dd31e`), executado diariamente
  às `13:10 UTC`. A nova rotina aplica o contrato do `bloom-reviewer`, consulta
  métricas de sete dias por ferramenta somente-leitura e produz relatório
  consolidado; aprovação e publicação continuam humanas.
- A validação direta de 10/08/2026 confirmou backlog editorial vazio nos dois
  tenants e acesso às métricas. O snapshot observado foi 2 visitas, 1 clique,
  CTR de 50% sobre amostra mínima, financeiro `awaiting_import` e 70 alertas de
  prioridade média. Revalidar esses números pela ferramenta antes de tratá-los
  como estado atual.
- Em 10/08/2026, os dois frontends públicos foram implantados no commit
  `7ad8953`. O arquivo `google9647fb0ea351262d.html` retorna HTTP 200 em
  `viralbarato.com.br` e `mundonoprato.com.br`; os dois `robots.txt` permitem
  indexação de busca e apontam para sitemaps tenant-aware; os sitemaps e
  canonicals foram validados em produção. A confirmação das propriedades e o
  envio dos sitemaps dentro do Google Search Console continuam pendentes de uma
  sessão autenticada do proprietário ou credencial específica da API.
- Em 10/08/2026, a coleta interna de analytics foi ampliada para todas as
  páginas públicas no commit `da1f23f`. O painel e a ferramenta do Hermes agora
  separam `site_views`, `article_views` e `other_page_views`, além de listar os
  caminhos mais acessados. O commit `9ed3247` moveu a ingestão pública para
  `/track/page-view`, pois o namespace `/api` do Mundo no Prato era interceptado
  por um serviço legado de newsletter. O commit `184ca13` alinhou a
  idempotência ao índice por caminho. O smoke test registrou eventos de home e
  categoria nos dois tenants, confirmou sua leitura pelo Hermes e removeu os
  quatro registros sintéticos; nenhum dado de teste permaneceu no banco.
