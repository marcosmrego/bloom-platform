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
- O manifesto `plugin.yaml` versão 1.2.0 declara as mesmas nove ferramentas
  registradas pelo plugin.
- O revisor editorial de primeira passagem está implementado pela skill
  `bloom-reviewer`. Ele lê drafts e envia pareceres estruturados; não edita,
  aprova, rejeita, arquiva nem publica. Alterações humanas invalidam o parecer
  corrente, e a decisão final registra concordância para avaliação futura.
- O cron `bloom-editorial-first-pass-review` (`ef4df3064a9c`) executa diariamente
  às `13:10 UTC`, depois do cron de drafts e antes do backfill de monetização.
- O piloto de 05/08/2026 revisou o post 59 e criou o relatório 1 com
  recomendação `pass`, risco `low` e seis checks aprovados. O post permaneceu em
  `draft`; esse resultado continua aguardando decisão humana.
