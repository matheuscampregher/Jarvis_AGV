"""Leitura de uma grade relacional do Google Planilhas.

Conta de serviço, link com leitura liberada ou arquivo XLSX local.
Somente leitura. Credenciais e arquivos ficam no servidor, fora de web.
O cache é em memória, com prazo curto; falhas nunca usam dados vencidos.
"""
import copy
import io
import json
import math
import posixpath
import re
import threading
import time
import unicodedata
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urljoin
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zipfile import BadZipFile, ZipFile

from .settings import DATA, ROOT, read_config

SCOPE = 'https://www.googleapis.com/auth/spreadsheets.readonly'
TOKEN_URI = 'https://oauth2.googleapis.com/token'
DEFAULT_TABS = {
    'professores': 'agv_professores', 'materias': 'agv_materias',
    'turmas': 'agv_turmas', 'salas': 'agv_salas', 'aulas': 'agv_aulas',
}
HORARIOS_TABS = {
    'professores': 'Professores', 'materias': 'Disciplinas',
    'turmas': 'Turmas', 'aulas': 'Horarios',
}
LAYOUT_TABS = {'relacional': DEFAULT_TABS, 'horarios': HORARIOS_TABS}
SCHOOL_SHEET_ID = '1DwHguCj2RcNHXCmfQSdNKFcDM8aw8F7knYl-wNygZcs'
SCHOOL_TABS = {**HORARIOS_TABS, 'aulas': 'Horário DS1'}
FORMULA_ERRORS = frozenset(('#N/A', '#REF!', '#VALUE!', '#DIV/0!', '#NAME?', '#NUM!', '#NULL!', '#ERROR!'))
MAX_WORKBOOK_BYTES = 8 * 1024 * 1024
XML_NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
_LOCK = threading.RLock()
_cache_key = None
_cache_data = None
_expires = 0
_last_sync = None
_last_error = None
_retry_at = 0
_client = None
_client_key = None


class SheetsError(RuntimeError):
    def __init__(self, message, code='sheets_error'):
        super().__init__(message)
        self.code = code

    @property
    def public_message(self):
        if self.code == 'sheets_not_configured':
            return 'Os horários da escola ainda não foram conectados ao Jarvis.'
        if self.code in ('sheets_structure', 'sheets_data', 'sheets_conflict', 'sheets_limit'):
            return 'A planilha da escola precisa de uma correção antes da consulta. Avise o responsável pelo Jarvis.'
        if self.code == 'sheets_quota':
            return 'As consultas à planilha estão temporariamente limitadas. Tente novamente em um minuto.'
        return 'Não consegui consultar a planilha da escola agora. Tente novamente ou avise o responsável pelo Jarvis.'


def normalize(value):
    return ''.join(c for c in unicodedata.normalize('NFD', str(value).strip().lower())
                   if unicodedata.category(c) != 'Mn')


def spreadsheet_id(value):
    value = str(value or '').strip()
    if value.startswith('https://'):
        url = urlparse(value)
        match = re.fullmatch(r'/spreadsheets/(?:u/\d+/)?d/([A-Za-z0-9_-]+)(?:/.*)?', url.path)
        if url.hostname != 'docs.google.com' or not match:
            raise SheetsError('Use o link de uma planilha do Google ou o ID dela.', 'sheets_config')
        value = match[1]
    if not re.fullmatch(r'[A-Za-z0-9_-]{20,200}', value):
        raise SheetsError('O ID da planilha está vazio ou inválido. Execute Jarvis.py, opção 2 (Configurar planilha).', 'sheets_config')
    return value


