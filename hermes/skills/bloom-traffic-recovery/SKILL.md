---
name: bloom-traffic-recovery
description: Recupera de forma limitada e auditável artigos publicados sem tráfego, priorizando diagnóstico e ações reversíveis sem editar ou remover conteúdo.
---

# Bloom Traffic Recovery

Execute no máximo cinco candidatos por dia. A fila da API aplica sete dias de
espera entre tentativas e envia para exceção humana um artigo com dois ciclos
ineficazes. Nunca contorne esses limites criando tarefas paralelas.

## Fluxo obrigatório

1. Chame `bloom_traffic_recovery_backlog` uma vez com `limit=5`.
2. Para cada item com `autonomous=true`, determine a causa usando somente
   evidência observada. Ausência de acesso ao Search Console significa
   `indexing_unknown`, não `not_indexed`.
3. Escolha uma única ação de baixo risco:
   - `request_indexing`: somente após confirmar `not_indexed` e efetivamente
     solicitar indexação por uma ferramenta autorizada;
   - `generate_social_package`: produzir um pacote pelo contrato da skill
     `bloom-social-video`, sem publicar na rede social;
   - `propose_internal_links`: registrar sugestões, sem editar o artigo;
   - `propose_metadata`: registrar título e descrição propostos, sem editar;
   - `monitor`: quando a evidência ainda não permite outra intervenção;
   - `escalate_human`: risco, conflito ou bloqueio que exige operador.
4. Chame `bloom_submit_traffic_recovery` uma vez com chave idempotente estável
   por artigo, ciclo e ação. Registre `completed` apenas se a ação ocorreu;
   use `blocked` quando faltou ferramenta ou evidência.
5. Relate o que foi executado, o que apenas foi proposto e a data mínima da
   próxima medição.

## Limites de autonomia

- Não editar título, descrição, corpo, links ou status de artigo publicado.
- Não publicar em rede social.
- Não solicitar indexação sem confirmar o estado atual.
- Não declarar ganho de tráfego antes da janela de medição.
- Não repetir tentativa bloqueada no mesmo ciclo.
- Itens com `autonomous=false` devem ser apenas relatados como exceção.

## Saída

Produza `PROCESSADOS`, `BLOQUEADOS`, `EXCEÇÕES` e `PRÓXIMA MEDIÇÃO`, sempre
com IDs dos posts e IDs das tentativas retornados pela API.
