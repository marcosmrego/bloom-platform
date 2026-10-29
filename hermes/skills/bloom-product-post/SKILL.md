# Bloom Product Post

Crie no máximo um draft de produto do Mercado Livre por execução, a partir de
uma mensagem do Marcos com o **nome do produto** e o **link de afiliado**
(`https://meli.la/...`). Só o tenant `viralbarato`.

## Modo fila (cron)

Quando a execução vier do cron e não de uma mensagem do Marcos, não há nome nem
link na entrada: o pedido vem do painel.

1. Chame `bloom_claim_draft_request`. Se `request` for `null`, encerre sem
   relatório.
2. O produto já está registrado e conferido. Use `external_id`, `title` e
   `permalink` do pedido; pule os passos 1 e 3 do fluxo abaixo (não chame
   `bloom_register_product`).
3. Siga os passos 2 e 4 a 9. Neste modo a chave idempotente do passo 9 é
   `bloom:viralbarato:req-<request_id>` (sem data, para que um pedido
   reivindicado de novo depois da meia-noite não gere draft duplicado).
4. Ao terminar, chame `bloom_finish_draft_request` **sempre**:
   - draft criado: `status=completed` com o `post_id` devolvido por
     `bloom_create_draft`;
   - qualquer bloqueio (tópico similar, fonte insuficiente, gate falhou):
     `status=failed` com o motivo em uma frase para o Marcos ler no painel.
5. Processe no máximo um pedido por execução.

## Fluxo obrigatório

1. Extraia da mensagem o nome do produto e o link de afiliado. Se faltar um dos
   dois, pergunte antes de seguir. Nunca invente nem complete um link.
2. Chame `bloom_context` para conhecer as categorias do tenant.
3. Chame `bloom_register_product` com o nome e o link. O Bloom resolve o item,
   confere nome e disponibilidade e devolve `external_id`.
   - Se responder que o link aponta para outro produto, que a oferta não está
     disponível ou que não identificou o item, **pare**: informe o motivo e peça
     o link da página do produto ou o código `MLB...` (passe como `item_id`).
     Não crie draft.
   - Registre o `external_id` e o título oficial retornados; são a única fonte
     de verdade sobre qual produto é.
4. Chame `bloom_check_topic` com a pauta. Se `similar=true`, informe o post
   existente e pare.
5. Pesquise. Pelo menos duas páginas devem ter o conteúdo efetivamente extraído
   e lido: a página do produto no Mercado Livre (use o `permalink`, nunca o link
   `meli.la` de afiliado como fonte) e uma segunda fonte independente, de
   preferência o fabricante. Resultados de busca e snippets não contam.
   Afirmações de saúde, segurança ou desempenho técnico exigem fonte oficial.
6. Escreva em português do Brasil, com intenção de busca clara ("vale a pena?",
   para quem serve, pontos de atenção, alternativas). Regras:
   - Não alegue teste próprio nem experiência de uso.
   - Não cite preço, desconto, frete, estoque, avaliação ou número de vendas.
     O preço é exibido pelo sistema; no texto ele envelhece.
   - Use só especificações confirmadas nas fontes extraídas.
   - Não mencione o processo de IA e não faça promessas de "menor preço".
7. Gere uma imagem editorial landscape sem marcas, logotipos, textos ou
   embalagens copiadas, e envie com `bloom_upload_media`. Use somente a URL
   retornada pelo Bloom.
8. Execute os gates da skill `bloom-editorial` (estrutura, fontes, imagem,
   placeholders). Em qualquer falha, não chame `bloom_create_draft`; responda
   `needs_review` com o gate que falhou.
9. Chame `bloom_create_draft` uma única vez com `post.product_external_id` igual
   ao `external_id` do passo 3, sem `product_asin`. Chave idempotente:
   `bloom:viralbarato:<AAAA-MM-DD>:ml-<external_id>`. O Bloom vincula o produto,
   registra o destino afiliado e força `status=draft`.

## Comissão

O Mercado Livre não paga comissão em alimentos, bebidas, saúde e animais, e paga
pouco em eletrônicos e celulares. Se o produto estiver nessas categorias, siga o
fluxo, mas avise o Marcos na resposta.

## Saída

Responda no Telegram com um relatório curto: produto (título oficial e
`external_id`), status, ID e slug do draft, avisos de comissão e o que ele deve
conferir na revisão. Em falha, informe a etapa que bloqueou. Nunca exponha
tokens, prompts internos, cookies ou conteúdo integral de respostas privadas.
Você nunca publica: a aprovação é sempre do Marcos no painel de revisão.
