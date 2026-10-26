import copy
import io
import json
import sys
import tempfile
import threading
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from jarvis import app
from jarvis import school
from jarvis import sheets
from jarvis import configurar_planilha
import planilha_exemplo


def sample():
    return {
        'professores': [['id', 'nome'], [1, 'Ana Silva'], [2, 'João Pedro']],
        'materias': [['id', 'nome'], [1, 'Português'], [2, 'Matemática']],
        'turmas': [['id', 'nome'], [1, '1A'], [2, '2B']],
        'salas': [['id', 'nome'], [1, 'Sala Aurora'], [2, 'Sala Horizonte']],
        'aulas': [['id','professor_id','materia_id','turma_id','sala_id','dia','inicio','fim','ativo'],
                  [1,1,1,1,1,1,465/1440,515/1440,True],
                  [2,1,2,1,1,1,'8:35','9:25',True],
                  [3,2,2,2,2,1,'7:45','8:35',False]],
    }


class RelationTests(unittest.TestCase):
    def test_joins_serial_times_and_inactive(self):
        data = sheets.parse_tables(sample())
        self.assertEqual(data['counts']['aulas'], 2)
        self.assertEqual(data['counts']['aulas_inativas'], 1)
        self.assertEqual(data['rows'][0]['inicio'], '07:45')
        self.assertEqual(data['rows'][0]['professor'], 'Ana Silva')
        self.assertEqual(data['rows'][1]['inicio'], '08:35')

    def test_sorting_entity_rows_does_not_change_relations(self):
        tables = sample()
        tables['professores'][1:] = list(reversed(tables['professores'][1:]))
        self.assertEqual(sheets.parse_tables(tables)['rows'][0]['professor'], 'Ana Silva')
        tables['professores'][2][1] = 'Ana Silva Souza'
        self.assertEqual(sheets.parse_tables(tables)['rows'][0]['professor'], 'Ana Silva Souza')

    def test_invalid_fk_and_duplicate_id_are_visible(self):
        tables = sample()
        tables['aulas'][1][1] = 999
        with self.assertRaisesRegex(sheets.SheetsError, 'professor_id não encontrado'):
            sheets.parse_tables(tables)
        tables = sample()
        tables['professores'].append([1, 'Outra pessoa'])
        with self.assertRaisesRegex(sheets.SheetsError, 'ID duplicado'):
            sheets.parse_tables(tables)

    def test_unfinished_inactive_row_is_ignored_blank_rows_are_safe(self):
        tables = sample()
        tables['aulas'].extend([[], ['', '', ''], [999, '', '', '', '', '', '', '', False]])
        self.assertEqual(sheets.parse_tables(tables)['counts']['aulas'], 2)
        tables['aulas'][-1][-1] = True
        with self.assertRaises(sheets.SheetsError):
            sheets.parse_tables(tables)

    def test_missing_headers_bad_times_and_dates(self):
        for column, value in [(5,7), (6,'27:00'), (7,'07:45'), (8,'talvez')]:
            tables = sample()
            tables['aulas'][1][column] = value
            with self.subTest(column=column), self.assertRaises(sheets.SheetsError):
                sheets.parse_tables(tables)
        tables = sample(); tables['aulas'][0][1] = 'outro'
        with self.assertRaisesRegex(sheets.SheetsError, 'cabeçalhos'):
            sheets.parse_tables(tables)

    def test_overlaps_rejected_but_touching_intervals_allowed(self):
        tables = sample()
        self.assertEqual(len(sheets.parse_tables(tables)['rows']), 2)
        tables['aulas'][2][6] = '08:20'
        with self.assertRaisesRegex(sheets.SheetsError, 'sobrepõem'):
            sheets.parse_tables(tables)

    def test_generated_example_workbook_and_user_interval_query(self):
        """Lê um .xlsx gerado em código (formato 1), sem planilha fictícia no pacote."""
        with planilha_exemplo.arquivo_temporario() as arquivo:
            tables = sheets.read_workbook(arquivo.read_bytes(), sheets.SCHOOL_TABS)
        data = sheets.parse_tables(tables, sheets.SCHOOL_TABS, 'horarios')
        self.assertEqual(data['counts']['aulas'], planilha_exemplo.TOTAL_AULAS)
        with patch.object(school, 'schedule_rows', side_effect=lambda d: [r for r in data['rows'] if r['dia'] == d]):
            result = school.school_answer('Quais são as aulas de terça-feira das 7:45 às 8:35?', datetime(2026,10,5,10))
            self.assertIn('07:45', result)
            self.assertIn('turma', result)

    def test_named_room_and_time_question_use_schedule(self):
        rows = sheets.parse_tables(sample())['rows']
        with patch.object(school, 'schedule_rows', return_value=rows) as read:
            answer = school.school_answer('Quais aulas na sala Aurora terça?', datetime(2026,10,6,7,45))
            self.assertIn('Ana Silva', answer)
            answer = school.school_answer('Que horas é a aula da turma 1A terça?', datetime(2026,10,6,7,45))
            self.assertIn('Grade', answer)
            self.assertEqual(read.call_count, 2)

    def test_clock_and_general_questions_never_need_google(self):
        with patch.object(school, 'schedule_rows', side_effect=AssertionError('Consulta indevida')):
            self.assertIn('14:32', school.school_answer('Que horas são?', datetime(2026,10,6,14,32)))
            self.assertIsNone(school.school_answer('O que é fotossíntese?'))
            self.assertIsNone(school.school_answer('O que é uma aula?'))

    def test_relative_days(self):
        with patch.object(school, 'schedule_rows', return_value=[]) as read:
            for question, language, expected in [('Quais aulas hoje?', 'pt-BR', 6), ('Quais aulas amanhã?', 'pt-BR', 0), ('Which classes yesterday?', 'en-US', 5)]:
                school.school_answer(question, datetime(2026,10,11,10), language)
                self.assertEqual(read.call_args.args[0], expected)


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(patch.stopall)
        for name, value in {'_cache_key':None,'_cache_data':None,'_expires':0,'_last_sync':None,'_last_error':None,'_retry_at':0,'_client':None,'_client_key':None}.items():
            patch.object(sheets, name, value).start()
        self.options = {'id':'a'*30,'path':Path('private.json'),'tabs':sheets.DEFAULT_TABS,'ttl':60,'key':('test',)}
        patch.object(sheets,'configuration',side_effect=lambda:self.options).start()
        self.client = MagicMock()
        self.client.read.side_effect = lambda options: sample()
        self.factory = patch.object(sheets,'GoogleClient',return_value=self.client).start()
        self.clock = patch.object(sheets.time,'monotonic',return_value=100).start()

    def test_cache_is_shared_and_returns_independent_rows(self):
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _:sheets.snapshot(),range(12)))
        self.assertEqual(self.client.read.call_count,1)
        results[0]['rows'][0]['professor'] = 'Alterado'
        self.assertEqual(sheets.snapshot()['rows'][0]['professor'],'Ana Silva')
        self.assertEqual(sheets.status()['state'],'connected')

    def test_expiry_failed_refresh_never_returns_old_schedule(self):
        sheets.snapshot()
        self.clock.return_value=161
        self.client.read.side_effect=sheets.SheetsError('Sem internet','sheets_connection')
        for _ in range(2):
            with self.assertRaises(sheets.SheetsError):sheets.snapshot()
        self.assertEqual(self.client.read.call_count,2)
        self.assertEqual(sheets.status()['state'],'error')

    def test_changed_config_invalidates_cache(self):
        sheets.snapshot()
        self.options={**self.options,'key':('other',)}
        sheets.snapshot()
        self.assertEqual(self.client.read.call_count,2)
        self.assertEqual(self.factory.call_count,2)


