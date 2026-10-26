# Jarvis AGV adaptado à sua planilha — 16/10/2026

Abra **GUIA-GOOGLE-PLANILHAS.html** com duplo clique para seguir a configuração completa.

**Antes de testar:** preencha `Horário DS1!B14` com o horário inicial correto da aula de terça-feira. A linha tem uma aula cadastrada, mas esse campo está vazio e C14 mostra #N/A. A grade será recusada até que a linha esteja completa. Não foi presumido um horário.

Se já configurou a versão anterior, execute o configurador novamente para atualizar o nome da aba de aulas para **Horário DS1**. Somente acrescentar dados não exige uma nova versão; renomear a aba exige atualizar a configuração.

## Instalação sem Google Cloud

1. Extraia este ZIP em uma nova pasta e execute `Jarvis.py`. No Windows, duplo clique; no Termux, `python Jarvis.py`.
2. Não há mais etapa separada de instalação: na primeira execução o próprio `Jarvis.py` cria o ambiente, instala as dependências e abre o configurador da planilha. As opções numeradas abaixo ficam em `python Jarvis.py menu`, para quem precisa de uma etapa isolada.
3. Escolha **modo 1** para ler pelo link, sem JSON ou cartão. Cole o link normal da planilha; Enter usa a sua. Esse modo exige leitura e download liberados para qualquer pessoa com o link. O programa não muda permissões.
4. Para manter a planilha privada sem Cloud, escolha **modo 2**: baixe pelo Google em Arquivo → Fazer download → Microsoft Excel (.xlsx) e selecione o arquivo. Será necessário baixar outra cópia quando editar os dados no Google.
5. Mantenha **formato 1** e confirme os nomes das quatro abas. Para conferir depois, use `python Jarvis.py testar` e `python Jarvis.py iniciar`, com o Ollama aberto.

O **modo 3** mantém a conexão anterior, por conta de serviço e JSON Google. O passo a passo desse modo está em `GUIA-CONTA-GOOGLE.html`. A falta de dinheiro não impede usar os modos 1 ou 2. Se aparecer pedido de JSON depois de escolher 1 ou 2, confira se está executando o configurador desta nova pasta.

O modelo continua `qwen3:4b-instruct-2507-q4_K_M`. Não baixe novamente se já estiver instalado. Se precisar, use `ollama pull qwen3:4b-instruct-2507-q4_K_M` no CMD. A logo foi mantida. As vozes passaram a se chamar **Jarvis** e são todas masculinas: uma em português (`jarvis-pt`) e duas em inglês (`jarvis-en` e `jarvis-en-2`). Francisca, Jenny e Guy foram removidas, e uma preferência salva com os nomes antigos é convertida automaticamente. O tom padrão é **-4**, mais grave, ajustável em Voz e ajustes.

Os dados continuam vindo do Google Planilhas: online nos modos 1/3, ou de uma cópia baixada no modo 2. O configurador cria `config.json`. O modo 1 não precisa de credencial; o modo 2 copia o XLSX para `dados/grade.xlsx`; o modo 3 usa `segredos/conta-google.json`. Arquivos existentes de configuração sem o campo mode continuam no acesso privado antigo. Para mudar o modo, execute o configurador.

Se a planilha já está aberta pelo link, o modo 2 não muda essa permissão. Para fechar o acesso online, ajuste Acesso geral para Restrito no Google.

Guarde dados e credenciais somente no computador servidor. A interface HTTP não serve as pastas `dados` ou `segredos`. Isso não impede o acesso por alguém que tenha acesso aos arquivos desse computador. Os usuários do Jarvis podem consultar os horários que ele mostra.

## Estrutura

O formato 1 lê suas quatro abas existentes: `Horário DS1`, `Disciplinas`, `Turmas` e `Professores`. Não é necessário renomeá-las nem criar tabelas `agv_*`.

`Horário DS1.Aula` busca `Disciplinas.ID`. O cadastro de Disciplinas informa a matéria, a turma e o professor. `Turmas.N° Salas` informa a sala padrão da turma. O professor é relacionado ao nome completo de `Professores.Nome Prof`. Uma abreviação só é aceita se identificar uma única pessoa. Os avisos aparecem no diagnóstico do responsável. A coluna Matéria da aba Professores é descritiva e não faz parte desse vínculo.

