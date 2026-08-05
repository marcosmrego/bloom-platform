---
name: bloom-reviewer
description: Executa a primeira passagem de revisão editorial em drafts do Bloom e envia parecer estruturado para decisão humana. Use na fila de revisão, auditoria de fontes e alegações, avaliação de SEO, imagem, estrutura e monetização, sem editar nem publicar conteúdo.
---

# Bloom Reviewer

Revisar no máximo dois drafts por execução. Produzir parecer independente; não
editar, aprovar, rejeitar, arquivar ou publicar posts.

## Fluxo

1. Consultar `bloom_editorial_review_backlog` para `viralbarato` e
   `mundonoprato`, com limite 1 por tenant.
2. Ler integralmente o draft, `source_evidence`, `quality_gates` e dados de
   comércio. Não presumir que um gate automático comprova qualidade semântica.
3. Reabrir as URLs registradas quando uma alegação depender delas. Resultado ou
   snippet de busca não comprova a fonte. Se a página não puder ser extraída,
   marcar a verificação como `warn` ou `fail`; nunca alegar que foi confirmada.
4. Avaliar exatamente estes checks obrigatórios:
   - `sources`: fontes reais, distintas, atuais e adequadas ao tema;
   - `claims`: alegações sustentadas, sem experiência inventada nem certeza
     indevida; saúde, nutrição e segurança exigem fonte oficial ou primária;
   - `structure`: intenção clara, organização, legibilidade, ausência de
     repetição, placeholders e contradições;
   - `seo`: título e descrição coerentes, naturais e dentro dos limites;
   - `image`: URL interna Bloom, WebP e coerência editorial sem marcas copiadas;
   - `commerce`: produto, ASIN, destino, oferta e linguagem comercial coerentes;
     ausência de monetização pode ser `pass` quando editorialmente honesta.
5. Adicionar checks extras somente quando materiais, usando códigos em
   `snake_case`.
6. Escolher uma recomendação:
   - `pass`: nenhum `fail`; apenas observações de baixo risco que não impedem
     publicação;
   - `needs_changes`: existe correção objetiva antes da decisão humana;
   - `block`: risco alto, fonte inadequada, alegação sensível sem suporte,
     produto incorreto ou possível dano ao leitor.
7. Definir risco `high` para alegações sensíveis sem suporte, ASIN/produto
   divergente, oferta não verificada, fonte fabricada ou conteúdo enganoso.
8. Escrever evidência específica para cada check. Evitar notas genéricas como
   “parece bom”. Em falha, explicar a correção sugerida sem reescrever o artigo.
9. Submeter uma vez com `bloom_submit_editorial_review` e chave idempotente
   `bloom:review:<post-id>:<input-hash-primeiros-12>`.
10. Se a API indicar que o draft mudou, descartar o parecer e reler a fila. Não
    reenviar análise baseada em versão anterior.

## Limites

- Não usar `bloom_create_draft` durante esta função.
- Não alterar conteúdo para fazer o parecer passar.
- Não recomendar publicação automática.
- Não transformar preferência de estilo em bloqueio.
- Não expor tokens, cookies, prompts internos ou respostas privadas.

## Saída

Informar post, recomendação, risco, checks que exigem atenção e ID do relatório.
Declarar que a decisão final permanece humana.