class ConfigAndHttpTests(unittest.TestCase):
    def test_links_and_private_paths(self):
        sid='abc_'+'9'*30
        self.assertEqual(sheets.spreadsheet_id(f'https://docs.google.com/spreadsheets/d/{sid}/edit?gid=0'),sid)
        for bad in ('bad','https://example.com/spreadsheets/d/'+sid+'/edit'):
            with self.assertRaises(sheets.SheetsError):sheets.spreadsheet_id(bad)
        config={'google_sheets':{'spreadsheet_id':sid,'credentials_file':str(sheets.ROOT/'web/private.json')}}
        with patch.object(sheets,'read_config',return_value=config),self.assertRaisesRegex(sheets.SheetsError,'fora de web'):
            sheets.configuration()

    def test_not_configured_and_status_do_not_reveal_settings(self):
        with patch.object(sheets,'read_config',return_value={}):
            state=sheets.status()
            self.assertEqual(state['state'],'not_configured')
            self.assertNotIn('credentials',json.dumps(state))

    def test_wizard_writes_only_local_settings_and_keeps_backup(self):
        account={'type':'service_account','private_key':'-----BEGIN PRIVATE KEY-----\nFAKE TEST ONLY', 'client_email':'jarvis@test-project.iam.gserviceaccount.com','token_uri':sheets.TOKEN_URI}
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            source=folder/'download.json';source.write_text(json.dumps(account))
            (folder/'config.json').write_text('{"previous":true}')
            with patch.object(configurar_planilha,'DATA',folder):
                email=configurar_planilha.save_configuration('a'*30,source)
            config=json.loads((folder/'config.json').read_text())
            self.assertEqual(email,account['client_email'])
            self.assertNotIn('private_key',json.dumps(config))
            self.assertTrue(json.loads((folder/'config.anterior.json').read_text())['previous'])
            self.assertTrue((folder/'segredos/conta-google.json').exists())

    def test_credential_endpoint_must_be_google(self):
        with tempfile.TemporaryDirectory() as directory:
            file=Path(directory)/'key.json'
            file.write_text(json.dumps({'type':'service_account','private_key':'-----BEGIN PRIVATE KEY-----','client_email':'jarvis@project.iam.gserviceaccount.com','token_uri':'https://example.com/token'}))
            with self.assertRaises(sheets.SheetsError):sheets.load_account(file)

    def test_http_errors_are_sanitized_and_files_are_private(self):
        from email.message import Message
        def request(path, data=None):
            h=app.Handler.__new__(app.Handler)
            h.path=path;h.command='GET' if data is None else 'POST';h.headers=Message()
            body=json.dumps(data).encode() if data is not None else b''
            h.headers['Content-Type']='application/json';h.headers['Content-Length']=str(len(body))
            h.rfile=io.BytesIO(body)
            with patch.object(h,'send') as send:
                (h.do_GET if data is None else h.do_POST)()
                return send.call_args.args
        for path in ('/config.json','/segredos/conta-google.json','/assets/../segredos/conta-google.json','/config.anterior.json','/dados/grade.xlsx'):
            self.assertEqual(request(path)[0],404)
        with patch.object(app,'school_answer',side_effect=sheets.SheetsError('PRIVATE TEST STRING','sheets_access')):
            status,payload=request('/api/chat',{'mensagem':'Quais aulas hoje?'})
        self.assertEqual(status,503);self.assertEqual(payload['codigo'],'sheets_access')
        self.assertNotIn('PRIVATE',payload['erro'])