def configuration():
    try:
        options = read_config().get('google_sheets', {})
    except RuntimeError:
        raise SheetsError('O arquivo config.json é inválido. Execute Jarvis.py, opção 2 (Configurar planilha).', 'sheets_config') from None
    if not isinstance(options, dict):
        raise SheetsError('A seção google_sheets de config.json deve ser um objeto.', 'sheets_config')
    mode = options.get('mode', 'service_account')
    if mode not in ('service_account', 'public', 'file'):
        raise SheetsError('Modo de acesso inválido. Execute Jarvis.py, opção 2 (Configurar planilha).', 'sheets_config')
    if mode != 'file' and not options.get('spreadsheet_id'):
        raise SheetsError('A planilha ainda não foi conectada. O responsável precisa executar Jarvis.py, opção 2 (Configurar planilha).', 'sheets_not_configured')
    sid = spreadsheet_id(options['spreadsheet_id']) if mode != 'file' else None
    path = None
    if mode != 'public':
        file = options.get('workbook_file', 'dados/grade.xlsx') if mode == 'file' else options.get('credentials_file', 'segredos/conta-google.json')
        if not isinstance(file, str) or not file.strip():
            raise SheetsError('Informe o caminho do arquivo no configurador.', 'sheets_config')
        path = (DATA / Path(file).expanduser()).resolve()
        # Nunca aceitar arquivos de dados ou credenciais na pasta pública.
        if path == (ROOT / 'web').resolve() or (ROOT / 'web').resolve() in path.parents:
            raise SheetsError('Guarde o arquivo de dados ou a credencial fora de web.', 'sheets_config')
    layout = options.get('layout', 'relacional')
    if not isinstance(layout, str) or layout not in LAYOUT_TABS:
        raise SheetsError('Formato de planilha inválido. Execute Jarvis.py, opção 2 (Configurar planilha).', 'sheets_config')
    defaults = LAYOUT_TABS[layout]
    custom_tabs = options.get('tabs', {})
    if not isinstance(custom_tabs, dict) or set(custom_tabs) - set(defaults):
        raise SheetsError('Confira os nomes das abas em google_sheets.tabs.', 'sheets_config')
    tabs = {**defaults, **custom_tabs}
    if any(not isinstance(n, str) or not n.strip() or len(n) > 100 for n in tabs.values()) or len(set(tabs.values())) != len(tabs):
        raise SheetsError('Cada tabela deve apontar para uma aba diferente e com nome válido.', 'sheets_config')
    ttl = options.get('cache_seconds', 60)
    if isinstance(ttl, bool) or not isinstance(ttl, int) or not 15 <= ttl <= 300:
        raise SheetsError('cache_seconds deve ser um inteiro entre 15 e 300.', 'sheets_config')
    fingerprint = None
    if path is not None:
        try:
            stat = path.stat()
            if not path.is_file():
                raise OSError()
        except OSError:
            label = 'Arquivo XLSX local' if mode == 'file' else 'Arquivo da conta Google'
            raise SheetsError(label + ' não encontrado. Execute Jarvis.py, opção 2 (Configurar planilha).', 'sheets_file' if mode == 'file' else 'sheets_credentials') from None
        fingerprint = (str(path), stat.st_mtime_ns, stat.st_size)
    key = (mode, sid, fingerprint, layout, tuple(tabs.items()), ttl)
    return {'mode': mode, 'id': sid, 'path': path, 'tabs': tabs, 'layout': layout, 'ttl': ttl, 'key': key}


def load_account(path):
    """Valida o tipo de credencial sem expor chave, token ou erro do provedor."""
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (ValueError, OSError, UnicodeError):
        raise SheetsError('O JSON da conta Google não pôde ser lido.', 'sheets_credentials') from None
    if (not isinstance(data, dict) or data.get('type') != 'service_account'
            or not isinstance(data.get('private_key'), str)
            or not data['private_key'].startswith('-----BEGIN PRIVATE KEY-----')
            or not re.fullmatch(r'[^\s@]+@[^\s@]+\.iam\.gserviceaccount\.com', str(data.get('client_email', '')))
            or data.get('token_uri') != TOKEN_URI):
        raise SheetsError('Use o arquivo JSON de uma conta de serviço criado no Google Cloud.', 'sheets_credentials')
    return data


