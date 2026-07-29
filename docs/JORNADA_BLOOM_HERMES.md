# Da reconstrução dos blogs à automação editorial com Hermes

## Sobre este documento

Este é o diário público e sanitizado da evolução da plataforma Bloom. Ele
registra decisões, erros, correções e resultados sem incluir senhas, tokens,
IPs, IDs pessoais ou detalhes que facilitem acesso à infraestrutura.

O material pode ser adaptado para:

- artigo técnico;
- estudo de caso;
- vídeo para YouTube;
- série de posts;
- documentação interna da Expansão AI.

## A visão

O objetivo começou como a recuperação de dois sites:

- ViralBarato, voltado a produtos, ofertas e conteúdo de afiliados;
- Mundo no Prato, voltado a gastronomia e receitas.

Durante o trabalho, o projeto evoluiu para uma plataforma editorial
multi-tenant com SEO, monetização, imagens próprias e automação diária
controlada por um agente hospedado na VPS.

O princípio central passou a ser:

> Automação não significa publicar sem controle. Significa tornar pesquisa,
> produção, validação e revisão repetíveis, observáveis e seguras.

## Capítulo 1 — Recuperar antes de automatizar

Antes de pensar em geração diária, foi necessário estabilizar a base:

- restaurar e validar o PostgreSQL;
- identificar tenants pelo domínio;
- corrigir slugs e redirects;
- eliminar conteúdo de teste;
- consolidar posts duplicados;
- remover links de afiliados incorretos;
- validar ASINs individualmente;
- recuperar imagens quebradas;
- servir imagens WebP locais;
- revisar títulos, descrições e conteúdo.

### Lição

Automatizar uma base inconsistente multiplica inconsistências. Curadoria e
integridade vieram antes da escala.

## Capítulo 2 — SEO e monetização sem comprometer a experiência

Os dois sites receberam uma fundação comum para:

- metadata de SEO;
- canonical;
- sitemap e robots;
- dados estruturados;
- AdSense;
- ads.txt;
- Adcash com configuração específica por tenant.

As integrações de anúncios foram tratadas como configuração de runtime. Isso
evitou gravar códigos sensíveis ou diferentes por site diretamente no código.

### Incidente útil

Um script completo de anúncio foi colocado como valor de variável em um arquivo
`.env`. Aspas e caracteres do JavaScript quebraram a leitura do Compose.

A correção foi separar configuração de código: variáveis guardam identificadores
simples; o frontend monta o script de forma controlada.

### Lição

Arquivos `.env` não são templates HTML nem locais seguros para armazenar blocos
arbitrários de JavaScript.

## Capítulo 3 — A curadoria do ViralBarato

A revisão encontrou:

- post de teste publicado;
- artigos duplicados e triplicados;
- links apontando para produtos diferentes;
- ASINs ausentes ou incorretos;
- títulos e slugs pouco naturais;
- conteúdo com qualidade desigual.

O trabalho combinou:

- normalização determinística;
- consultas ao banco;
- validação manual de destinos;
- redirects 301;
- arquivamento em vez de exclusão indiscriminada;
- reescrita editorial dos casos prioritários.

### Lição

Em conteúdo de afiliados, um link tecnicamente válido pode estar editorialmente
errado. O destino precisa corresponder exatamente ao produto descrito.

## Capítulo 4 — Imagens próprias mudaram a percepção dos sites

As imagens externas e frágeis foram substituídas por ativos WebP próprios. O
resultado visual foi um dos pontos de virada do projeto.

O padrão adotado:

- imagem exclusiva por artigo;
- formato WebP;
- caminho previsível;
- ausência de texto, marca ou embalagem copiada;
- coerência visual com a pauta;
- validação HTTP antes da publicação.

### Lição

Imagem não é acabamento. Em sites editoriais, ela influencia confiança,
identidade, compartilhamento e percepção de qualidade.

## Capítulo 5 — O primeiro desenho da automação estava errado

A arquitetura inicial previa um novo worker dedicado. A auditoria da VPS mostrou
que o Hermes já possuía:

