"""Teste da voz natural: gera teste-voz.mp3 com a voz do Jarvis e tenta abrir o arquivo.

Também confere, no serviço, se os motores do catálogo existem. Essa conferência
não pode ser feita sem internet, então aqui ela só informa; a falta de um motor
não impede o teste de áudio.
"""
import asyncio
import os
import sys

from . import voice
from .settings import DATA


def conferir_motores():
    """Informa quais motores do catálogo o serviço reconhece."""
    try:
        resultado = asyncio.run(voice.verify_engines())
    except Exception as exc:
        print('Não foi possível consultar a lista de vozes do serviço.')
        print('Detalhe:', exc)
        return
    if resultado is None:
        print('Não foi possível confirmar a lista de vozes do serviço (sem internet ou serviço fora).')
        print('O catálogo conhecido será usado como está.')
        return
    for motor, existe in resultado.items():
        print(('  existe      ' if existe else '  NÃO EXISTE ') + motor)
    faltando = [motor for motor, existe in resultado.items() if not existe]
    if faltando:
        print('Avise o responsável: os motores acima precisam ser trocados em jarvis/voice.py.')
    else:
        print('Todos os motores do catálogo existem no serviço.')


def main():
    print('\n=== Teste da voz natural do Jarvis AGV ===')
    if not voice.available():
        print('edge-tts não foi encontrado neste ambiente.')
        print('Execute Jarvis.py, opção 1 (Instalar), e tente novamente.')
        return 1
    print('edge-tts encontrado')
    print('\nConferindo os motores de voz no serviço:')
    conferir_motores()
    idioma = 'pt-BR'
    escolhida = voice.DEFAULT_VOICES[idioma]
    rotulo = voice.CATALOG[idioma]['voices'][escolhida]['label']
    print(f'\nGerando áudio com {rotulo} e tom {voice.DEFAULT_PITCH}.')
    target = DATA / 'teste-voz.mp3'
    try:
        audio = asyncio.run(voice.synthesize(
            voice.CATALOG[idioma]['sample'], idioma, escolhida, 1.15, voice.DEFAULT_PITCH, 1.0))
        target.write_bytes(audio)
    except Exception as exc:  # a síntese depende de rede e de um serviço externo
        print('Não foi possível gerar áudio. Verifique a internet.')
        print('Detalhe:', exc)
        return 1
    print(f'Áudio criado em {target.name}. Abrindo agora...')
    if hasattr(os, 'startfile'):  # somente Windows
        os.startfile(target)
    return 0


if __name__ == '__main__':
    sys.exit(main())