As colunas Disciplina e Professor de Horário DS1 podem continuar com PROCV. O Jarvis usa o cadastro diretamente e avisa se essas fórmulas divergirem. Uma linha sem dia, horário inicial, código de aula ou sala é ignorada quando C está vazia ou contém erro de fórmula, mesmo se E/F também mostrarem #N/A. Uma linha parcialmente preenchida gera erro com aba e número da linha.

A tabela Entrada/Saída em `Turmas!E:F` é independente dos cadastros de turma/sala em A:B. Não ordene A:F como uma única tabela. Ela pode continuar alimentando a fórmula do horário final; o Jarvis lê o resultado em Horário DS1.

Você pode adicionar uma coluna `Sala` em Horário DS1 para indicar laboratório, quadra ou outra sala naquela aula. Se vazia, usa N° Salas de Turmas. Interpretei essa coluna como o número da sala, não como quantidade de salas. A coluna opcional `Ativo` permite excluir uma aula da consulta com FALSO.

O formato 2 mantém compatibilidade com as cinco tabelas anteriores `agv_*`. **O pacote não traz mais nenhuma planilha de exemplo.** A pasta de exemplo e o XLSX fictício de 100 aulas que vinham no ZIP foram apagados: os testes agora geram a planilha de que precisam, com openpyxl, em pasta temporária. Assim nenhum dado inventado é distribuído junto do programa.

Esta versão lê uma única aba de grade, configurada em `google_sheets.tabs.aulas`. Se acrescentar outras turmas, coloque as aulas nessa mesma aba; novas abas de grade não são descobertas automaticamente.

O cache é em memória por 60 segundos. Nos modos online, mudanças aparecem na primeira consulta depois desse prazo. No modo 2 existe uma cópia persistente em dados/grade.xlsx, que você precisa atualizar baixando outro arquivo e selecionando-o no configurador. O Jarvis não recalcula fórmulas; usa os resultados salvos pelo Google. Uma leitura que falhar não retorna um cache vencido como se estivesse atualizado. Perguntas gerais e a hora continuam funcionando sem acesso ao Google. Horários online dependem da conexão; o modo 2 usa o arquivo local. Todos exigem dados válidos.

O teste detecta cabeçalhos ausentes, códigos duplicados, nomes ambíguos, referências inexistentes, horários inválidos e sobreposição de professor, turma ou sala no mesmo dia. Linhas totalmente vazias e aulas com Ativo=FALSO são ignoradas. Sem Ativo ou com valor vazio, a aula é ativa. Consulte `SUA-PLANILHA.md` para a avaliação do que já está cadastrado e os ajustes recomendados.

## Conexão sem Cloud desta atualização

- `jarvis/sheets.py`: modo public baixa o XLSX pelo link e modo file lê a cópia local, preservando linhas, horas e valores calculados. Os dois usam o mesmo relacionamento já existente.
- `jarvis/configurar_planilha.py`: opções 1 (link sem JSON), 2 (XLSX local) e 3 (JSON antigo); gravação local com cópia da configuração anterior.
- `tests/test_without_cloud.py`: leitura, configuração, transporte, cache e falhas dos novos modos. A rota de dados continua bloqueada pela interface HTTP.
- `GUIA-GOOGLE-PLANILHAS.html`: guia principal sem Cloud; `GUIA-CONTA-GOOGLE.html`: instruções opcionais do modo 3.
- Interface e contratos de API não foram alterados. No modo local, o rótulo da fonte passa a ser Planilha local, mantendo os mesmos campos.

## Ajustes anteriores na leitura da grade

- `jarvis/sheets.py`: ignora fórmulas de horário final nas linhas separadoras vazias, informa o campo ausente em aulas incompletas e separa a tabela auxiliar Entrada/Saída dos cadastros de Turmas.
- `jarvis/configurar_planilha.py` e `config.exemplo.json`: sugerem a nova aba `Horário DS1`.
- `tests/test_horarios.py`: cobre esses casos, o nome novo e horas numéricas calculadas por fórmula.
- Interface, logo, modelo, vozes e dependências permanecem iguais.

## Adaptação à estrutura da planilha