- scheduler e cron;
- trava contra concorrência;
- jobs com modelo e perfil próprios;
- skills;
- plugins;
- roteamento de ferramentas;
- geração de imagens;
- outputs persistidos;
- mecanismos de segurança para prompts agendados.

A decisão foi revista: a automação do Bloom seria nativa do Hermes, sem um
segundo sistema concorrente.

### Lição

Antes de criar infraestrutura, audite a capacidade já instalada. O melhor novo
componente pode ser nenhum componente.

## Capítulo 6 — Acesso temporário e auditoria segura

Foi criado um usuário temporário de auditoria com:

- chave SSH específica;
- acesso limitado;
- comandos sudo explicitamente autorizados;
- leitura do código por ACL;
- nenhuma exposição deliberada dos volumes privados.

Durante a configuração, um comando que prometia saída redigida exibiu chaves
completas. Todas foram imediatamente revogadas e rotacionadas.

### Lição

Nunca confie apenas na palavra “redacted” de uma ferramenta. Saídas de
diagnóstico também precisam ser tratadas como potencialmente sensíveis.

## Capítulo 7 — Um perfil exclusivo para o Bloom

Foi criado um perfil `bloom` do zero, sem clonar memória ou credenciais do
perfil pessoal.

Configuração adotada:

- DeepSeek V4 Pro via OpenRouter para o trabalho editorial;
- GPT Image 2 Medium para imagens;
- DuckDuckGo para descoberta inicial;
- navegador local para extração;
- Telegram para relatórios;
- limite reduzido de iterações;
- reset por inatividade e diário;
- terminal, código, memória e delegação desabilitados para o agente editorial.

### Lição

Isolamento de perfil é tão importante quanto isolamento de container. Memória,
ferramentas e credenciais devem seguir o princípio do menor privilégio.

## Capítulo 8 — A API precisava ser protegida

A auditoria descobriu que o endpoint de criação de posts:

- era público;
- não exigia autenticação;
- aceitava publicação direta;
- ignorava silenciosamente algumas referências inválidas.

A nova camada adicionou:

- token Bearer dedicado;
- comparação segura;
- autopublicação desligada por padrão;
- chave de idempotência obrigatória;
- tabela `content_jobs`;
- validação estrita de categoria e ASIN;
- respostas sem detalhes internos do banco;
- criação forçada de draft pelo plugin do Hermes.

### Lição

Um agente não deve receber acesso direto ao banco quando uma API restrita pode
expressar exatamente as operações permitidas.

## Capítulo 9 — Resolver imagens sem commits automáticos

As imagens antigas estavam dentro do container do frontend. Isso não funcionaria
para uma rotina diária sem commit e deploy.

A solução foi:

- upload autenticado para a API;
- validação de tipo, bytes e dimensões;
- conversão server-side para WebP;
- remoção de metadados;
- deduplicação por SHA-256;
- armazenamento em volume persistente;
- entrega pública pela rota `/media`.

Essa abordagem evitou conceder ao Hermes permissão para fazer push no
repositório ou deploy em produção.

### Lição

Ativos gerados por automação precisam de ciclo de vida próprio. O repositório de
código não deve virar armazenamento operacional por conveniência.

## Capítulo 10 — O plugin restrito

O plugin `bloom-content` oferece somente três ferramentas:

1. consultar categorias e posts recentes;
2. enviar uma imagem gerada;
3. criar um draft idempotente.

Ele não aceita:

- SQL;
- terminal;
- URL arbitrária;
- publicação direta;
- tenants fora da allowlist;
- imagens fora do cache do Hermes.

### Lição

Ferramentas para agentes devem ser estreitas. Quanto menor a superfície de
ação, mais fácil auditar, testar e confiar.

## Capítulo 11 — O primeiro draft automatizado

O primeiro fluxo real executou:

- carregamento do skill;
- consulta ao tenant;
- pesquisa;
- geração de imagem;
- upload e conversão WebP;
- criação idempotente;
- retorno de ID e slug.