class GoogleClient:
    def __init__(self, path):
        try:
            from google.oauth2 import service_account
            from google.auth.transport.requests import AuthorizedSession
            from google.auth.exceptions import GoogleAuthError
            from requests.exceptions import RequestException
        except ImportError:
            raise SheetsError('Falta instalar a conexão Google. Execute Jarvis.py, opção 1 (Instalar).', 'sheets_dependencies') from None
        self.expected_errors = (GoogleAuthError, RequestException, TimeoutError)
        try:
            credentials = service_account.Credentials.from_service_account_info(load_account(path), scopes=[SCOPE])
            self.session = AuthorizedSession(credentials, refresh_timeout=10, max_refresh_attempts=1)
        except (ValueError, GoogleAuthError):
            raise SheetsError('A chave da conta Google é inválida. Baixe uma nova chave JSON no Google Cloud.', 'sheets_credentials') from None

    def close(self):
        self.session.close()

    def read(self, options):
        params = [('ranges', "'" + name.replace("'", "''") + "'!A:Z") for name in options['tabs'].values()]
        params.extend([('majorDimension', 'ROWS'), ('valueRenderOption', 'UNFORMATTED_VALUE'), ('dateTimeRenderOption', 'SERIAL_NUMBER')])
        try:
            with self.session.get(
                'https://sheets.googleapis.com/v4/spreadsheets/' + options['id'] + '/values:batchGet',
                params=params, timeout=(5, 15), max_allowed_time=35, allow_redirects=False,
            ) as response:
                if response.status_code == 400:
                    raise SheetsError('Confira os nomes das abas do formato selecionado e converta o arquivo para Google Planilhas, se ainda for Excel.', 'sheets_structure')
                if response.status_code in (401, 403, 404):
                    raise SheetsError('Sem acesso à planilha. Confira o ID, ative Google Sheets API e compartilhe a planilha com o e-mail da conta de serviço como Leitor.', 'sheets_access')
                if response.status_code == 429:
                    raise SheetsError('O Google limitou as consultas. Aguarde um minuto e tente novamente.', 'sheets_quota')
                if response.status_code != 200:
                    raise SheetsError('O Google Planilhas está indisponível no momento. Tente novamente.', 'sheets_unavailable')
                if len(response.content) > 8 * 1024 * 1024:
                    raise SheetsError('A planilha excedeu o limite de leitura desta versão. Remova linhas que não fazem parte da grade.', 'sheets_limit')
                payload = response.json()
        except self.expected_errors:
            raise SheetsError('Não consegui acessar o Google Planilhas. Confira a internet, o relógio do computador e a credencial da conta.', 'sheets_connection') from None
        except ValueError:
            raise SheetsError('O Google retornou uma resposta inválida. Tente novamente.', 'sheets_response') from None
        if not isinstance(payload, dict) or not isinstance(payload.get('valueRanges'), list) or len(payload['valueRanges']) != len(options['tabs']):
            raise SheetsError('O Google não retornou todas as tabelas esperadas.', 'sheets_response')
        result = {}
        for key, block in zip(options['tabs'], payload['valueRanges']):
            if not isinstance(block, dict) or not isinstance(block.get('values', []), list):
                raise SheetsError('A resposta da planilha não contém linhas válidas.', 'sheets_response')
            result[key] = block.get('values', [])
        return result


