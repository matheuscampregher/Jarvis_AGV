import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from .sheets import schedule_rows

DAYS = ['segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo']
DAY_LABELS_PT = ['segunda-feira', 'terça-feira', 'quarta-feira', 'quinta-feira', 'sexta-feira', 'sábado', 'domingo']
SCHOOL_TIMEZONE = 'America/Sao_Paulo'


def current_school_datetime():
    """Relógio único do projeto; cai para o fuso local se tzdata não existir."""
    try:
        return datetime.now(ZoneInfo(SCHOOL_TIMEZONE)), SCHOOL_TIMEZONE
    except ZoneInfoNotFoundError:
        local = datetime.now().astimezone()
        return local, local.tzname() or 'fuso local'


def current_datetime_text():
    now, timezone_name = current_school_datetime()
    return f'Data e hora atuais: {DAY_LABELS_PT[now.weekday()]}, {now:%d/%m/%Y}, {now:%H:%M} (fuso {timezone_name}).'


def norm(text):
    return ''.join(c for c in unicodedata.normalize('NFD', str(text).lower()) if unicodedata.category(c) != 'Mn')


DAY_NAMES = {
    'pt-BR': ['segunda-feira', 'terça-feira', 'quarta-feira', 'quinta-feira', 'sexta-feira', 'sábado', 'domingo'],
    'en-US': ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],
    'es-ES': ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'],
}
DAY_ALIASES = [
    ('segunda', 'monday', 'lunes'), ('terça', 'terca', 'tuesday', 'martes'),
    ('quarta', 'wednesday', 'miércoles', 'miercoles'), ('quinta', 'thursday', 'jueves'),
    ('sexta', 'friday', 'viernes'), ('sábado', 'sabado', 'saturday'), ('domingo', 'sunday'),
]
FIELD_ALIASES = {
    'professor': ('professor', 'professora', 'teacher', 'profesor', 'profesora'),
    'turma': ('turma', 'class', 'group', 'clase', 'grupo'),
    'sala': ('sala', 'room', 'aula', 'salon', 'salón'),
}
LOCALIZED = {
    'pt-BR': {
        'no_day': 'Não há aulas cadastradas para {day}.',
        'no_db': 'Não há aulas cadastradas para {day} na planilha.',
        'interval_empty': 'Não há aulas entre {start} e {end} em {day}. Confira se os dados foram cadastrados no Google Planilhas.',
        'ask_teacher': 'Qual professor você quer consultar? {names}.',
        'unknown_professor': 'Não encontrei esse professor na grade desse dia. Use o nome cadastrado na planilha.',
        'unknown_field': 'Não encontrei essa {field} na grade desse dia. Use o nome cadastrado.',
        'invalid_time': 'Informe um horário válido, por exemplo, às 08:20.',
        'other_day': 'Para consultar outro dia, informe também o horário, por exemplo, segunda às 08:20.',
        'ask_class': 'De qual turma? Pergunte, por exemplo: qual é a próxima aula da turma 1A?',
        'empty': 'Não há aula cadastrada para esse professor, turma ou sala no horário consultado.',
        'line': '{start}–{end}: {subject}, professor(a) {teacher}, turma {group}, sala {room}.',
        'more': 'Há mais aulas. Informe a turma ou o professor para filtrar.', 'header': 'Grade de {day}:',
        'teacher_word': 'professor', 'class_word': 'turma', 'room_word': 'sala', 'unknown': 'não informado',
        'clock': 'Agora são {time}, {day}, {date}.', 'date': 'Hoje é {day}, {date}.',
    },
    'en-US': {
        'no_day': 'There are no classes registered for {day}.',
        'no_db': 'There are no classes registered for {day} in the spreadsheet.',
        'interval_empty': 'There are no classes between {start} and {end} on {day}. Check whether the data was registered in Google Sheets.',
        'ask_teacher': 'Which teacher do you want to check? {names}.',
        'unknown_professor': 'I could not find that teacher on this day. Use the name registered in the spreadsheet.',
        'unknown_field': 'I could not find that {field} on this day. Use the registered name.',
        'invalid_time': 'Enter a valid time, for example 08:20.',
        'other_day': 'To check another day, also enter a time, for example Monday at 08:20.',
        'ask_class': 'Which class? For example: what is the next class for 1A?',
        'empty': 'There is no class for this teacher, class or room at the selected time.',
        'line': '{start}–{end}: {subject}, teacher {teacher}, class {group}, room {room}.',
        'more': 'There are more classes. Enter a class or teacher to filter.', 'header': '{day} schedule:',
        'teacher_word': 'teacher', 'class_word': 'class', 'room_word': 'room', 'unknown': 'not informed',
        'clock': 'It is {time} on {day}, {date}.', 'date': 'Today is {day}, {date}.',
    },
    'es-ES': {
        'no_day': 'No hay clases registradas para {day}.',
        'no_db': 'No hay clases registradas para {day} en la hoja de cálculo.',
        'interval_empty': 'No hay clases entre {start} y {end} en {day}. Comprueba si los datos fueron registrados en Google Sheets.',
        'ask_teacher': '¿Qué profesor quieres consultar? {names}.',
        'unknown_professor': 'No encontré ese profesor en el horario de ese día. Usa el nombre registrado en la hoja de cálculo.',
        'unknown_field': 'No encontré esa {field} en el horario de ese día. Usa el nombre registrado.',
        'invalid_time': 'Indica una hora válida, por ejemplo, 08:20.',
        'other_day': 'Para consultar otro día, indica también la hora, por ejemplo, lunes a las 08:20.',
        'ask_class': '¿De qué clase? Por ejemplo: ¿cuál es la próxima clase de 1A?',
        'empty': 'No hay clase para ese profesor, clase o sala en la hora consultada.',
        'line': '{start}–{end}: {subject}, profesor {teacher}, clase {group}, sala {room}.',
        'more': 'Hay más clases. Indica la clase o el profesor para filtrar.', 'header': 'Horario del {day}:',
        'teacher_word': 'profesor', 'class_word': 'clase', 'room_word': 'sala', 'unknown': 'no informado',
        'clock': 'Ahora son las {time} del {day}, {date}.', 'date': 'Hoy es {day}, {date}.',
    },
}


