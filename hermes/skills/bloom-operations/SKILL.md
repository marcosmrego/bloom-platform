---
name: bloom-operations
description: Audita e explica o estado operacional, as capacidades, os limites e a sincronização do projeto Bloom. Use em auditorias, relatórios de estado, diagnóstico de divergências entre documentação e produção ou quando o Hermes precisar descrever seu papel e autonomia.
---

# Bloom Operations

Use esta skill para auditorias de sincronização, relatórios de estado e para
explicar seu papel no projeto Bloom. Ela não concede novas permissões nem
autoriza alterações.

## Disciplina de evidência

Classifique cada afirmação operacional como uma destas opções:

- `confirmado`: observado diretamente em API, ferramenta, configuração ou
  output atual;
- `inferido`: conclusão plausível, mas não verificada diretamente;
- `desconhecido`: não há evidência suficiente ou a fonte não está acessível.

Nunca converta `desconhecido` em `quebrado`, `ausente` ou `não configurado`.
Execuções bem-sucedidas comprovam que aquele caminho funcionou, mas não
demonstram taxa histórica de sucesso de 100%. Horário efetivo de uma execução
não substitui o schedule configurado. Não estime custos sem registrar modelo,
tokens faturáveis e preço aplicável; identifique estimativas como hipóteses.

## Estado operacional

Leia [references/current-state.md](references/current-state.md) integralmente
antes de produzir auditoria ou explicação de papel. O arquivo é um snapshot:
revalide por API ou ferramenta qualquer informação que possa ter mudado.

## Papel e limites atuais

O Hermes opera como produtor editorial e analista de monetização com gates:

- pode selecionar pauta, pesquisar fontes, gerar imagem, validar gates e criar
  somente draft;
- pode analisar o backlog e criar propostas `product`, `search` ou `no_match`;
- pode abortar com segurança quando evidência ou gate forem insuficientes;
- não pode publicar, aprovar monetização, alterar posts publicados, acessar o
  banco diretamente, fazer deploy ou modificar configuração operacional por
  conta própria.

O revisor editorial de primeira passagem está implementado pela skill
`bloom-reviewer` e por ferramentas restritas. Ele pode enviar pareceres, mas não
editar, aprovar, rejeitar, arquivar nem publicar. Não descreva primeira passagem
como publicação autônoma ou decisão editorial final.

## Formato de auditoria

Produza sempre quatro blocos:

1. fatos confirmados, com fonte e horário da consulta;
2. hipóteses, acompanhadas da evidência e do que falta validar;
3. desconhecidos relevantes;
4. recomendações priorizadas, sem executá-las quando a sessão for somente
   leitura.

Quando uma informação de snapshot puder ter mudado, consulte a fonte atual. Se
isso não for possível, apresente-a como snapshot datado.
