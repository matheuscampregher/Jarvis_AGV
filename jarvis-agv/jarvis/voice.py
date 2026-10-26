"""Síntese de voz do Jarvis.

O áudio natural é gerado sob demanda pelo edge-tts. O pacote precisa estar
instalado no mesmo Python que inicia o servidor e o computador precisa estar
conectado à internet durante a geração.
"""
import asyncio
import sys
import time


CATALOG = {
    "pt-BR": {
        "label": "Português (Brasil)",
        "sample": "Olá! Eu sou o Jarvis AGV. Esta é uma amostra da minha voz.",
        "voices": {
            "jarvis-pt": {"label": "Jarvis — voz masculina (Brasil)", "engine": "pt-BR-AntonioNeural"},
        },
    },
    "en-US": {
        "label": "English (United States)",
        "sample": "Hello! I am Jarvis AGV. This is a sample of my voice.",
        "voices": {
            "jarvis-en": {"label": "Jarvis — voz masculina (inglês)", "engine": "en-GB-RyanNeural"},
        },
    },
}

# Compatibilidade com código de versões antigas.
VOICES = {voice_id: item["engine"] for data in CATALOG.values() for voice_id, item in data["voices"].items()}
_LIVE_VOICE_CACHE = {}
_LIVE_VOICE_CACHE_TTL = 300
_AVAILABLE_ENGINES_CACHE = None
_AVAILABLE_ENGINES_AT = 0.0
_AVAILABLE_ENGINES_TTL = 300
DEFAULT_VOICES = {'pt-BR': 'jarvis-pt', 'en-US': 'jarvis-en'}

# Tom padrão mais grave. Valor proposto, fácil de mudar aqui e no index.html.
DEFAULT_PITCH = -4

# Ids usados em versões anteriores. Ficam aqui só para converter o que já está
# salvo em config.json e nas preferências do navegador; não aparecem na tela.
LEGACY_VOICE_IDS = {
    'antonio': 'jarvis-pt',
    'francisca': 'jarvis-pt',
    'jenny': 'jarvis-en',
    'guy': 'jarvis-en',
}


def resolve_voice_id(voice_id, language='pt-BR'):
    """Converte um id antigo no atual. Devolve o padrão do idioma se não houver.

    Quem chama recebe sempre um id que existe no catálogo, para que uma
    preferência antiga não vire erro nem caia no padrão sem explicação.
    """
    language = language if language in CATALOG else 'pt-BR'
    voices = CATALOG[language]['voices']
    if isinstance(voice_id, str):
        if voice_id in voices:
            return voice_id
        migrated = LEGACY_VOICE_IDS.get(voice_id.strip().lower())
        if migrated in voices:
            return migrated
        # O id pode ser de outro idioma (preferência antiga de inglês em pt-BR).
        if migrated:
            for outro, dados in CATALOG.items():
                if migrated in dados['voices'] and outro == language:
                    return migrated
    return DEFAULT_VOICES[language]


class VoiceError(RuntimeError):
    def __init__(self, message, code="voice_error"):
        super().__init__(message)
        self.code = code


def _expected_service_errors(edge_tts):
    errors = [OSError, ConnectionError, ValueError, TypeError]
    try:
        import aiohttp
        errors.append(aiohttp.ClientError)
    except ImportError:
        pass
    module = getattr(edge_tts, "exceptions", None)
    for name in ("EdgeTTSException", "NoAudioReceived", "UnknownVoice"):
        error_type = getattr(module, name, None)
        if isinstance(error_type, type) and issubclass(error_type, BaseException):
            errors.append(error_type)
    return tuple(errors)


def available():
    try:
        import edge_tts  # noqa: F401
        return True
    except ImportError:
        return False


def diagnostic():
    try:
        import edge_tts
    except ImportError:
        return {
            "installed": False,
            "version": None,
            "python": sys.executable,
            "message": "edge-tts não está instalado neste ambiente Python.",
        }
    return {
        "installed": True,
        "version": getattr(edge_tts, "__version__", "desconhecida"),
        "python": sys.executable,
        "message": "edge-tts está instalado. Faça um teste para verificar a internet.",
    }


