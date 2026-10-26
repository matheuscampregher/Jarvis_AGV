import io
import json
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from jarvis import configurar_planilha
from jarvis import sheets
from test_horarios import sample
import planilha_exemplo


def workbook(tables=None):
    tables = tables or sample()
    ns = sheets.XML_NS
    relns = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
    book = ET.Element(ns + 'workbook')
    tabs = ET.SubElement(book, ns + 'sheets')
    rels = ET.Element('Relationships')
    shared = ET.Element(ns + 'sst')
    output = io.BytesIO()
    text_count = 0
    with ZipFile(output, 'w') as archive:
        for i, (key, name) in enumerate(sheets.SCHOOL_TABS.items(), 1):
            rid = 'rId' + str(i)
            ET.SubElement(tabs, ns + 'sheet', {'name': name, relns + 'id': rid})
            ET.SubElement(rels, 'Relationship', {'Id': rid, 'Target': 'worksheets/sheet' + str(i) + '.xml'})
            sheet = ET.Element(ns + 'worksheet')
            data = ET.SubElement(sheet, ns + 'sheetData')
            for line, values in enumerate(tables[key], 1):
                row = ET.SubElement(data, ns + 'row', {'r': str(line)})
                for column, value in enumerate(values):
                    if value is None or value == '':
                        continue
                    cell = ET.SubElement(row, ns + 'c', {'r': chr(65 + column) + str(line)})
                    if isinstance(value, bool):
                        cell.set('t', 'b')
                        value = '1' if value else '0'
                    elif isinstance(value, str) and value.startswith('#'):
                        cell.set('t', 'e')
                        ET.SubElement(cell, ns + 'f').text = 'VLOOKUP(B4,Turmas!E:F,2,0)'
                    elif isinstance(value, str):
                        cell.set('t', 's')
                        ET.SubElement(ET.SubElement(shared, ns + 'si'), ns + 't').text = value
                        value = text_count
                        text_count += 1
                    ET.SubElement(cell, ns + 'v').text = str(value)
            archive.writestr('xl/worksheets/sheet' + str(i) + '.xml', ET.tostring(sheet))
        archive.writestr('xl/sharedStrings.xml', ET.tostring(shared))
        archive.writestr('xl/workbook.xml', ET.tostring(book))
        archive.writestr('xl/_rels/workbook.xml.rels', ET.tostring(rels))
    return output.getvalue()


class WorkbookTests(unittest.TestCase):
    def test_values_line_numbers_and_formula_errors_are_preserved(self):
        tables = sample()
        tables['aulas'][1][1:3] = [450 / 1440, 500 / 1440]
        tables['aulas'][-1][2] = '#N/A'
        tables['aulas'].append([])
        tables['aulas'].append(['Terça', '', '#N/A', 'BD1°Ds'])
        result = sheets.read_workbook(workbook(tables), sheets.SCHOOL_TABS)
        self.assertEqual(result['aulas'][1][1], 450 / 1440)
        self.assertEqual(result['aulas'][3][2], '#N/A')
        self.assertEqual(result['aulas'][4], [])
        with self.assertRaisesRegex(sheets.SheetsError, 'linha 6: o campo Horario Inicial está vazio'):
            sheets.parse_tables(result, sheets.SCHOOL_TABS, 'horarios')

    def test_valid_relations_and_generated_example(self):
        result = sheets.parse_tables(sheets.read_workbook(workbook(), sheets.SCHOOL_TABS), sheets.SCHOOL_TABS, 'horarios')
        self.assertEqual(result['counts']['aulas'], 2)
        # A planilha de exemplo é criada em disco pelo próprio teste, em pasta temporária.
        with planilha_exemplo.arquivo_temporario() as arquivo:
            tables = sheets.read_workbook(arquivo.read_bytes(), sheets.SCHOOL_TABS)
        result = sheets.parse_tables(tables, sheets.SCHOOL_TABS, 'horarios')
        self.assertEqual(result['counts']['aulas'], planilha_exemplo.TOTAL_AULAS)
        self.assertEqual(result['counts']['professores'], len(planilha_exemplo.PROFESSORES))
        self.assertEqual(sorted(sheets.SCHOOL_TABS.values()),
                         ['Disciplinas', 'Horário DS1', 'Professores', 'Turmas'])

    def test_missing_tabs_invalid_file_and_size_limits(self):
        with self.assertRaisesRegex(sheets.SheetsError, 'Abas não encontradas'):
            sheets.read_workbook(workbook(), {'aulas': 'Nome que não existe'})
        with self.assertRaises(sheets.SheetsError):
            sheets.read_workbook(b'<html>Login</html>', sheets.SCHOOL_TABS)
        with patch.object(sheets, 'MAX_WORKBOOK_BYTES', 3):
            with self.assertRaises(sheets.SheetsError) as err:
                sheets.read_workbook(b'1234', sheets.SCHOOL_TABS)
            self.assertEqual(err.exception.code, 'sheets_limit')