- `jarvis/sheets.py`: novo perfil `horarios`, leitura das quatro abas e relacionamentos por código/nome. Autenticação oficial, escopo somente leitura, cache e tratamento de erros mantidos.
- `jarvis/school.py`: aceita turma `1 DS`, `1°Ds` ou `1º DS`; separa nomes de professores de palavras de dia/horário.
- `jarvis/configurar_planilha.py`: seu link já é sugerido; formato 1 seleciona as quatro abas reais. A chave é configurada somente no seu computador.
- `jarvis/testar_planilha.py`: mostra avisos sobre abreviações e fórmulas de exibição. A fonte oficial da consulta é o cadastro relacionado.
- Contratos de `/api/status`, `/api/chat` e `/api/tts`, interface, logo, Qwen e vozes preservados em relação à versão anterior com Google Planilhas.
- Os antigos atalhos `.bat` foram unificados em `Jarvis.py`, que roda no Windows (`py Jarvis.py`) e no Termux (`python Jarvis.py`). Dependências novas: `openpyxl` (gerar a planilha de exemplo nos testes), `numpy` e `sounddevice` (acionamento por palma).

## Rede e executável

No computador principal, `python Jarvis.py rede` (opção 6 do menu) permite acesso pela rede local com a porta 8000 autorizada pelo responsável de TI. Os alunos abrem `http://IP-DO-PC:8000`. Esta entrega não adiciona login nem publicação na internet.

`python Jarvis.py exe` (opção 8 do menu) gera `dist/JarvisAGV`. Depois, copie `config.json` e a pasta correspondente ao modo escolhido (`dados` no modo 2 ou `segredos` no modo 3) para o lado de `JarvisAGV.exe`, somente no computador servidor. O Ollama continua separado. O caminho recomendado continua ser executar o `Jarvis.py`.

## Abrir com duas palmas

`python Jarvis.py palma` liga um escutador do microfone. Bata duas palmas e o Jarvis sobe (se ainda não estiver de pé) e abre no navegador.

Para iniciar junto com o Windows sem janela de console, crie em `shell:startup` (Windows+R) um atalho para `pythonw.exe` com o caminho do `Jarvis.py` e o argumento `palma`:

```
"C:\...\Python312\pythonw.exe" "C:\Jarvis AGV\Jarvis.py" palma
```

Para desativar, apague esse atalho.

**Privacidade:** nenhum áudio é gravado, salvo ou enviado. De cada pedaço curto do microfone o programa calcula apenas o pico de volume, um número, em memória, e descarta o pedaço.

**Como a palma é reconhecida:** um som que passa do limiar vindo do silêncio, que cai abaixo do limiar de queda dentro de 150 ms e cuja cauda dura ao menos 20 ms. Essa duração mínima é o que separa a palma de um clique de teclado, que termina em poucos milissegundos. Duas palmas separadas por 150 a 700 ms acionam; depois disso há 10 segundos de espera antes de aceitar outra sequência.

**Ajustes:** ficam na seção `palma` de `jarvis/config.json` (veja `config.exemplo.json`). `limiar` menor fica mais sensível; maior fica mais exigente. Também é possível escolher o microfone em `dispositivo`, por número ou nome.

Sem microfone ou sem a biblioteca de áudio, o escutador escreve o motivo e encerra, sem travar nada.

## Verificações

Passaram **59 testes Python** nesta atualização. A leitura real pelo link também foi confirmada, sem login ou JSON, recebendo as quatro abas. A validação continua apontando B14 vazio. O arquivo real de 16/10/2026 tem 30 registros de aulas: 29 completos e um com Horario Inicial vazio, em Horário DS1!B14. A leitura detectou essa pendência corretamente. Não alterei a planilha online.

Para validar o restante, somente numa cópia em memória, marquei a linha incompleta como inativa. As outras 29 aulas passaram pelas verificações de referências, horários e conflitos: seis na segunda, cinco na terça, seis na quarta, seis na quinta e seis na sexta. As quatro linhas separadoras com fórmulas foram ignoradas com aviso. A consulta de terça das 7:45 às 8:35 encontrou Geografia e Educação Física. Essa simulação não resolve nem exclui a linha na sua planilha: preencha B14 antes do uso.

Os testes distribuídos usam nomes fictícios. Os testes JavaScript de voz e preferências passaram na versão anterior, e esses arquivos não foram alterados. O transporte autenticado do modo 3 continua simulado nos testes; a conta de serviço real será confirmada por `python Jarvis.py testar` no seu computador. Scripts Windows, áudio real e Ollama real não foram executados aqui.

Comandos: `python -m unittest discover -s tests -v`, `node tests/test_speech.cjs`, `node tests/test_ui_preferences.cjs`.
