---
name: bloom-social-video
description: Produz diariamente um pacote de vídeo vertical pronto para revisão e publicação manual no TikTok, usando conteúdo publicado e métricas reais do Bloom.
---

# Bloom Social Video

Gere no máximo um pacote por execução. O resultado é um vídeo pronto para
revisão humana; esta skill nunca publica, autentica ou interage com o TikTok.

## Fluxo obrigatório

1. Chame `bloom_performance_metrics` com `days=7` e `tenant=viralbarato`.
2. Chame `bloom_context` com `tenant=viralbarato` e use somente um post
   publicado retornado pela ferramenta. Priorize artigo com tráfego medido;
   na ausência de tráfego por artigo, escolha o post recente com melhor
   potencial de dica útil. Não invente desempenho.
3. Crie um roteiro original de 18 a 25 segundos, em português do Brasil, com
   quatro a seis cenas. Cada tela deve ter no máximo 90 caracteres e uma ideia.
4. Gere uma imagem vertical sem texto, marcas ou embalagens copiadas para cada
   cena. Use imagens próprias ou geradas pelo recurso de imagem disponível.
   Nunca reutilize imagem de outro tenant e nunca baixe material sem licença.
5. Crie `manifest.json` conforme o contrato abaixo dentro de
   `/home/hermes/.hermes/profiles/bloom/work/tiktok/<AAAA-MM-DD>/`.
6. Execute exatamente:

   `python3 /home/hermes/.hermes/profiles/bloom/skills/bloom-social-video/render_video.py manifest.json /home/hermes/.hermes/profiles/bloom/outputs/tiktok/<AAAA-MM-DD>-viralbarato`

7. Confirme que o renderizador respondeu `rendered` ou `already_exists`, que
   `package.json` contém `render.validated=true` e que existem `video.mp4`,
   `cover.jpg` e `publicacao.md`. Não declare sucesso sem esses arquivos.

## Contrato do manifesto

```json
{
  "tenant": "viralbarato",
  "profile": "@viralbarato5",
  "title": "Título curto do vídeo",
  "source_post_id": 58,
  "source_url": "https://viralbarato.com.br/blog/slug-publicado",
  "selection_reason": "Evidência observada ou hipótese explicitamente marcada",
  "caption": "Legenda pronta para revisão",
  "hashtags": ["ViralBarato", "DicasDeCompra", "CustoBeneficio"],
  "scenes": [
    {"duration": 3.5, "text": "Gancho direto", "image": "/caminho/absoluto/scene-01.png"},
    {"duration": 4.0, "text": "Uma ideia por tela", "image": "/caminho/absoluto/scene-02.png"},
    {"duration": 4.0, "text": "Explique sem promessas", "image": "/caminho/absoluto/scene-03.png"},
    {"duration": 4.0, "text": "Dê uma ação prática", "image": "/caminho/absoluto/scene-04.png"},
    {"duration": 4.5, "text": "Salve para consultar depois", "image": "/caminho/absoluto/scene-05.png"}
  ]
}
```

## Gates editoriais

- O assunto deriva de post realmente publicado e a URL pertence ao tenant.
- Não incluir preço, cupom ou disponibilidade sem verificação atual.
- Não alegar teste físico, experiência pessoal, garantia de economia ou saúde.
- Conteúdo de saúde, alimentação e segurança exige fonte oficial já presente
  no artigo; quando isso não puder ser confirmado, escolha outro post.
- A abertura entrega o tema no primeiro segundo, sem vinheta.
- O CTA pede salvar, comentar ou visitar o perfil; não força compra.
- As imagens não contêm texto gerado. O texto é aplicado pelo renderizador.
- A faixa de áudio permanece silenciosa para escolha manual de música.

## Idempotência e retenção

A pasta final é única por data. Se `video.mp4` já existir, não gere outra pauta
nem use `--force`. Mantenha os últimos 30 pacotes e remova somente diretórios
mais antigos dentro de `outputs/tiktok`, nunca fora desse caminho.

## Saída

Responda com data, título, post de origem, motivo de seleção, duração validada e
caminho absoluto do pacote. Em falha, responda `needs_operator` e indique a
etapa exata. Nunca exponha tokens, cookies ou prompts internos.