def _catalog_engines():
    return {item['engine'] for data in CATALOG.values() for item in data['voices'].values()}


async def available_engines():
    """Consulta e memoriza os ShortName aceitos pela instalação do edge-tts.

    Em caso de falha de rede/listagem, o catálogo conhecido é usado como
    fallback: a própria síntese ainda poderá produzir um erro de serviço claro.
    """
    global _AVAILABLE_ENGINES_CACHE, _AVAILABLE_ENGINES_AT
    now = time.monotonic()
    if _AVAILABLE_ENGINES_CACHE is not None and now - _AVAILABLE_ENGINES_AT < _AVAILABLE_ENGINES_TTL:
        return set(_AVAILABLE_ENGINES_CACHE)
    fallback = _catalog_engines()
    try:
        import edge_tts
    except ImportError:
        _AVAILABLE_ENGINES_CACHE = fallback
        _AVAILABLE_ENGINES_AT = now
        return set(fallback)
    try:
        voices = await edge_tts.list_voices()
        engines = {item.get('ShortName') for item in voices if item.get('ShortName')}
        result = engines or fallback
    except asyncio.TimeoutError:
        result = fallback
    except _expected_service_errors(edge_tts):
        result = fallback
    except Exception:
        # A consulta é apenas validação preventiva; não escondemos erros da síntese.
        result = fallback
    _AVAILABLE_ENGINES_CACHE = result
    _AVAILABLE_ENGINES_AT = now
    return set(result)


def list_all_voices(language):
    """Lista vozes neurais do idioma; usa o catálogo fixo se a consulta falhar."""
    fallback = CATALOG.get(language, {}).get("voices", {})
    if not fallback:
        return {}
    cached = _LIVE_VOICE_CACHE.get(language)
    if cached and time.monotonic() - cached[0] < _LIVE_VOICE_CACHE_TTL:
        return cached[1]
    try:
        import edge_tts
        voices = asyncio.run(edge_tts.list_voices())
        # O motor não precisa ser do mesmo locale do idioma da interface: a voz
        # masculina de inglês usa en-GB. Por isso a checagem é pelo motor do
        # catálogo, não pelo prefixo do idioma.
        known = {profile['engine']: (voice_id, profile) for voice_id, profile in fallback.items()}
        live = {}
        for item in voices:
            short_name = item.get("ShortName", "")
            if short_name in known:
                voice_id, profile = known[short_name]
                # O rótulo é sempre o nosso ("Jarvis — ..."). O FriendlyName do
                # serviço traz nome de pessoa e não vai para a tela.
                live[voice_id] = {"label": profile["label"], "engine": short_name}
        result = live or fallback
    except (ImportError, OSError, asyncio.TimeoutError, ValueError):
        result = fallback
    except Exception:
        # A listagem é opcional; a síntese continua usando o catálogo conhecido.
        result = fallback
    _LIVE_VOICE_CACHE[language] = (time.monotonic(), result)
    return result


def catalog_for_client(live=False):
    return {
        language: {
            "label": data["label"],
            "sample": data["sample"],
            "voices": {
                key: item["label"]
                for key, item in (list_all_voices(language) if live else data["voices"]).items()
            },
        }
        for language, data in CATALOG.items()
    }


def _cached_engines():
    """Devolve a lista memorizada de motores, ou None se não houver uma fresca."""
    if _AVAILABLE_ENGINES_CACHE is None:
        return None
    if time.monotonic() - _AVAILABLE_ENGINES_AT >= _AVAILABLE_ENGINES_TTL:
        return None
    return set(_AVAILABLE_ENGINES_CACHE)


def warm_engines():
    """Memoriza a lista de motores em segundo plano, fora do caminho da fala.

    Chamada na inicialização do servidor. Sem isso, a primeira frase pagaria o
    tempo dessa consulta de rede antes de qualquer áudio sair.
    """
    import threading

    def tarefa():
        try:
            asyncio.run(available_engines())
        except Exception:
            # É só aquecimento: a síntese segue com o catálogo conhecido.
            pass

    threading.Thread(target=tarefa, daemon=True).start()