def read_workbook(content, tabs):
    """Lê valores calculados do XLSX, preservando células vazias e linhas.

    Não executa fórmulas nem macros. O Google deve calcular antes da exportação.
    """
    if len(content) > MAX_WORKBOOK_BYTES:
        raise SheetsError('O arquivo XLSX ultrapassa 8 MB.', 'sheets_limit')
    try:
        with ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > 2000 or sum(item.file_size for item in entries) > 48 * 1024 * 1024:
                raise SheetsError('A planilha ultrapassa o limite de leitura desta versão.', 'sheets_limit')
            strings = []
            if 'xl/sharedStrings.xml' in archive.namelist():
                strings = [''.join(t.text or '' for t in item.iter(XML_NS + 't'))
                           for item in ET.fromstring(archive.read('xl/sharedStrings.xml'))]
            targets = {item.attrib['Id']: item.attrib['Target']
                       for item in ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
                       if item.attrib.get('TargetMode') != 'External'}
            book = ET.fromstring(archive.read('xl/workbook.xml'))
            result = {}
            wanted = {name: key for key, name in tabs.items()}
            for tab in book.find(XML_NS + 'sheets'):
                name = tab.attrib['name']
                if name not in wanted:
                    continue
                rel = tab.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
                target = targets[rel]
                target = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/' + target)
                if not target.startswith('xl/worksheets/'):
                    raise ValueError('Worksheet inválida')
                root = ET.fromstring(archive.read(target))
                rows = []
                for cell in root.iter(XML_NS + 'c'):
                    match = re.fullmatch(r'([A-Z]+)([1-9]\d*)', cell.attrib.get('r', ''))
                    if not match:
                        raise ValueError('Célula inválida')
                    column = 0
                    for letter in match[1]:
                        column = column * 26 + ord(letter) - 64
                    if column > 26:
                        continue
                    value = cell.findtext(XML_NS + 'v', '')
                    kind = cell.attrib.get('t', '')
                    if kind == 's':
                        index = int(value)
                        if not 0 <= index < len(strings):
                            raise ValueError('Texto inválido')
                        value = strings[index]
                    elif kind == 'inlineStr':
                        value = ''.join(t.text or '' for t in cell.iter(XML_NS + 't'))
                    elif kind == 'b':
                        if value not in ('0', '1'):
                            raise ValueError('Booleano inválido')
                        value = value == '1'
                    elif value and kind not in ('str', 'e', 'd'):
                        value = float(value)
                    if value == '':
                        continue
                    line = int(match[2])
                    if line > 10001:
                        raise SheetsError(f'A aba {name} ultrapassa 10.000 registros.', 'sheets_limit')
                    while len(rows) < line:
                        rows.append([])
                    row = rows[line - 1]
                    row.extend([''] * max(0, column - len(row)))
                    row[column - 1] = value
                result[wanted[name]] = rows
            missing = [name for key, name in tabs.items() if key not in result]
            if missing:
                raise SheetsError('Abas não encontradas no arquivo: ' + ', '.join(missing) + '. Confira o nome exato no configurador.', 'sheets_structure')
            return result
    except SheetsError:
        raise
    except (BadZipFile, KeyError, IndexError, TypeError, ValueError, ET.ParseError, RuntimeError, OSError):
        raise SheetsError('O arquivo não é um XLSX válido. Baixe novamente pelo Google: Arquivo > Fazer download > Microsoft Excel (.xlsx).', 'sheets_response') from None


class FileClient:
    def close(self):
        pass

    def read(self, options):
        try:
            with options['path'].open('rb') as stream:
                content = stream.read(MAX_WORKBOOK_BYTES + 1)
        except OSError:
            raise SheetsError('Não consegui ler dados/grade.xlsx. Baixe e selecione a planilha novamente no configurador.', 'sheets_file') from None
        return read_workbook(content, options['tabs'])


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class PublicClient:
    """Baixa uma cópia em memória pelo link, sem cookies, login ou chave."""
    def __init__(self):
        self.opener = build_opener(_NoRedirect())
        self.expected_errors = (URLError, TimeoutError, OSError)

    def close(self):
        pass

    @staticmethod
    def allowed_url(url):
        try:
            parsed = urlparse(url)
            host = parsed.hostname or ''
            return (parsed.scheme == 'https' and parsed.port in (None, 443)
                    and not parsed.username and not parsed.password
                    and (host == 'docs.google.com' or host.endswith('-sheets.googleusercontent.com')))
        except ValueError:
            return False

    def read(self, options):
        url = 'https://docs.google.com/spreadsheets/d/' + options['id'] + '/export?format=xlsx'
        try:
            for _ in range(5):
                if not self.allowed_url(url):
                    raise SheetsError('O link exige login ou não permite o download. Use o modo 2 (arquivo local) se a planilha deve continuar privada.', 'sheets_access')
                request = Request(url, headers={'User-Agent': 'JarvisAGV/1.0'}, method='GET')
                try:
                    response = self.opener.open(request, timeout=15)
                except HTTPError as exc:
                    response = exc
                with response:
                    if response.status in (301, 302, 303, 307, 308):
                        url = urljoin(url, response.headers.get('Location', ''))
                        continue
                    if response.status in (401, 403, 404):
                        raise SheetsError('Sem leitura pelo link. Confira se ele abre e permite download numa janela anônima. Para manter a planilha privada, escolha o modo 2 (arquivo local).', 'sheets_access')
                    if response.status == 429:
                        raise SheetsError('O Google limitou as leituras. Aguarde um minuto e tente novamente.', 'sheets_quota')
                    if response.status != 200:
                        raise SheetsError('O Google não conseguiu fornecer a planilha agora. Tente novamente.', 'sheets_unavailable')
                    content = bytearray()
                    while True:
                        chunk = response.read(65536)
                        if not chunk:
                            break
                        content.extend(chunk)
                        if len(content) > MAX_WORKBOOK_BYTES:
                            raise SheetsError('O arquivo XLSX ultrapassa 8 MB.', 'sheets_limit')
                    if not content.startswith(b'PK'):
                        raise SheetsError('O Google retornou uma página em vez da planilha. Confira a permissão de leitura/download ou use o modo 2 (arquivo local).', 'sheets_access')
                    return read_workbook(content, options['tabs'])
            raise SheetsError('O Google redirecionou a leitura muitas vezes. Tente novamente ou use o modo 2.', 'sheets_response')
        except self.expected_errors:
            raise SheetsError('Não consegui baixar a planilha. Confira a internet ou use o modo 2 (arquivo local).', 'sheets_connection') from None