class PublicTransportTests(unittest.TestCase):
    def response(self, status=200, content=None, location=None):
        response = MagicMock()
        response.status = status
        response.headers = {'Location': location} if location else {}
        response.read.side_effect = [workbook() if content is None else content, b'']
        response.__enter__.return_value = response
        return response

    def client(self, responses):
        client = sheets.PublicClient.__new__(sheets.PublicClient)
        client.expected_errors = (TimeoutError,)
        client.opener = MagicMock()
        client.opener.open.side_effect = responses
        return client

    def test_read_by_link_and_allowed_export_redirect(self):
        client = self.client([self.response(302, location='https://doc-01-test-sheets.googleusercontent.com/export/a'),
                              self.response()])
        options = {'id': 'a' * 30, 'tabs': sheets.SCHOOL_TABS}
        result = sheets.parse_tables(client.read(options), sheets.SCHOOL_TABS, 'horarios')
        self.assertEqual(result['counts']['aulas'], 2)
        self.assertEqual(client.opener.open.call_count, 2)
        for call in client.opener.open.call_args_list:
            self.assertEqual(call.args[0].get_method(), 'GET')
            self.assertIsNone(call.args[0].get_header('Authorization'))
            self.assertIsNone(call.args[0].get_header('Cookie'))

    def test_login_html_private_sheet_quota_and_timeout(self):
        cases = [(self.response(403), 'sheets_access'), (self.response(429), 'sheets_quota'),
                 (self.response(content=b'<html>Login SECRET</html>'), 'sheets_access'),
                 (self.response(500), 'sheets_unavailable'), (TimeoutError('SECRET'), 'sheets_connection'),
                 (HTTPError('https://docs.google.com/', 403, 'SECRET', {}, io.BytesIO()), 'sheets_access')]
        for response, code in cases:
            with self.subTest(code=code):
                client = self.client([response])
                with self.assertRaises(sheets.SheetsError) as err:
                    client.read({'id': 'a' * 30, 'tabs': sheets.SCHOOL_TABS})
                self.assertEqual(err.exception.code, code)
                self.assertNotIn('SECRET', str(err.exception))

    def test_external_redirect_never_fetched_and_body_is_bounded(self):
        client = self.client([self.response(302, location='http://127.0.0.1/private')])
        with self.assertRaises(sheets.SheetsError):
            client.read({'id': 'a' * 30, 'tabs': sheets.SCHOOL_TABS})
        self.assertEqual(client.opener.open.call_count, 1)
        self.assertFalse(sheets.PublicClient.allowed_url('https://docs.google.com:bad/'))
        self.assertFalse(sheets.PublicClient.allowed_url('https://docs.google.com.evil.test/'))
        client = self.client([self.response(content=b'PK12345')])
        with patch.object(sheets, 'MAX_WORKBOOK_BYTES', 4):
            with self.assertRaises(sheets.SheetsError) as err:
                client.read({'id': 'a' * 30, 'tabs': sheets.SCHOOL_TABS})
            self.assertEqual(err.exception.code, 'sheets_limit')