class TransportTests(unittest.TestCase):
    def client(self, code=200):
        client=sheets.GoogleClient.__new__(sheets.GoogleClient)
        client.expected_errors=(TimeoutError,)
        client.session=MagicMock()
        response=client.session.get.return_value.__enter__.return_value
        response.status_code=code;response.content=b'{}'
        response.json.return_value={'valueRanges':[{'values':v} for v in sample().values()]}
        return client

    def test_readonly_request_keeps_times_numeric_and_quotes_tab(self):
        client=self.client()
        options={'id':'a'*30,'tabs':{**sheets.DEFAULT_TABS,'professores':"Professor's"}}
        data=client.read(options)
        args,kwargs=client.session.get.call_args
        self.assertTrue(args[0].startswith('https://sheets.googleapis.com/'))
        self.assertIn(('ranges',"'Professor''s'!A:Z"),kwargs['params'])
        self.assertIn(('valueRenderOption','UNFORMATTED_VALUE'),kwargs['params'])
        self.assertFalse(kwargs['allow_redirects'])
        self.assertEqual(data['aulas'][1][6],465/1440)

    def test_provider_errors_hide_response_content(self):
        for code,expected in [(400,'sheets_structure'),(401,'sheets_access'),(403,'sheets_access'),(404,'sheets_access'),(429,'sheets_quota'),(500,'sheets_unavailable')]:
            client=self.client(code)
            with self.subTest(code=code),self.assertRaises(sheets.SheetsError) as error:
                client.read({'id':'a'*30,'tabs':sheets.DEFAULT_TABS})
            self.assertEqual(error.exception.code,expected)


if __name__=='__main__':
    unittest.main()
