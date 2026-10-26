"""Planilha de exemplo gerada em código, para os testes.

Substitui o XLSX fictício que era distribuído junto do projeto. Nada aqui é
dado real da escola: são quatro abas no formato 1 (Horário DS1, Disciplinas,
Turmas e Professores) com nomes inventados, criadas em diretório temporário.

Use `arquivo_temporario()` quando o teste precisar de um .xlsx em disco, ou
`tabelas()` quando bastar o conteúdo.
"""
import tempfile
from contextlib import contextmanager
from pathlib import Path

DIAS = ('Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta')
FAIXAS = (('07:45', '08:35'), ('08:35', '09:25'), ('09:45', '10:35'))
TURMAS = (('1°Ds', 2), ('2°Ds', 3))
PROFESSORES = (
    ('Ana Silva', 'Banco de Dados'),
    ('Bruno Costa', 'Matemática'),
    ('Carla Dias', 'Geografia'),
)
# Uma disciplina por turma, para que cada aula tenha professor e sala definidos.
DISCIPLINAS = tuple(
    (f'{sigla}{turma}', nome, sigla, turma, professor)
    for sigla, nome, professor in (
        ('BD', 'Banco de Dados', 'Ana Silva'),
        ('MT', 'Matemática', 'Bruno Costa'),
        ('GE', 'Geografia', 'Carla Dias'),
    )
    for turma, _ in TURMAS
)
TOTAL_AULAS = len(DIAS) * len(FAIXAS) * len(TURMAS)


def tabelas():
    """As quatro abas do formato 1, como listas de linhas."""
    aulas = [['Dia da semana', 'Horario Inicial', 'Horario final', 'Aula', 'Disciplina', 'Professor']]
    for dia in DIAS:
        for posicao, (inicio, fim) in enumerate(FAIXAS):
            for indice, (turma, _) in enumerate(TURMAS):
                # Gira as disciplinas para que cada turma tenha uma grade variada.
                sigla, nome, professor = (
                    ('BD', 'Banco de Dados', 'Ana Silva'),
                    ('MT', 'Matemática', 'Bruno Costa'),
                    ('GE', 'Geografia', 'Carla Dias'),
                )[(posicao + indice) % 3]
                aulas.append([dia, inicio, fim, f'{sigla}{turma}', nome, professor])
    return {
        'professores': [['Nome Prof', 'Matéria'], *[list(item) for item in PROFESSORES]],
        'materias': [['ID', 'Disciplina', 'Resumo disciplina', 'Turma', 'Professor'],
                     *[list(item) for item in DISCIPLINAS]],
        'turmas': [['Turmas', 'N° Salas'], *[list(item) for item in TURMAS]],
        'aulas': aulas,
    }


def escrever(destino, dados=None):
    """Grava o .xlsx com openpyxl. Os nomes das abas são os do formato 1."""
    from openpyxl import Workbook

    from jarvis import sheets

    dados = dados or tabelas()
    livro = Workbook()
    livro.remove(livro.active)
    for chave, nome in sheets.SCHOOL_TABS.items():
        aba = livro.create_sheet(title=nome)
        for linha in dados[chave]:
            aba.append(list(linha))
    destino = Path(destino)
    livro.save(destino)
    return destino


@contextmanager
def arquivo_temporario(dados=None):
    """Cria a planilha num diretório temporário e apaga ao sair."""
    with tempfile.TemporaryDirectory() as pasta:
        yield escrever(Path(pasta) / 'exemplo-formato-1.xlsx', dados)
