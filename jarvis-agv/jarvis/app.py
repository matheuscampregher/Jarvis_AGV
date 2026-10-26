"""Servidor HTTP do Jarvis AGV: interface, chat (Ollama), voz e consulta de horários."""
import asyncio
import json
import os
import threading
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import voice
from .school import school_answer, current_datetime_text
from .settings import MODEL, WEB
from .sheets import status as sheets_status, SheetsError

MODEL_LOCK = threading.Lock()
VOICE_LOCK = threading.BoundedSemaphore(2)


LANGUAGE_PROMPTS = {
    'pt-BR': 'Responda sempre em português do Brasil. Use frases simples e naturais.',
    'en-US': 'Always answer in English from the United States. Use simple, natural sentences.',
}
LANGUAGE_EXAMPLES = {
    'pt-BR': 'Exemplo: Pergunta: O que é fotossíntese? Resposta: Fotossíntese é o processo pelo qual as plantas transformam luz em energia.',
    'en-US': 'Example: Question: What is photosynthesis? Answer: Photosynthesis is the process plants use to turn light into energy.',
}
# Dados da escola só chegam pela consulta de grade (school_answer). Quando essa
# consulta não responde, o modelo não recebe nenhum dado e não pode preencher a
# lacuna por conta própria.
NO_INVENTION = {
    'pt-BR': (
        'REGRA ABSOLUTA: você nunca inventa dados da escola. É proibido afirmar horário, '
        'professor, sala, turma, disciplina ou data de aula que não tenha vindo da consulta de grade. '
        'Esta conversa não traz nenhum dado de grade: portanto, se a pergunta for sobre horário, '
        'professor, sala, turma ou calendário escolar, responda exatamente que não tem essa informação '
        'e oriente a procurar o responsável pela grade na escola. Não chute, não dê exemplo, '
        'não suponha e não ofereça um horário "provável". Dizer que não sabe é a resposta correta. '
        'Você ainda pode explicar matéria e ajudar nos estudos normalmente.'
    ),
    'en-US': (
        'ABSOLUTE RULE: never invent school data. You must not state any class time, teacher, room, '
        'group, subject or school date that did not come from the schedule query. '
        'This conversation carries no schedule data, so if the question is about times, teachers, rooms, '
        'groups or the school calendar, answer exactly that you do not have that information and tell the '
        'person to ask the staff member responsible for the schedule. Do not guess, do not give an example, '
        'do not assume and do not offer a "likely" time. Saying you do not know is the correct answer. '
        'You can still explain subjects and help with studying.'
    ),
}


def model_request(question, history, language='pt-BR'):
    language = language if language in LANGUAGE_PROMPTS else 'pt-BR'
    clock_context = current_datetime_text()
    messages = [{'role': 'system', 'content': (
        'You are Jarvis AGV, a school assistant. ' + LANGUAGE_PROMPTS[language] + ' '
        'If you do not know something, say so. '
        + NO_INVENTION[language] + ' '
        + clock_context + ' Use SEMPRE esta data como verdade absoluta. Nunca diga outro ano, mês, dia ou hora. '
        + LANGUAGE_EXAMPLES[language]
    )}]
    for item in history[-8:]:
        if isinstance(item, dict) and item.get('role') in ('user', 'assistant') and isinstance(item.get('content'), str):
            messages.append({'role': item['role'], 'content': item['content'][:2000]})
    messages.append({'role': 'user', 'content': LANGUAGE_PROMPTS[language] + '\n' + question})
    return urllib.request.Request('http://127.0.0.1:11434/api/chat', json.dumps({'model': MODEL, 'messages': messages, 'stream': True, 'think': False, 'options': {'num_ctx': 2048, 'num_predict': 512}}).encode(), {'Content-Type': 'application/json'})