def _cell(value):
    if value is None:
        return ''
    if isinstance(value, (list, dict, bool)):
        raise ValueError('valor inválido')
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def _id(value):
    text = _cell(value)
    if not text or len(text) > 80 or text.startswith(('#', '=')):
        raise ValueError('ID ausente ou inválido')
    return text


def _time(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value) or not 0 <= value < 1:
            raise ValueError('horário numérico inválido')
        minutes = round(value * 1440)
        if minutes >= 1440 or abs(value * 1440 - minutes) > 0.01:
            raise ValueError('use horários com minutos inteiros')
        return f'{minutes // 60:02}:{minutes % 60:02}'
    match = re.fullmatch(r'(\d{1,2})(?::|h)(\d{2})(?::00)?', _cell(value))
    if not match or int(match[1]) > 23 or int(match[2]) > 59:
        raise ValueError('horário inválido; use 07:45 ou uma célula de hora')
    return f'{int(match[1]):02}:{int(match[2]):02}'


def _day(value):
    text = normalize(_cell(value)).replace('-feira', '').strip()
    names = ('segunda', 'terca', 'quarta', 'quinta', 'sexta', 'sabado', 'domingo')
    if text in names:
        return names.index(text)
    if text in tuple(str(i) for i in range(7)):
        return int(text)
    raise ValueError('dia inválido; use 0 para segunda até 6 para domingo')


def _active(value):
    if value is None or value == '':
        return True
    if value is True or value == 1 or normalize(value) in ('true', 'verdadeiro', 'sim', 's', 'ativo', '1'):
        return True
    if value is False or value == 0 or normalize(value) in ('false', 'falso', 'nao', 'n', 'inativo', '0'):
        return False
    raise ValueError('ativo inválido; use VERDADEIRO/FALSO ou Sim/Não')


def _records(values, required, tab):
    if not values or not isinstance(values[0], list):
        raise SheetsError(f'A aba {tab} está sem os cabeçalhos na linha 1.', 'sheets_structure')
    if len(values) > 10001:
        raise SheetsError(f'A aba {tab} ultrapassa 10.000 registros.', 'sheets_limit')
    headers = [re.sub(r'\s+', '_', normalize(v)) for v in values[0]]
    used = [h for h in headers if h]
    if len(used) != len(set(used)) or any(c not in headers for c in required):
        raise SheetsError(f'Confira os cabeçalhos da aba {tab}: ' + ', '.join(required) + '.', 'sheets_structure')
    result = []
    for line, values_row in enumerate(values[1:], 2):
        if not isinstance(values_row, list):
            raise SheetsError(f'Aba {tab}, linha {line}: formato inválido.', 'sheets_structure')
        if not any(v is not None and v != '' for v in values_row):
            continue
        row = {h: values_row[i] if i < len(values_row) else '' for i, h in enumerate(headers) if h}
        result.append((line, row))
    return result


