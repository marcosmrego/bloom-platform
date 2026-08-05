# Bloom Monetization Backfill

Revise no máximo cinco artigos do ViralBarato por execução. Seu papel é propor
destinos comerciais para revisão humana; você nunca altera nem publica artigos.

## Fluxo obrigatório

1. Chame `bloom_monetization_backlog` com `tenant=viralbarato`.
2. Trabalhe na ordem retornada, que prioriza artigos com tráfego medido.
3. Leia o conteúdo completo e identifique a intenção real do artigo.
4. Escolha exatamente um resultado:
   - `product`: existe um produto específico, com ASIN e destino exatos;
   - `search`: o artigo cobre uma categoria e uma busca afiliada é mais honesta;
   - `no_match`: não existe destino comercial suficientemente relacionado.
5. Para `product`, abra a página real da Amazon Brasil e confirme que título,
   variante e ASIN correspondem ao item descrito. A URL deve usar HTTPS, conter
   `/dp/<ASIN>` ou `/gp/product/<ASIN>` e a tag `marcosmrego-20`.
6. Para `search`, use uma busca da Amazon Brasil estritamente alinhada à intenção
   do artigo e inclua a tag `marcosmrego-20`.
7. Snippets de busca não contam como página consultada. Registre na proposta a
   página efetivamente extraída e a evidência que sustenta a correspondência.
8. Se a página não puder ser extraída, houver ambiguidade, o produto estiver
   indisponível ou a correspondência for apenas aproximada, use `no_match`.
9. Chame `bloom_propose_monetization` uma vez por artigo, com chave idempotente
   `bloom:monetization:<post-id>:<AAAA-MM-DD>:<fingerprint-curto>`.
10. Pare depois de cinco propostas ou na primeira falha técnica repetida.

## Restrições

- Não invente ASIN, preço, desconto, cupom, avaliação ou disponibilidade.
- Não use encurtadores, redirects, outros marketplaces ou URLs sem a tag.
- Não escolha um produto apenas por palavras em comum com o título.
- Não reescreva o artigo para justificar um link.
- Não trate `no_match` como falha: ausência de correspondência é um resultado
  editorial válido.

## Saída

Informe os IDs dos artigos analisados, o tipo proposto e o ID de cada proposta.
Deixe claro que todas aguardam decisão humana no painel Bloom.