async def verify_engines():
    """Confere no serviço se os motores do catálogo existem. Usada pelo CLI."""
    engines = await available_engines()
    conhecidos = _catalog_engines()
    # Sem resposta do serviço, available_engines devolve o próprio catálogo.
    if engines == conhecidos:
        return None
    return {motor: motor in engines for motor in sorted(conhecidos)}


async def synthesize(text, language="pt-BR", voice=None, speed=1.15, pitch=DEFAULT_PITCH, volume=1.0):
    if language not in CATALOG:
        raise VoiceError("Idioma de voz inválido.", "invalid_language")
    requested_voice = voice
    voice = resolve_voice_id(voice, language)
    if requested_voice and requested_voice != voice:
        print(f'Voz {requested_voice!r} não existe mais em {language}; usando {voice!r}.', flush=True)
    profile = CATALOG[language]["voices"][voice]
    try:
        import edge_tts
    except ImportError as exc:
        raise VoiceError(
            "A voz natural não está instalada neste ambiente. Execute Jarvis.py, opção 1 (Instalar), e inicie o Jarvis pela mesma pasta.",
            "missing_dependency",
        ) from exc

    try:
        # A validação preventiva só espera a rede quando o motor é desconhecido.
        # Para os motores do próprio catálogo, usamos a lista já memorizada
        # (aquecida na inicialização); assim a primeira frase não espera a
        # consulta de list_voices, que custava centenas de milissegundos.
        engines = _cached_engines()
        if engines is None and profile["engine"] not in _catalog_engines():
            engines = await available_engines()
        if engines is not None and profile["engine"] not in engines:
            fallback_voice = DEFAULT_VOICES[language]
            fallback_profile = CATALOG[language]["voices"][fallback_voice]
            if fallback_profile["engine"] in engines and fallback_voice != voice:
                print(
                    f'Voz {profile["label"]!r} ({profile["engine"]}) não está disponível; '
                    f'usando {fallback_voice!r}.',
                    flush=True,
                )
                profile = fallback_profile
            else:
                raise VoiceError(
                    f'A voz {profile["label"]} não está disponível nesta versão do edge-tts. Escolha outra.',
                    "voice_unavailable",
                )
        speed = max(0.85, min(1.5, float(speed)))
        pitch = max(-10, min(10, int(pitch)))
        volume = max(0.5, min(1.2, float(volume)))
        rate = f"{round((speed - 1) * 100):+d}%"
        pitch_value = f"{pitch:+d}Hz"
        volume_value = f"{round((volume - 1) * 100):+d}%"
        chunks = []

        async def collect():
            communicator = edge_tts.Communicate(
                text,
                profile["engine"],
                rate=rate,
                pitch=pitch_value,
                volume=volume_value,
            )
            async for chunk in communicator.stream():
                if chunk.get("type") == "audio" and chunk.get("data"):
                    chunks.append(chunk["data"])

        await asyncio.wait_for(collect(), timeout=25)
        if not chunks:
            raise VoiceError("O serviço de voz não devolveu áudio.", "empty_audio")
        return b"".join(chunks)
    except VoiceError:
        raise
    except asyncio.TimeoutError as exc:
        raise VoiceError("A voz demorou mais de 25 segundos. Verifique a internet.", "timeout") from exc
    except _expected_service_errors(edge_tts) as exc:
        detail = str(exc).strip().replace("\n", " ")[:240]
        suffix = f" Detalhe: {detail}" if detail else ""
        raise VoiceError(
            "Não consegui gerar a voz natural. Verifique a internet e tente o botão Testar voz." + suffix,
            "service_error",
        ) from exc
    except Exception as exc:
        raise RuntimeError("Erro inesperado no sintetizador de voz; consulte o traceback do servidor.") from exc