def parse_tables(tables, tabs=None, layout='relacional'):
    """JOIN por ID. Recusa referências ambíguas, horários inválidos e conflitos."""
    if layout == 'horarios':
        return _parse_horarios(tables, tabs or HORARIOS_TABS)
    if layout != 'relacional':
        raise SheetsError('Formato de planilha não reconhecido.', 'sheets_config')
    tabs = tabs or DEFAULT_TABS
    entities = {}
    counts = {}
    for name in ('professores', 'materias', 'turmas', 'salas'):
        items = {}
        for line, row in _records(tables.get(name, []), ('id', 'nome'), tabs[name]):
            try:
                key = _id(row['id'])
                label = _cell(row['nome'])
                if not label or len(label) > 200 or label.startswith(('#', '=')):
                    raise ValueError('nome ausente ou inválido')
                if key in items:
                    raise ValueError('ID duplicado')
                items[key] = label
            except ValueError as exc:
                raise SheetsError(f'Aba {tabs[name]}, linha {line}: {exc}.', 'sheets_data') from None
        entities[name] = items
        counts[name] = len(items)
    required = ('id', 'professor_id', 'materia_id', 'turma_id', 'sala_id', 'dia', 'inicio', 'fim')
    rows = []
    ids = set()
    reservations = defaultdict(list)
    inactive = 0
    for line, row in _records(tables.get('aulas', []), required, tabs['aulas']):
        try:
            if not _active(row.get('ativo', '')):
                inactive += 1
                continue
            key = _id(row['id'])
            if key in ids:
                raise ValueError('ID de aula duplicado')
            ids.add(key)
            day, start, end = _day(row['dia']), _time(row['inicio']), _time(row['fim'])
            if start >= end:
                raise ValueError('o início precisa ser anterior ao fim')
            result = {'id': key, 'dia': day, 'inicio': start, 'fim': end}
            for field, entity in (('professor', 'professores'), ('materia', 'materias'), ('turma', 'turmas'), ('sala', 'salas')):
                fk = _id(row[field + '_id'])
                if fk not in entities[entity]:
                    raise ValueError(f'{field}_id não encontrado na aba {tabs[entity]}')
                result[field] = entities[entity][fk]
                if field != 'materia':
                    reservations[(day, field, fk)].append((start, end, line))
            rows.append(result)
        except ValueError as exc:
            raise SheetsError(f'Aba {tabs["aulas"]}, linha {line}: {exc}.', 'sheets_data') from None
    _check_conflicts(reservations, tabs['aulas'])
    counts.update(aulas=len(rows), aulas_inativas=inactive)
    return {'rows': sorted(rows, key=lambda r: (r['dia'], r['inicio'], r['id'])), 'counts': counts}


def _check_conflicts(reservations, tab):
    for (_, field, _), periods in reservations.items():
        previous = None
        for period in sorted(periods):
            if previous and period[0] < previous[1]:
                raise SheetsError(f'Aba {tab}: conflito de {field} entre as linhas {previous[2]} e {period[2]}. Os horários se sobrepõem no mesmo dia.', 'sheets_conflict')
            previous = period


def _name(value):
    label = _cell(value)
    if not label or len(label) > 200 or label.startswith(('#', '=')):
        raise ValueError('nome ausente ou inválido')
    return re.sub(r'\s+', ' ', label)


def _key(value):
    return normalize(re.sub(r'\s+', ' ', _cell(value)))


def _room_key(value):
    key = re.sub(r'^(?:sala|room)\s*', '', _key(value))
    return str(int(key)) if key.isdigit() else key


def _teacher(value, teachers):
    """Aceita abreviação apenas como prefixo de palavras e sem ambiguidade."""
    key = _key(_name(value))
    if key in teachers:
        return teachers[key]
    candidates = [name for candidate, name in teachers.items() if candidate.startswith(key + ' ')]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        raise ValueError('professor abreviado ambíguo; use o nome completo da aba Professores')
    raise ValueError('professor não encontrado na aba Professores')


