"""Garantias contra inventar dados da escola (item 3).

Sem dado vindo da consulta de grade, o Jarvis responde que não tem a
informação. O modelo não é chamado para preencher a lacuna.
"""
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from email.message import Message
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from jarvis import app
from jarvis import school
from jarvis import sheets


def pedir(path, data=None):
    """Executa uma requisição no Handler sem abrir porta de rede."""
    handler = app.Handler.__new__(app.Handler)
    handler.path = path
    handler.command = 'GET' if data is None else 'POST'
    handler.request_version = 'HTTP/1.1'
    handler.requestline = f'{handler.command} {path} HTTP/1.1'
    handler.client_address = ('127.0.0.1', 0)
    handler.log_message = lambda *args: None
    body = b'' if data is None else json.dumps(data).encode()
    handler.rfile = io.BytesIO(body)
    handler.wfile = io.BytesIO()
    handler.headers = Message()
    handler.headers['Content-Type'] = 'application/json'
    handler.headers['Content-Length'] = str(len(body))
    handler.headers['Host'] = 'localhost:8000'
    (handler.do_GET if data is None else handler.do_POST)()
    return handler.wfile.getvalue()


class PromptTests(unittest.TestCase):
    def sistema(self, language):
        pedido = app.model_request('Qual a aula de amanhã?', [], language)
        return json.loads(pedido.data)['messages'][0]['content']

    def test_prompt_forbids_inventing_schedule_teacher_room_group_and_date(self):
        texto = self.sistema('pt-BR')
        for proibido in ('horário', 'professor', 'sala', 'turma'):
            self.assertIn(proibido, texto)
        self.assertIn('nunca inventa', texto)
        self.assertIn('não tem essa informação', texto)
        self.assertIn('responsável', texto)

    def test_prompt_rule_exists_in_english_too(self):
        texto = self.sistema('en-US')
        self.assertIn('never invent school data', texto)
        self.assertIn('do not have that information', texto)

    def test_prompt_still_allows_helping_with_subjects(self):
        self.assertIn('explicar matéria', self.sistema('pt-BR'))

    def test_model_keeps_receiving_the_absolute_date(self):
        self.assertIn('verdade absoluta', self.sistema('pt-BR'))


class SemDadosTests(unittest.TestCase):
    def test_empty_spreadsheet_answers_no_data_without_calling_the_model(self):
        with patch.object(school, 'schedule_rows', return_value=[]), \
                patch.object(app, 'open_model', side_effect=AssertionError('o modelo não deve ser chamado')):
            resposta = school.school_answer('Quais aulas de terça?', datetime(2026, 10, 5, 7, 45))
        self.assertIn('na planilha', resposta)
        self.assertNotIn(':', resposta.replace('07:', '').replace('08:', ''))

    def test_unconfigured_spreadsheet_returns_an_error_instead_of_a_guess(self):
        erro = sheets.SheetsError(
            'A planilha ainda não foi conectada. O responsável precisa executar Jarvis.py, opção 2 (Configurar planilha).',
            'sheets_not_configured')
        with patch.object(school, 'schedule_rows', side_effect=erro), \
                patch.object(app, 'open_model', side_effect=AssertionError('o modelo não deve ser chamado')):
            bruto = pedir('/api/chat', {'mensagem': 'Quais aulas de terça?'})
        self.assertIn(b'503', bruto.split(b'\r\n')[0])
        corpo = json.loads(bruto.split(b'\r\n\r\n', 1)[1])
        self.assertEqual(corpo['codigo'], 'sheets_not_configured')
        # A mensagem pública é amigável, mas continua dizendo que não há dados.
        self.assertIn('não foram conectados', corpo['erro'])
        for inventado in ('07:', '08:', 'Segunda', 'Terça'):
            self.assertNotIn(inventado, corpo['erro'])

    def test_general_questions_still_reach_the_model(self):
        with patch.object(school, 'schedule_rows', side_effect=AssertionError('não consulta a planilha')), \
                patch.object(app, 'open_model',
                             return_value=io.BytesIO(b'{"message":{"content":"Resposta."},"done":true}\n')):
            bruto = pedir('/api/chat', {'mensagem': 'Explique fotossíntese.'})
        self.assertIn(b'"texto": "Resposta."', bruto)


class PortaOcupadaTests(unittest.TestCase):
    def test_a_busy_port_gives_a_clear_message_instead_of_a_traceback(self):
        with patch.object(app, 'ThreadingHTTPServer', side_effect=OSError('Address already in use')), \
                patch.object(app.voice, 'available', return_value=False), \
                redirect_stdout(io.StringIO()) as saida:
            self.assertEqual(app.main(), 1)
        texto = saida.getvalue()
        self.assertIn('porta 8000', texto)
        self.assertIn('http://127.0.0.1:8000', texto)
        self.assertNotIn('Traceback', texto)


class PlanilhaFicticiaTests(unittest.TestCase):
    def test_no_fictional_workbook_is_shipped_with_the_project(self):
        raiz = Path(__file__).resolve().parents[2]
        self.assertEqual(list(raiz.rglob('Jarvis_AGV_Base_Relacional*')), [])
        self.assertEqual(list(raiz.rglob('planilha-modelo')), [])
        self.assertEqual([p for p in raiz.rglob('*.xlsx') if '.venv' not in p.parts], [])


if __name__ == '__main__':
    unittest.main()
