"""Regressões do formato Horarios, com pessoas fictícias."""
import copy
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from jarvis import configurar_planilha
from jarvis import school
from jarvis import sheets


def sample():
    return {
        'professores': [['Nome Prof', 'Matéria'], ['Ana Silva', 'Banco de Dados'],
                        ['Ana Silva', 'Introdução a Computação'], ['Bruno Costa', 'Matemática']],
        'materias': [['ID', 'Disciplina', 'Resumo disciplina', 'Turma', 'Professor'],
                     ['BD1°Ds', 'Banco de Dados', 'BD', '1°Ds', 'Ana'],
                     ['MT1°Ds', 'Matemática', 'MT', '1°Ds', 'Bruno Costa'],
                     ['MT2°Ds', 'Matemática', 'MT', '2°Ds', 'Bruno Costa']],
        'turmas': [['Turmas', 'N° Salas'], ['1°Ds', 2], ['2°Ds', 3]],
        'aulas': [['Dia da semana', 'Horario Inicial', 'Horario final', 'Aula', 'Disciplina', 'Professor'],
                  ['Segunda', 450 / 1440, 500 / 1440, 'BD1°Ds', 'Banco de Dados', 'Ana'],
                  ['Segunda', '8:20', '9:10', 'MT1°Ds', 'Matemática', 'Bruno Costa'],
                  ['', '', '', '', '#N/A', '#N/A']],
    }


def parse(tables):
    return sheets.parse_tables(tables, layout='horarios')