def _parse_horarios(tables, tabs):
    """Formato real: Horarios.Aula -> Disciplinas.ID -> Turmas/Professores.

    E/F de Horarios são fórmulas de visualização: a fonte é Disciplinas.
    Sala vem de Turmas.N° Salas, salvo uma coluna opcional Sala em Horarios.
    """
    teachers, groups, subjects = {}, {}, {}
    warnings = []
    for line, row in _records(tables.get('professores', []), ('nome_prof',), tabs['professores']):
        try:
            name = _name(row['nome_prof'])
            # A mesma pessoa pode aparecer em várias linhas, uma por matéria.
            teachers.setdefault(_key(name), name)
        except ValueError as exc:
            raise SheetsError(f'Aba {tabs["professores"]}, linha {line}: {exc}.', 'sheets_data') from None
    for line, row in _records(tables.get('turmas', []), ('turmas', 'n°_salas'), tabs['turmas']):
        # Turmas também contém uma tabela independente de Entrada/Saída em E:F.
        if all(row.get(field) is None or row.get(field) == '' for field in ('turmas', 'n°_salas')):
            continue
        try:
            name, room = _name(row['turmas']), _name(row['n°_salas'])
            key = _key(name)
            if key in groups:
                raise ValueError('turma duplicada')
            groups[key] = (name, room)
        except ValueError as exc:
            raise SheetsError(f'Aba {tabs["turmas"]}, linha {line}: {exc}.', 'sheets_data') from None
    for line, row in _records(tables.get('materias', []), ('id', 'disciplina', 'turma', 'professor'), tabs['materias']):
        try:
            key = _key(_id(row['id']))
            if key in subjects:
                raise ValueError('ID de disciplina duplicado')
            group = _key(_name(row['turma']))
            if group not in groups:
                raise ValueError('turma não encontrada na aba Turmas')
            teacher = _teacher(row['professor'], teachers)
            if _key(row['professor']) != _key(teacher):
                warnings.append(f'Aba {tabs["materias"]}, linha {line}: {row["professor"]} foi relacionado a {teacher}. Prefira o nome completo.')
            subjects[key] = {'materia': _name(row['disciplina']), 'professor': teacher,
                             'turma': groups[group][0], 'sala': groups[group][1]}
        except ValueError as exc:
            raise SheetsError(f'Aba {tabs["materias"]}, linha {line}: {exc}.', 'sheets_data') from None
    required = ('dia_da_semana', 'horario_inicial', 'horario_final', 'aula')
    rows, reservations = [], defaultdict(list)
    inactive = ignored = 0
    for line, row in _records(tables.get('aulas', []), required, tabs['aulas']):
        try:
            if not _active(row.get('ativo', '')):
                inactive += 1
                continue
            # C também pode vir de PROCV. Uma fórmula sem entrada não é uma aula.
            # Horário final válido sozinho ou qualquer entrada parcial continuam sendo erros.
            empty_inputs = all(row.get(field) is None or row.get(field) == ''
                               for field in ('dia_da_semana', 'horario_inicial', 'aula', 'sala'))
            end_value = row.get('horario_final')
            if empty_inputs and (end_value is None or end_value == '' or str(end_value) in FORMULA_ERRORS):
                ignored += 1
                if any(str(row.get(field, '')) in FORMULA_ERRORS for field in ('horario_final', 'disciplina', 'professor')):
                    warnings.append(f'Aba {tabs["aulas"]}, linha {line}: fórmula com erro numa linha sem aula; linha ignorada.')
                continue
            for field, label in (('dia_da_semana', 'Dia da semana'), ('horario_inicial', 'Horario Inicial'),
                                 ('horario_final', 'Horario final'), ('aula', 'Aula')):
                if row.get(field) is None or row.get(field) == '':
                    raise ValueError(f'o campo {label} está vazio')
            key = _key(_id(row['aula']))
            if key not in subjects:
                raise ValueError('código de Aula não encontrado em Disciplinas.ID')
            day, start, end = _day(row['dia_da_semana']), _time(row['horario_inicial']), _time(row['horario_final'])
            if start >= end:
                raise ValueError('o início precisa ser anterior ao fim')
            result = dict(subjects[key], id=f'horarios:{line}', dia=day, inicio=start, fim=end)
            if row.get('sala') is not None and row.get('sala') != '':
                result['sala'] = _name(row['sala'])
            for field in ('professor', 'turma', 'sala'):
                value = _room_key(result[field]) if field == 'sala' else _key(result[field])
                reservations[(day, field, value)].append((start, end, line))
            # Fórmulas divergentes não mudam a fonte: avise o responsável no diagnóstico.
            for column, field in (('disciplina', 'materia'), ('professor', 'professor')):
                display = row.get(column, '')
                if display is None or display == '':
                    continue
                if field == 'professor':
                    try:
                        display = _teacher(display, teachers)
                    except ValueError:
                        display = ''
                if _key(display) != _key(result[field]):
                    warnings.append(f'Aba {tabs["aulas"]}, linha {line}: a coluna {column} diverge do cadastro. O Jarvis usa Disciplinas.')
            rows.append(result)
        except ValueError as exc:
            raise SheetsError(f'Aba {tabs["aulas"]}, linha {line}: {exc}.', 'sheets_data') from None
    _check_conflicts(reservations, tabs['aulas'])
    counts = {'professores': len(teachers), 'disciplinas_por_turma': len(subjects),
              'turmas': len(groups), 'salas': len({_room_key(g[1]) for g in groups.values()} | {_room_key(r['sala']) for r in rows}),
              'aulas': len(rows), 'aulas_inativas': inactive, 'linhas_sem_aula': ignored}
    return {'rows': sorted(rows, key=lambda r: (r['dia'], r['inicio'], r['id'])),
            'counts': counts, 'warnings': warnings}


