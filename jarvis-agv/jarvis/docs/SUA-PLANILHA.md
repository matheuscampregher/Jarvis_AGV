# Conferência da sua planilha — 16/10/2026

A [planilha compartilhada](https://docs.google.com/spreadsheets/d/1DwHguCj2RcNHXCmfQSdNKFcDM8aw8F7knYl-wNygZcs/edit?gid=956506766#gid=956506766) foi somente lida. Esta avaliação substitui a de 15/10/2026. As alterações desta entrega estão no projeto, não no arquivo online.

## O que mudou

A estrutura continua adequada para esta etapa do Jarvis. A aba antes chamada Horarios agora se chama **Horário DS1**. Ela contém **30 registros de aulas da turma 1°Ds, de segunda a sexta: 29 completos e um incompleto**.

A aba Disciplinas passou a ter 14 cadastros, incluindo Biologia (`BL1°Ds`) e Educação Digital (`ED1°Ds`). Todos os 30 códigos usados na grade existem no cadastro. São 12 turmas com salas padrão e 12 professores distintos em 14 linhas; repetir o nome por matéria não cria outra pessoa.

| Dia | Linhas de aulas | Aulas completas | Pendência |
| --- | --- | ---: | --- |
| Segunda | 2–7 | 6 | — |
| Terça | 9–14 | 5 | B14 vazio |
| Quarta | 16–21 | 6 | — |
| Quinta | 23–28 | 6 | — |
| Sexta | 30–35 | 6 | — |

## Primeiro: preencha B14

Em **Horário DS1!B14**, informe o horário inicial correto da aula `AM1°Ds`, de terça-feira. O cadastro a relaciona a Análise e Método Para Sistemas, com Gabriel Elienai. O valor precisa constar na tabela de horários de Turmas!E:F usada pelo PROCV. **Não foi presumido um horário para essa aula.**

C14 mostra #N/A porque depende de B14. Enquanto a linha estiver incompleta, o teste e as consultas escolares avisam: `Aba Horário DS1, linha 14: o campo Horario Inicial está vazio.` Preencha o início e confira o resultado do horário final. A aplicação mantém essa validação para não apresentar uma grade incompleta como se estivesse correta.

As outras 29 aulas não apresentaram sobreposição de professor, turma ou sala. O conflito envolvendo a aula incompleta só pode ser verificado depois que seu horário for preenchido. Duas aulas consecutivas de uma mesma disciplina são aceitas: não são duplicadas quando ocupam intervalos diferentes.

## Fórmulas e tabela de horários

As linhas separadoras **8, 15, 22 e 29** não contêm aulas, mas suas fórmulas mostram #N/A. A atualização ignora essas linhas e emite um aviso. Para também corrigir a aparência da planilha, use estas fórmulas a partir da linha 2 e copie para baixo:

```text
C2: =SE(B2="";"";PROCV(B2;Turmas!$E$2:$F$7;2;FALSO))
E2: =SE(D2="";"";PROCV(D2;Disciplinas!A:E;2;FALSO))
F2: =SE(D2="";"";PROCV(D2;Disciplinas!A:E;5;FALSO))
```

A condição trata somente entradas vazias; horários e códigos inválidos continuam visíveis. Essas fórmulas não substituem o preenchimento de B14. Se sua configuração usa funções em inglês, os equivalentes são IF, VLOOKUP e FALSE, com os separadores do seu arquivo.

A tabela auxiliar **Turmas!E2:F7**, Entrada/Saída, contém seis faixas: 07:30–08:20, 08:20–09:10, 09:10–10:00, 10:20–11:10, 11:10–12:00 e 12:00–12:50. Amplie o intervalo da fórmula se adicionar novas faixas.

Essa tabela é independente das turmas e salas em A:B; não há relacionamento pela posição da linha. **Não ordene A:F como uma única tabela.** Você pode manter E:F ali, mas separar essa tabela numa aba própria futuramente deixaria a organização mais clara e exigiria atualizar a fórmula de C.

## Relacionamentos utilizados

| Origem | Destino | Resultado |
| --- | --- | --- |
| Horário DS1.Aula | Disciplinas.ID | cadastro da aula |
| Disciplinas.Disciplina | nome da matéria | disciplina apresentada |
| Disciplinas.Professor | Professores.Nome Prof | nome completo do professor |
| Disciplinas.Turma | Turmas.Turmas | turma |
| Turmas.N° Salas | sala padrão da turma | localização prevista |
| Horário DS1.Sala, opcional | substitui a sala padrão naquela linha | laboratório, quadra ou outra sala |

As fórmulas E/F são de exibição: o programa refaz esses relacionamentos pelos cadastros. O horário final em C é lido pelo programa, inclusive quando calculado por fórmula.

Em Disciplinas!E2 e E3, prefira `Lucas Pawlak`; em E4, `Luciano Roberto`. As abreviações atuais são aceitas porque identificam uma única pessoa. Se surgir outro Lucas, o programa exigirá desambiguação. A coluna Matéria de Professores é descritiva; a atribuição da aula vem de Disciplinas.

Para 1°Ds, N° Salas fornece sala 2. Confirme essa localização e acrescente uma coluna `Sala` na grade se uma aula ocorrer na quadra ou laboratório. O Jarvis informa a localização prevista pela grade, não a posição física da pessoa.

## O que foi ajustado no projeto

- `jarvis/configurar_planilha.py` e `config.exemplo.json`: novo nome de aba, Horário DS1, já sugerido.
- `jarvis/sheets.py`: separadores vazios com erro de fórmula em C/E/F são ignorados com aviso; aulas incompletas continuam gerando erro com campo e linha.
- `jarvis/sheets.py`: a tabela auxiliar Entrada/Saída não cria turmas vazias ao crescer além da lista em A:B.
- `tests/test_horarios.py`: testes para esses casos e horários numéricos arredondados pelo cálculo de fórmulas.

Interface, logo, Qwen, duas vozes em português e duas em inglês permanecem iguais.

## Como atualizar e testar sem Cloud

1. Se B14 ainda estiver vazia, preencha o início correto e confira C14.
2. Extraia o novo ZIP em outra pasta e execute `Jarvis.py` (opção 1 — Instalar).
3. Execute `Jarvis.py` (opção 2 — Configurar a planilha). **Modo 1** usa o link normal, sem JSON, desde que a leitura e o download estejam liberados para quem tem o link. Não é acesso privado.
4. Para manter a planilha privada sem Cloud, baixe pelo Google um arquivo **Microsoft Excel (.xlsx)** e escolha **modo 2**. Selecione esse arquivo. Baixe novamente após cada alteração que quiser levar ao Jarvis.
5. Mantenha **formato 1** e confirme Professores, Disciplinas, Turmas e **Horário DS1**.
6. Execute `Jarvis.py` (opção 3 — Testar a planilha) e corrija qualquer erro. Com o horário da linha 14 correto e sem outras alterações, a contagem esperada é 30 aulas.
7. Mantenha o Ollama aberto, execute `Jarvis.py` (opção 5 — Iniciar) e pergunte: `Quais aulas da turma 1 DS terça das 7:45 às 8:35?`

A resposta esperada nesse intervalo é **Geografia (07:30–08:20)** e **Educação Física (08:20–09:10)**. Ambas se sobrepõem ao intervalo solicitado.

Nos modos online, o cache dura **60 segundos**. Novos dados não exigem outro ZIP, desde que a estrutura e os nomes das abas sejam mantidos. No modo 2, o arquivo precisa ser atualizado manualmente. Esta versão lê uma única aba de grade; outras turmas podem ter linhas nessa mesma aba. Novas abas de horários não são descobertas automaticamente.

O guia principal, `GUIA-GOOGLE-PLANILHAS.html`, mostra as perguntas do CMD. A conexão anterior por JSON continua disponível no modo 3, explicada em `GUIA-CONTA-GOOGLE.html`.

## Validação realizada

Passaram **59 testes Python** na atualização sem Cloud. A leitura real pelo link, sem login ou JSON, recebeu as quatro abas e confirmou novamente o horário inicial vazio em B14. Para verificar as demais aulas, somente numa cópia em memória, a linha 14 foi marcada como inativa: as outras 29 passaram pelas referências e verificações de conflito. A consulta de terça por intervalo e a de sexta-feira foram conferidas nessa cópia. Nenhuma dessas alterações foi feita na planilha online.

O modo 3, se escolhido, ainda deve ter a conexão com sua conta de serviço confirmada por `Jarvis.py` (opção 3 — Testar a planilha) no seu computador. Windows, Ollama real e áudio real não foram executados nesta conferência. Os testes distribuídos contêm dados fictícios; o pacote não inclui uma cópia dos dados reais da sua planilha nem credenciais.