def model_error(exc):
    if isinstance(exc, urllib.error.HTTPError) and exc.code == 404:
        return f'O modelo {MODEL} não foi encontrado. Peça ao responsável para baixá-lo no Ollama.'
    if isinstance(exc, (TimeoutError,)):
        return 'O modelo demorou demais para responder. Tente uma pergunta curta ou use um modelo menor.'
    return 'Não foi possível receber a resposta da IA. Confira se o Ollama está aberto no computador principal.'


def open_model(request):
    try:
        return urllib.request.urlopen(request, timeout=75)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(model_error(exc)) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(model_error(exc)) from exc


class Handler(BaseHTTPRequestHandler):
    def send(self, status, content, kind='application/json; charset=utf-8'):
        data = content if isinstance(content, bytes) else json.dumps(content, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        files = {'/': ('index.html', 'text/html'), '/style.css': ('style.css', 'text/css'), '/app.js': ('app.js', 'text/javascript'), '/speech.js': ('speech.js', 'text/javascript'), '/assets/agv-logo.png': ('assets/agv-logo.png', 'image/png')}
        if self.path in files:
            name, kind = files[self.path]
            content_type = kind + '; charset=utf-8' if kind.startswith('text/') else kind
            return self.send(200, (WEB / name).read_bytes(), content_type)
        if self.path == '/api/voices':
            try:
                # Filtra o catálogo usando os ShortName que o edge-tts instalado conhece.
                return self.send(200, voice.catalog_for_client(live=True))
            except Exception:
                return self.send(503, {'erro': 'Não foi possível listar as vozes agora.', 'codigo': 'voice_catalog_error'})
        if self.path == '/api/status':
            return self.send(200, {
                'online': True,
                'natural_voice': voice.available(),
                'voice': voice.diagnostic(),
                'languages': voice.catalog_for_client(),
                'database': sheets_status(),
            })
        self.send(404, {'erro': 'Página não encontrada', 'codigo': 'not_found'})

    def tts(self):
        if not VOICE_LOCK.acquire(blocking=False):
            return self.send(429, {'erro': 'Serviço de voz ocupado. Tente novamente.', 'codigo': 'voice_busy'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if size < 1 or size > 6000:
                raise ValueError('Texto de voz muito grande.')
            data = json.loads(self.rfile.read(size))
            text = data.get('texto', '')
            language = data.get('idioma', 'pt-BR')
            # A voz pode vir com um id antigo salvo no navegador; synthesize converte.
            chosen = data.get('voz')
            speed = float(data.get('velocidade', 1.15))
            pitch = int(data.get('tom', voice.DEFAULT_PITCH))
            volume = float(data.get('volume', 1.0))
            if not isinstance(text, str) or not text.strip() or len(text) > 1200 or language not in voice.CATALOG or not 0.85 <= speed <= 1.5 or not -10 <= pitch <= 10 or not 0.5 <= volume <= 1.2:
                raise ValueError('Parâmetros de voz inválidos.')
            # O handler é síncrono; o loop curto evita compartilhar um loop entre threads.
            # O custo é criar/destruir um loop por frase, aceitável para o protótipo local.
            audio = asyncio.run(voice.synthesize(text, language, chosen, speed, pitch, volume))
            self.send(200, audio, 'audio/mpeg')
        except (ValueError, TypeError, AttributeError) as exc:
            self.send(400, {'erro': str(exc), 'codigo': 'invalid_request'})
        except voice.VoiceError as exc:
            self.send(503, {'erro': str(exc), 'codigo': exc.code})
        except RuntimeError as exc:
            self.send(503, {'erro': str(exc), 'codigo': 'runtime_error'})
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            VOICE_LOCK.release()

    def do_POST(self):
        if not self.headers.get('Content-Type', '').startswith('application/json'):
            return self.send(415, {'erro': 'Use JSON.', 'codigo': 'invalid_content_type'})
        origin = self.headers.get('Origin')
        if origin and origin not in ('http://' + self.headers.get('Host', ''), 'https://' + self.headers.get('Host', '')):
            return self.send(403, {'erro': 'Origem não permitida.', 'codigo': 'forbidden_origin'})
        if self.path == '/api/tts':
            return self.tts()
        if self.path != '/api/chat':
            return self.send(404, {'erro': 'Rota não encontrada', 'codigo': 'not_found'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if size < 1 or size > 20000:
                raise ValueError('Mensagem muito grande')
            body = json.loads(self.rfile.read(size))
            question = body.get('mensagem', '')
            language = body.get('idioma', 'pt-BR')
            if language not in LANGUAGE_PROMPTS:
                raise ValueError('Idioma inválido.')
            if not isinstance(question, str) or not question.strip() or len(question) > 2000:
                raise ValueError('Digite uma mensagem de até 2000 caracteres')
            history = body.get('historico', [])
            direct = school_answer(question, language=language)
            if direct is not None:
                return self.send(200, {'resposta': direct})
            if not MODEL_LOCK.acquire(blocking=False):
                return self.send(429, {'erro': 'O Jarvis está respondendo outra pergunta. Tente de novo em instantes.', 'codigo': 'model_busy'})
            try:
                with open_model(model_request(question, history if isinstance(history, list) else [], language)) as response:
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/x-ndjson; charset=utf-8')
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('X-Content-Type-Options', 'nosniff')
                    self.end_headers()
                    answer = ''
                    try:
                        for line in response:
                            packet = json.loads(line)
                            part = packet.get('message', {}).get('content', '')
                            if part:
                                answer += part
                                self.wfile.write((json.dumps({'texto': part}, ensure_ascii=False) + '\n').encode())
                                self.wfile.flush()
                            if packet.get('done'):
                                break
                        self.wfile.write((json.dumps({'fim': True, 'vazio': not bool(answer.strip())}) + '\n').encode())
                        self.wfile.flush()
                    except (OSError, ValueError, TimeoutError, urllib.error.URLError) as exc:
                        try:
                            self.wfile.write((json.dumps({'erro': model_error(exc), 'codigo': 'model_stream_error'}, ensure_ascii=False) + '\n').encode())
                            self.wfile.flush()
                        except OSError:
                            pass
            finally:
                MODEL_LOCK.release()
        except (ValueError, TypeError, KeyError) as exc:
            self.send(400, {'erro': str(exc), 'codigo': 'invalid_request'})
        except SheetsError as exc:
            self.send(503, {'erro': exc.public_message, 'codigo': exc.code})
        except RuntimeError as exc:
            self.send(503, {'erro': str(exc), 'codigo': 'server_error'})


def main():
    host = '0.0.0.0' if os.environ.get('JARVIS_REDE') == '1' else '127.0.0.1'
    print('Voz natural instalada neste Jarvis:', 'sim' if voice.available() else 'não — execute Jarvis.py, opção 1 (Instalar), e inicie de novo')
    # Aquece a lista de vozes agora para que a primeira frase falada não espere
    # essa consulta de rede.
    if voice.available():
        voice.warm_engines()
    try:
        server = ThreadingHTTPServer((host, 8000), Handler)
    except OSError as exc:
        # Erro comum: o Jarvis já está aberto em outra janela.
        print('\nNão consegui usar a porta 8000.')
        print('Quase sempre é o próprio Jarvis já aberto em outra janela:')
        print('  abra http://127.0.0.1:8000 no navegador.')
        print('Se não for, feche o outro programa que usa a porta 8000 e tente de novo.')
        print('Detalhe:', exc)
        return 1
    print('Dados escolares: Google Planilhas. Estado:', sheets_status()['label'])
    print('Jarvis AGV pronto em http://127.0.0.1:8000. Mantenha esta janela aberta.')
    # Quem inicia pelo escutador de palmas abre o navegador por conta própria.
    if os.environ.get('JARVIS_SEM_NAVEGADOR') != '1':
        threading.Timer(0.5, lambda: webbrowser.open('http://127.0.0.1:8000')).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nJarvis encerrado.')
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
