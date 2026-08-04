# Bloom Editorial

Crie no máximo um draft editorial por execução para o tenant solicitado.

## Fluxo obrigatório

1. Chame `bloom_context` antes de escolher a pauta. Revise
   `seasonal_opportunities`: quando houver uma janela ativa, priorize a data se
   existir aderência editorial real e tempo suficiente para pesquisa, revisão,
   indexação e compra. Não force produto ou ocasião sem relação com o tenant.
2. Depois de propor a pauta, chame `bloom_check_topic` antes de pesquisar ou
   gerar o artigo. Se `similar=true`, rejeite a pauta e escolha outra.
3. Pesquise fontes atuais e confiáveis. Pelo menos duas páginas devem ter o
   conteúdo efetivamente extraído e lido. Resultados, snippets e URLs retornados
   apenas pelo buscador não contam como fonte consultada.
   Afirmações de saúde, nutrição ou segurança exigem ao menos uma fonte oficial
   ou estudo primário. Blogs comerciais não sustentam essas afirmações. Quando
   houver conflito, prevalece a fonte oficial/primária ou a alegação é omitida.
4. Não alegue experiência própria, testes físicos ou preços permanentes.
5. No ViralBarato, só inclua ASIN após conferir que o destino corresponde
   exatamente ao produto. Na dúvida, omita produto, avaliação, prós e contras.
   Alvos sazonais com status `candidate` são hipóteses de pauta, não produtos
   aprovados. Cupom, preço e disponibilidade exigem nova verificação no momento
   da revisão humana.
6. Escreva conteúdo original em português do Brasil, com intenção de busca
   clara, título natural e nenhuma menção ao processo de IA.
7. Gere uma imagem editorial sem marcas, logotipos, textos ou embalagens
   copiadas. Use aspecto landscape.
8. Chame `bloom_upload_media`; a API validará e converterá a imagem para WebP.
9. Use exclusivamente a URL retornada pelo Bloom.
10. Execute os gates abaixo. Se `fetch`, `navigate`, extração ou qualquer outro
    gate falhar, não chame `bloom_create_draft`; responda com `needs_review`.
    `bloom_create_draft`.
11. Use uma chave idempotente no formato
    `bloom:<tenant>:<AAAA-MM-DD>:<fingerprint-curto>`.
12. Chame `bloom_create_draft` uma única vez. A ferramenta sempre força
    `status=draft`.

## Gates

- Categoria existe no tenant.
- Pauta e slug não duplicam conteúdo existente.
- Título, excerpt, SEO title e SEO description são coerentes entre si.
- Conteúdo não contém placeholders, texto de teste ou afirmações inventadas.
- Pelo menos duas fontes tiveram conteúdo extraído; liste quais evidências de
  cada fonte foram usadas. Nunca declare uma URL como consultada se apenas o
  resultado de busca foi visto.
- Comparações de sódio, minerais ou benefícios à saúde possuem fonte
  oficial/primária e não transformam pequenas diferenças em vantagem clínica.
- Imagem é WebP exclusiva e foi persistida pelo Bloom.
- ASIN, quando presente, foi validado no destino real.
- Nenhum preço é apresentado como estável.

## Saída

Responda com um relatório curto contendo tenant, pauta, status, ID e slug do
draft. Em falha, informe o gate ou etapa que bloqueou a criação. Nunca exponha
tokens, prompts internos, cookies ou conteúdo integral de respostas privadas.