def snapshot(force=False):
    global _cache_key, _cache_data, _expires, _last_sync, _last_error, _retry_at, _client, _client_key
    options = configuration()
    with _LOCK:
        if options['key'] != _cache_key:
            _cache_key, _cache_data, _expires = options['key'], None, 0
            _last_sync, _last_error, _retry_at = None, None, 0
        if not force and _cache_data is not None and time.monotonic() < _expires:
            return copy.deepcopy(_cache_data)
        if not force and _last_error is not None and time.monotonic() < _retry_at:
            raise SheetsError(str(_last_error), _last_error.code)
        try:
            # Uma sessão e uma renovação de token por vez entre as threads HTTP.
            if _client is None or _client_key != options['key']:
                if _client is not None:
                    _client.close()
                _client, _client_key = None, None
                mode = options.get('mode', 'service_account')
                _client = PublicClient() if mode == 'public' else FileClient() if mode == 'file' else GoogleClient(options['path'])
                _client_key = options['key']
            data = parse_tables(_client.read(options), options['tabs'], options.get('layout', 'relacional'))
        except SheetsError as exc:
            _last_error, _retry_at = exc, time.monotonic() + 5
            _cache_data, _expires = None, 0
            raise
        _cache_data, _expires = data, time.monotonic() + options['ttl']
        _last_sync = datetime.now().astimezone().isoformat(timespec='seconds')
        _last_error, _retry_at = None, 0
        return copy.deepcopy(data)


def schedule_rows(day):
    return [r for r in snapshot()['rows'] if r['dia'] == day]


def status():
    """Estado público sem chave, e-mail, ID da planilha ou caminho de arquivo."""
    try:
        options = configuration()
    except SheetsError as exc:
        return {'provider': 'google_sheets', 'configured': exc.code != 'sheets_not_configured', 'state': 'not_configured' if exc.code == 'sheets_not_configured' else 'error', 'label': 'Não configurada' if exc.code == 'sheets_not_configured' else 'Verificar configuração', 'last_sync': None}
    with _LOCK:
        same = _cache_key == options['key']
        if same and _last_error is not None:
            state, label = 'error', 'Falha na consulta'
        elif same and _cache_data is not None and time.monotonic() < _expires:
            state, label = 'connected', 'Planilha local' if options.get('mode') == 'file' else 'Google Planilhas'
        else:
            state, label = 'pending', 'Aguardando consulta'
        return {'provider': 'google_sheets', 'configured': True, 'state': state, 'label': label, 'last_sync': _last_sync if same else None}