def _tr(language, key, **values):
    language = language if language in LOCALIZED else 'pt-BR'
    return LOCALIZED[language][key].format(**values)


def _has_word(text, words):
    return any(re.search(r'\b' + re.escape(norm(word)) + r'\b', text) for word in words)


def _clock_text(value):
    """Normaliza HH:MM, H:MM ou HH:MM:SS para comparações de grade."""
    parts = str(value or '').split(':')
    if len(parts) < 2:
        return ''
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except (TypeError, ValueError):
        return ''
    return f'{hour:02}:{minute:02}' if 0 <= hour <= 23 and 0 <= minute <= 59 else ''


def _parse_clock(hour, minute='0'):
    value = _clock_text(f'{int(hour)}:{int(minute or 0)}')
    return value or None


def school_answer(question, now=None, language='pt-BR'):
    language = language if language in LOCALIZED else 'pt-BR'
    q = norm(question)
    now = now or current_school_datetime()[0]
    date_text = f'{now:%d/%m/%Y}'
    if re.search(r'\b(?:que horas|qual a hora|what time|what is the time|que hora es|a que hora)\b', q) and not _has_word(q, ('aula', 'aulas', 'professor', 'professora', 'turma', 'sala', 'class', 'classes', 'teacher', 'room')):
        return _tr(language, 'clock', time=now.strftime('%H:%M'), day=DAY_NAMES[language][now.weekday()], date=date_text)
    if re.search(r'\b(?:que dia e hoje|qual a data|what day is it|what is today|que dia es hoy|cual es la fecha)\b', q):
        return _tr(language, 'date', day=DAY_NAMES[language][now.weekday()], date=date_text)

    schedule_term = _has_word(q, ('aula', 'aulas', 'horario', 'horarios', 'grade', 'proxima', 'proximo', 'next', 'class', 'classes', 'clase', 'clases'))
    question_term = _has_word(q, ('quando', 'que', 'que horas', 'quais', 'onde', 'tem', 'ha', 'esta', 'when', 'what', 'what time', 'which', 'where', 'cuándo', 'dónde', 'cuáles', 'hoy', 'manana', 'ayer', 'today', 'tomorrow', 'yesterday'))
    teacher_expression = re.search(r'\b(?:professor|professora|teacher|profesor|profesora)\s+([A-Za-zÀ-ÿ]+(?:\s+[A-Za-zÀ-ÿ]+){0,3})\b', str(question), re.IGNORECASE)
    teacher_candidate = norm(teacher_expression.group(1)) if teacher_expression else ''
    suffix_words = ('hoje', 'amanha', 'ontem', 'agora', 'as', 'at', 'today', 'tomorrow',
                    'yesterday', 'now', 'esta', 'vai', 'tem', 'na', 'no', 'com')
    suffix_words += tuple(norm(alias) for aliases in DAY_ALIASES for alias in aliases)
    teacher_candidate = re.split(r'\b(?:' + '|'.join(map(re.escape, suffix_words)) + r')\b', teacher_candidate, maxsplit=1)[0].strip()
    has_named_teacher = bool(teacher_candidate) and teacher_candidate.split()[0] not in {'a', 'o', 'um', 'uma', 'the', 'un', 'una', 'de', 'da', 'do', 'na', 'no', 'esta', 'vai', 'tem', 'sobre', 'para'}
    has_class_or_room_code = bool(re.search(r'\b(?:turma|sala|class|room)\s+(?:[0-9]{1,3}[A-Za-z]?|[A-Za-z]?[0-9]{1,3})\b', q))
    if not ((schedule_term and question_term) or has_named_teacher or has_class_or_room_code):
        return None
    if q.startswith(('o que e ', 'explique ', 'defina ', 'what is ', 'explain ', 'define ', 'que es ', 'explica ', 'define ')):
        return None
    day = now.weekday()
    if _has_word(q, ('amanha', 'tomorrow', 'mañana', 'manana')):
        day = (day + 1) % 7
    elif _has_word(q, ('ontem', 'yesterday', 'ayer')):
        day = (day - 1) % 7
    for index, aliases in enumerate(DAY_ALIASES):
        if _has_word(q, aliases):
            day = index
            break
    rows = schedule_rows(day)
    if not rows:
        return _tr(language, 'no_db', day=DAY_NAMES[language][day])
    for field in ('professor', 'turma', 'sala'):
        values = {r.get(field, '') for r in rows if r.get(field)}
        aliases = FIELD_ALIASES[field]
        if field == 'sala' and language != 'es-ES':
            aliases = tuple(alias for alias in aliases if alias != 'aula')
        if field == 'professor':
            matches = [v for v in values if re.search(r'\b' + re.escape(norm(v)) + r'\b', q)]
            if not matches and teacher_candidate:
                matches = [
                    v for v in values
                    if teacher_candidate == norm(v)
                    or teacher_candidate.startswith(norm(v) + ' ')
                    or norm(v).startswith(teacher_candidate + ' ')
                    or teacher_candidate == norm(v).split()[0]
                ]
            if len(matches) > 1:
                return _tr(language, 'ask_teacher', names=', '.join(sorted(matches)))
            if not matches and teacher_candidate:
                return _tr(language, 'unknown_professor')
        else:
            matches = []
            for value in values:
                # A planilha pode chamar a sala de 'Sala Aurora' ou somente 'Aurora'.
                name = norm(value)
                short = re.sub(r'^(?:sala|room)\s+', '', name) if field == 'sala' else name
                pattern = re.escape(name) + '|' + re.escape(short)
                if field == 'turma':
                    # "1°Ds", "1º DS" e "1 DS" representam a mesma turma.
                    parts = re.findall(r'[a-z]+|\d+', name)
                    if parts:
                        pattern += '|' + r'[\s°ºª_-]*'.join(map(re.escape, parts))
                if re.search(r'\b(?:' + '|'.join(map(re.escape, aliases)) + r')\s+(?:' + pattern + r')\b', q):
                    matches.append(value)
            if _has_word(q, aliases) and not matches and re.search(r'\b(?:' + '|'.join(map(re.escape, aliases)) + r')\s+\w', q):
                label_key = {'professor': 'teacher_word', 'turma': 'class_word', 'sala': 'room_word'}[field]
                return _tr(language, 'unknown_field', field=LOCALIZED[language][label_key])
        if matches:
            rows = [r for r in rows if r.get(field) in matches]
    interval = (
        re.search(r'\b(?:das?|de)\s+(\d{1,2})(?::|h)(\d{2})?\s+(?:as|a|ate|hasta)\s+(\d{1,2})(?::|h)(\d{2})?\b', q)
        or re.search(r'\bfrom\s+(\d{1,2})(?::|h)(\d{2})?\s+(?:to|until)\s+(\d{1,2})(?::|h)(\d{2})?\b', q)
        or re.search(r'\bde\s+(\d{1,2})(?::|h)(\d{2})?\s+a\s+(?:las\s+)?(\d{1,2})(?::|h)(\d{2})?\b', q)
    )
    if interval:
        start_point = _parse_clock(interval[1], interval[2])
        end_point = _parse_clock(interval[3], interval[4])
        if not start_point or not end_point or start_point >= end_point:
            return _tr(language, 'invalid_time')
        rows = [
            r for r in rows
            if _clock_text(r.get('inicio')) and _clock_text(r.get('fim'))
            and _clock_text(r['inicio']) < end_point
            and _clock_text(r['fim']) > start_point
        ]
        if not rows:
            return _tr(language, 'interval_empty', start=start_point, end=end_point, day=DAY_NAMES[language][day])
    elif at := re.search(r'\b(?:as|a|horario|at|time|hora|a las)\s+(\d{1,2})(?::|h)(\d{2})?\b', q):
        point = _parse_clock(at[1], at[2])
        if not point:
            return _tr(language, 'invalid_time')
        rows = [r for r in rows if _clock_text(r.get('inicio')) <= point < _clock_text(r.get('fim'))]
    elif _has_word(q, ('agora', 'now', 'ahora')) or _has_word(q, ('onde esta', 'where is', 'donde esta')):
        if day != now.weekday():
            return _tr(language, 'other_day')
        point = now.strftime('%H:%M')
        rows = [r for r in rows if _clock_text(r.get('inicio')) <= point < _clock_text(r.get('fim'))]
    elif _has_word(q, ('proxima', 'proximo', 'next', 'siguiente')):
        if len({r.get('turma', '') for r in rows}) > 1 and not _has_word(q, FIELD_ALIASES['turma']):
            return _tr(language, 'ask_class')
        if day == now.weekday():
            rows = [r for r in rows if _clock_text(r.get('inicio')) > now.strftime('%H:%M')]
        rows = rows[:1]
    if not rows:
        return _tr(language, 'empty')
    unknown = LOCALIZED[language]['unknown']
    lines = [_tr(language, 'line', start=_clock_text(r.get('inicio')) or str(r.get('inicio', '')), end=_clock_text(r.get('fim')) or str(r.get('fim', '')), subject=r['materia'], teacher=r.get('professor') or unknown, group=r.get('turma') or unknown, room=r.get('sala') or unknown) for r in rows[:20]]
    if len(rows) > 20:
        lines.append(_tr(language, 'more'))
    return _tr(language, 'header', day=DAY_NAMES[language][day]) + '\n' + '\n'.join(lines)