O draft sobre tipos de sal foi criado com sucesso. A imagem:

- ficou visualmente coerente;
- foi servida com HTTP 200;
- tinha menos de 200 KB;
- não continha texto ou marcas.

Mas o teste também revelou uma falha: o navegador ainda não estava instalado, e
o agente tratou URLs encontradas como fontes efetivamente lidas.

O draft permaneceu sem publicação.

### Lição

O primeiro teste de produção deve tentar provar que o sistema está errado. Um
draft bloqueado ensina mais do que uma publicação apressada.

## Capítulo 12 — Extração não é autoridade

Após instalar o Chrome no volume persistente do perfil, a navegação passou a
funcionar. Um novo teste leu páginas reais.

Mesmo assim, uma fonte afirmou uma diferença de sódio questionável entre tipos
de sal. Fontes oficiais indicavam uma conclusão diferente.

O skill foi endurecido:

- snippets não contam como fonte;
- pelo menos duas páginas precisam ser extraídas;
- falha de navegação bloqueia o draft;
- saúde e nutrição exigem fonte oficial ou estudo primário;
- conflitos são resolvidos em favor da fonte mais autoritativa;
- diferenças pequenas não podem virar alegações clínicas.

### Lição

Conseguir ler uma página prova acesso, não confiabilidade. Pesquisa automatizada
precisa avaliar hierarquia de evidência.

## Estado atual

Concluído:

- plataforma multi-tenant estável;
- SEO e monetização;
- curadoria prioritária;
- imagens próprias;
- perfil Hermes isolado;
- API autenticada e draft-only;
- idempotência;
- mídia persistente;
- plugin e skill;
- navegador persistente;
- primeiro teste ponta a ponta.

Pendente:

- interface ou fluxo de revisão dos drafts;
- edição, aprovação e rejeição;
- segundo teste com fontes autoritativas;
- teste equivalente no ViralBarato;
- cron diário inicialmente pausado;
- sete dias de shadow mode;
- limites de recursos do container;
- alertas e métricas;
- ativação gradual da publicação.

## Estrutura sugerida para artigo

Título provisório:

> Como transformamos dois blogs quebrados em uma plataforma editorial com IA,
> sem entregar a produção inteira ao agente

Estrutura:

1. O estado inicial.
2. Por que a curadoria veio primeiro.
3. A arquitetura multi-tenant.
4. Imagens e monetização.
5. Auditoria do Hermes.
6. O erro do worker duplicado.
7. Segurança da API.
8. Primeiro draft e primeira falha.
9. O problema das fontes.
10. O que falta para autopublicar.

## Estrutura sugerida para vídeo

### Abertura

“Eu queria automatizar dois blogs com IA. Antes de publicar o primeiro artigo,
descobri posts duplicados, imagens quebradas, links errados e um endpoint aberto.
Foi aí que o projeto ficou interessante.”

### Blocos

1. Antes e depois visual dos sites.
2. O banco e a arquitetura multi-tenant.
3. Curadoria de conteúdo e afiliados.
4. Como o Hermes já estava estruturado.
5. Perfil isolado e ferramentas mínimas.
6. API segura e imagens persistentes.
7. Demonstração do primeiro draft.
8. A falha silenciosa das fontes.
9. Por que o artigo não foi publicado.
10. Próximos passos até produção.

### Encerramento

“A parte mais valiosa da automação não foi gerar texto ou imagem. Foi construir
um sistema capaz de dizer não quando ainda não existe evidência suficiente para
publicar.”

## Princípios que ficaram

1. Curadoria antes de escala.
2. Draft antes de autopublicação.
3. API restrita antes de acesso ao banco.
4. Idempotência antes de cron.
5. Evidência antes de afirmação.
6. Fonte lida não é automaticamente fonte confiável.
7. Perfil isolado antes de credenciais compartilhadas.
8. Ativos persistentes antes de URLs efêmeras.
9. Observabilidade antes de autonomia.
10. Rollout gradual antes de confiança.
