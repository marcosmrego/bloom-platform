# Hermes: automação editorial do Bloom

## Decisão

A automação será executada pelo Hermes já instalado na VPS. Não será criado um
worker ou container concorrente. A integração usará os recursos nativos do
Hermes:

- um skill editorial específico do Bloom;
- um cron job isolado por perfil, modelo e conjunto de ferramentas;
- o provedor nativo OpenAI para imagens com `gpt-image-2`;
- fal.ai apenas como fallback explícito;
- publicação pela API interna do Bloom, nunca por SQL editorial livre.

Os jobs antigos dos blogs permanecem pausados como legado. Eles não devem ser
reativados, reutilizados ou removidos antes da validação da nova automação.

## Situação encontrada na VPS

- Modelo principal: `deepseek/deepseek-v4-pro` via OpenRouter.
- `image_gen` não possui seleção explícita; nesse estado o Hermes prefere
  fal.ai por compatibilidade.
- O container já possui o plugin OpenAI para `gpt-image-2` nas qualidades
  `low`, `medium` e `high`.
- O cron suporta modelo, provedor, perfil, skills, ferramentas, diretório de
  trabalho, retries, outputs persistidos e trava contra concorrência.
- O container do Hermes roda como root e sem limites de CPU ou memória.
- A VPS apresenta pressão de memória/swap, carga e disco. Nenhum modelo de
  imagem deve rodar localmente nessa máquina.

## Configuração recomendada

O job do Bloom deve usar:

- modelo editorial fixado por job, sem depender do padrão global;
- `image_gen.provider: openai`;
- `image_gen.openai.model: gpt-image-2-medium`;
- qualidade `low` somente para testes e `high` somente sob revisão manual;
- toolsets mínimos: pesquisa web, geração de imagem e cliente da API Bloom;
- perfil Hermes próprio, sem memória das conversas pessoais;
- limite de uma execução simultânea e orçamento diário.

## Cadência inicial

- Uma execução diária, alternando os tenants.
- Começar em `draft_only=true` por sete dias.
- Após calibração, habilitar autopublicação por tenant.
- Limite de no máximo um post publicado por tenant em 24 horas.
- Usar jitter para evitar colisão com backups, deploys e outros 24 jobs.

## Estados

`queued -> researching -> drafting -> validating -> ready -> published`

Saídas alternativas:

- `rejected`: falhou em um gate editorial;
- `failed`: erro técnico após retries limitados;
- `needs_review`: ambiguidade de produto, fonte, imagem ou política.

## Pacote produzido

Antes da publicação, o Hermes deve produzir um artefato JSON com:

- tenant, pauta e identificador idempotente;
- título, slug, excerpt e conteúdo Markdown;
- categoria, tags, SEO title e SEO description;
- fontes, data da consulta e afirmações sustentadas;
- produto e ASIN somente quando houver correspondência exata;
- prompt, provedor, modelo, hash e metadados da imagem;
- fingerprints de título, pauta e conteúdo;
- versão do prompt, modelo editorial, custo e duração;
- resultado individual de cada gate.

## Gates bloqueantes

1. Tenant permitido e categoria pertencente ao tenant.
2. Slug normalizado e ainda não utilizado.
3. Similaridade com posts publicados e arquivados abaixo do limite.
4. Conteúdo e estrutura mínimos, sem texto de teste ou placeholders.
5. Nenhuma alegação de uso próprio sem evidência.
6. Preço nunca tratado como permanente.
7. ASIN validado no destino; divergência remove o CTA e exige revisão.
8. Imagem WebP exclusiva, persistida e acessível com HTTP 200.
9. SEO title, description, canonical e dados estruturados válidos.
10. Limite de publicação por tenant respeitado.
11. Repetição da mesma chave idempotente retorna o mesmo resultado.
12. Post, artefato e log são registrados atomicamente.

## Bloqueios atuais no Bloom

O endpoint atual `POST /api/v1/{tenant}/posts` não possui autenticação e aceita
publicação direta. Antes de conectar o Hermes, a API precisa receber:

- token interno com comparação segura e rotação;
- modo draft-only ativado por padrão;
- chave de idempotência obrigatória;
- validação estrita de tenant, categoria, produto e status;
- tabelas de execução, artefatos e auditoria;
- endpoint separado para promover um draft aprovado;
- logs sem tokens nem conteúdo sensível.

As imagens atuais ficam dentro da imagem Docker do frontend. A automação precisa
escolher uma estratégia antes de publicar:

1. armazenamento persistente/objeto e URL servida pelo domínio; ou
2. commit da imagem WebP no repositório, seguido de deploy automático.

Até essa decisão, o job deve gerar somente drafts e manter a imagem no artefato
do Hermes.

## Segurança operacional

- Não fornecer ao Hermes o usuário PostgreSQL `postgres`.
- Secrets apenas no perfil/runtime dedicado.
- Não expor portas adicionais.
- Restringir egress à API Bloom, OpenAI, fontes permitidas e armazenamento.
- Aplicar limites de CPU/memória ao container antes da rotina diária.
- Usar timeout por etapa, retries com backoff e orçamento de custo.
- Manter os jobs antigos pausados durante toda a calibração.

## Implantação em fases

1. Proteger a API e criar o controle de idempotência/auditoria.
2. Definir persistência e entrega das imagens WebP.
3. Criar perfil e skill nativos do Bloom no Hermes.
4. Criar um novo cron job, inicialmente pausado.
5. Executar manualmente e validar um draft por tenant.
6. Rodar sete dias em modo draft-only.
7. Habilitar publicação automática para um tenant.
8. Após mais sete dias estáveis, habilitar o segundo tenant.