class SetupTests(unittest.TestCase):
    def test_public_setup_needs_no_key_and_keeps_previous_config_backup(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(configurar_planilha, 'DATA', Path(directory)):
            path = Path(directory)
            (path / 'config.json').write_text('{"old": true}')
            configurar_planilha.save_public_configuration('a' * 30)
            config = json.loads((path / 'config.json').read_text())
            self.assertEqual(config['google_sheets']['mode'], 'public')
            self.assertNotIn('credentials_file', config['google_sheets'])
            self.assertFalse((path / 'segredos').exists())
            self.assertEqual(json.loads((path / 'config.anterior.json').read_text()), {'old': True})
            with patch.object(sheets, 'read_config', return_value=config):
                options = sheets.configuration()
                self.assertIsNone(options['path'])
                self.assertEqual(options['mode'], 'public')

    def test_local_setup_copies_all_tabs_and_tracks_updates(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(configurar_planilha, 'DATA', Path(directory)), patch.object(sheets, 'DATA', Path(directory)):
            path = Path(directory)
            source = path / 'download.xlsx'
            source.write_bytes(workbook())
            configurar_planilha.save_file_configuration(source)
            config = json.loads((path / 'config.json').read_text())
            self.assertEqual(config['google_sheets']['mode'], 'file')
            self.assertNotIn('spreadsheet_id', config['google_sheets'])
            with patch.object(sheets, 'read_config', return_value=config):
                options = sheets.configuration()
                self.assertEqual(options['path'], path / 'dados/grade.xlsx')
                tables = sheets.FileClient().read(options)
                self.assertEqual(sheets.parse_tables(tables, sheets.SCHOOL_TABS, 'horarios')['counts']['aulas'], 2)
                key = options['key']
                with options['path'].open('ab') as stream:
                    stream.write(b' ')
                self.assertNotEqual(sheets.configuration()['key'], key)

    def test_local_data_cannot_be_inside_web(self):
        config = {'google_sheets': {'mode': 'file', 'workbook_file': str(sheets.ROOT / 'web/grade.xlsx')}}
        with patch.object(sheets, 'read_config', return_value=config):
            with self.assertRaisesRegex(sheets.SheetsError, 'fora de web'):
                sheets.configuration()

    def test_public_wizard_does_not_ask_for_json_or_launch_cloud(self):
        data = {'counts': {'aulas': 2}}
        with patch('builtins.input', side_effect=['1', '', '', '']), patch('builtins.print'), \
             patch.object(configurar_planilha, 'choose_file') as pick, \
             patch.object(configurar_planilha, 'save_public_configuration') as save, \
             patch.object(configurar_planilha, 'snapshot', return_value=data):
            self.assertEqual(configurar_planilha.main(), 0)
            pick.assert_not_called()
            self.assertEqual(save.call_args.args[0], sheets.SCHOOL_SHEET_ID)

    def test_public_snapshot_uses_public_client_and_shared_cache(self):
        options = {'mode': 'public', 'id': 'a' * 30, 'path': None, 'key': ('public-test',),
                   'tabs': sheets.SCHOOL_TABS, 'layout': 'horarios', 'ttl': 60}
        reset = {'_cache_key': None, '_cache_data': None, '_client': None, '_client_key': None,
                 '_last_error': None, '_retry_at': 0, '_expires': 0, '_last_sync': None}
        client = MagicMock()
        client.read.return_value = sample()
        with patch.multiple(sheets, **reset), patch.object(sheets, 'configuration', return_value=options), \
             patch.object(sheets, 'PublicClient', return_value=client), patch.object(sheets, 'GoogleClient') as private:
            self.assertEqual(sheets.snapshot()['counts']['aulas'], 2)
            self.assertEqual(sheets.snapshot()['counts']['aulas'], 2)
            self.assertEqual(client.read.call_count, 1)
            private.assert_not_called()
            self.assertEqual(sheets.status()['state'], 'connected')


if __name__ == '__main__':
    unittest.main()