class HorariosTests(unittest.TestCase):
    def test_four_tabs_join_the_real_layout_with_unique_prefixes(self):
        data = parse(sample())
        row = data['rows'][0]
        self.assertEqual((row['inicio'], row['fim'], row['professor'], row['turma'], row['sala']),
                         ('07:30', '08:20', 'Ana Silva', '1°Ds', '2'))
        self.assertEqual(data['counts']['professores'], 2)  # Uma pessoa, várias matérias.
        self.assertEqual(data['counts']['aulas'], 2)
        self.assertEqual(data['counts']['linhas_sem_aula'], 1)
        self.assertTrue(any('linha 4' in warning for warning in data['warnings']))

    def test_reordering_and_formula_disagreements_do_not_change_relations(self):
        tables = sample()
        tables['materias'][1:] = list(reversed(tables['materias'][1:]))
        tables['turmas'][1:] = list(reversed(tables['turmas'][1:]))
        tables['aulas'][1][4:] = ['#N/A', 'Outra pessoa']
        data = parse(tables)
        self.assertEqual(data['rows'][0]['materia'], 'Banco de Dados')
        self.assertEqual(data['rows'][0]['professor'], 'Ana Silva')
        self.assertEqual(sum('diverge' in w for w in data['warnings']), 2)

    def test_partial_rows_and_unknown_codes_fail_clearly(self):
        for row in (['Segunda'], ['Segunda', '7:30', '8:20', 'INEXISTENTE'],
                    ['Segunda', '#N/A', '8:20', 'BD1°Ds']):
            tables = sample()
            tables['aulas'].append(row)
            with self.subTest(row=row), self.assertRaisesRegex(sheets.SheetsError, 'Horarios, linha 5'):
                parse(tables)

    def test_end_formula_on_empty_row_is_ignored_but_missing_start_is_not(self):
        tables = sample()
        tables['aulas'][-1][2] = '#N/A'
        self.assertEqual(parse(tables)['counts']['aulas'], 2)
        tables['aulas'].append(['Terça-feira', '', '#N/A', 'BD1°Ds', 'Banco de Dados', 'Ana'])
        with self.assertRaisesRegex(sheets.SheetsError, 'linha 5: o campo Horario Inicial está vazio'):
            parse(tables)
        tables['aulas'][-1] = ['', '', '8:20', '', '', '']
        with self.assertRaisesRegex(sheets.SheetsError, 'Dia da semana está vazio'):
            parse(tables)

    def test_auxiliary_time_table_is_independent_from_classes(self):
        tables = sample()
        tables['turmas'][0].extend(['', '', 'Entrada', 'Saída'])
        tables['turmas'].append(['', '', '', '', 0.5, 0.5347222222])
        self.assertEqual(parse(tables)['counts']['turmas'], 2)
        tables['turmas'][-1][1] = 9
        with self.assertRaisesRegex(sheets.SheetsError, 'Turmas, linha 4'):
            parse(tables)

    def test_new_sheet_name_and_rounded_formula_times(self):
        tables = sample()
        tables['aulas'][1][2] = 0.3472222222
        tables['aulas'][2][2] = 0.3819444444
        result = sheets.parse_tables(tables, sheets.SCHOOL_TABS, 'horarios')
        self.assertEqual(result['rows'][0]['fim'], '08:20')
        self.assertEqual(result['rows'][1]['fim'], '09:10')
        self.assertTrue(any('Horário DS1' in w for w in result['warnings']))

    def test_duplicate_ids_missing_class_and_ambiguous_teacher_rejected(self):
        tables = sample()
        tables['materias'].append(copy.deepcopy(tables['materias'][1]))
        with self.assertRaisesRegex(sheets.SheetsError, 'duplicado'):
            parse(tables)
        tables = sample()
        tables['materias'][1][3] = '9°Ds'
        with self.assertRaisesRegex(sheets.SheetsError, 'turma não encontrada'):
            parse(tables)
        tables = sample()
        tables['professores'].append(['Ana Souza', 'Banco de Dados'])
        with self.assertRaisesRegex(sheets.SheetsError, 'ambíguo'):
            parse(tables)

    def test_two_teachers_sharing_prefix_require_a_full_name(self):
        tables = sample()
        tables['professores'].append(['Ana Souza', 'Banco de Dados'])
        tables['materias'][1][4] = 'Ana Silva'
        self.assertEqual(parse(tables)['rows'][0]['professor'], 'Ana Silva')

    def test_room_override_and_inactive_unfinished_rows(self):
        tables = sample()
        tables['aulas'][0].extend(['Sala', 'Ativo'])
        tables['aulas'][1].extend(['Laboratório 1', True])
        tables['aulas'].append(['Segunda', '', '', '', '', '', '', False])
        data = parse(tables)
        self.assertEqual(data['rows'][0]['sala'], 'Laboratório 1')
        self.assertEqual(data['counts']['aulas_inativas'], 1)
        self.assertEqual(data['counts']['salas'], 3)

    def test_conflicts_include_room_number_aliases(self):
        tables = sample()
        tables['aulas'][0].append('Sala')
        tables['aulas'].append(['Segunda', '7:30', '8:20', 'MT2°Ds', '', '', 'Sala 02'])
        with self.assertRaisesRegex(sheets.SheetsError, 'conflito de sala'):
            parse(tables)
        tables['aulas'][-1][-1] = '3'
        self.assertEqual(parse(tables)['counts']['aulas'], 3)

    def test_actual_question_formats_and_missing_day(self):
        rows = parse(sample())['rows']
        with patch.object(school, 'schedule_rows', side_effect=lambda day: [r for r in rows if r['dia'] == day]):
            for name in ('1 DS', '1°Ds', '1º DS'):
                result = school.school_answer(f'Quais aulas da turma {name} segunda das 7:45 às 8:35?', datetime(2026, 10, 15, 12))
                self.assertIn('Banco de Dados', result)
                self.assertIn('Matemática', result)
            result = school.school_answer('Onde está a professora Ana segunda às 7:45?', datetime(2026, 10, 15, 12))
            self.assertIn('Ana Silva', result)
            self.assertIn('sala 2', result)
            self.assertNotIn('Bruno', result)
            self.assertIn('terça-feira na planilha', school.school_answer('Quais aulas terça?'))

    def test_wizard_and_configuration_keep_the_selected_layout(self):
        account = {'type':'service_account', 'private_key':'-----BEGIN PRIVATE KEY-----\nFAKE TEST ONLY',
                   'client_email':'jarvis@test-project.iam.gserviceaccount.com', 'token_uri':sheets.TOKEN_URI}
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / 'download.json'
            source.write_text(json.dumps(account), encoding='utf-8')
            with patch.object(configurar_planilha, 'DATA', folder):
                configurar_planilha.save_configuration(sheets.SCHOOL_SHEET_ID, source, layout='horarios')
            payload = json.loads((folder / 'config.json').read_text(encoding='utf-8'))
            with patch.object(sheets, 'DATA', folder), patch.object(sheets, 'read_config', return_value=payload):
                options = sheets.configuration()
            self.assertEqual(options['layout'], 'horarios')
            self.assertEqual(options['tabs'], sheets.HORARIOS_TABS)
            self.assertNotIn('private_key', json.dumps(payload))

    def test_transport_reads_four_tabs_and_snapshot_selects_adapter(self):
        client = sheets.GoogleClient.__new__(sheets.GoogleClient)
        client.expected_errors = (TimeoutError,)
        client.session = MagicMock()
        response = client.session.get.return_value.__enter__.return_value
        response.status_code = 200
        response.content = b'{}'
        response.json.return_value = {'valueRanges':[{'values':v} for v in sample().values()]}
        options = {'id':'a'*30, 'tabs':sheets.HORARIOS_TABS, 'layout':'horarios',
                   'ttl':60, 'path':Path('unused'), 'key':('horarios-test',)}
        with patch.object(sheets, 'configuration', return_value=options), patch.object(sheets, 'GoogleClient', return_value=client), \
             patch.object(sheets, '_client', None), patch.object(sheets, '_client_key', None), \
             patch.object(sheets, '_cache_key', None), patch.object(sheets, '_cache_data', None), \
             patch.object(sheets, '_last_error', None):
            result = sheets.snapshot(force=True)
        self.assertEqual(result['counts']['aulas'], 2)
        params = client.session.get.call_args.kwargs['params']
        self.assertEqual(len([p for p in params if p[0] == 'ranges']), 4)


if __name__ == '__main__':
    unittest.main()
