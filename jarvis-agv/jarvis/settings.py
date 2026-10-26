"""Configuração do servidor fora de web. Credenciais Google ficam na pasta segredos.

Pastas usadas pelo programa:
- PACOTE: a pasta jarvis/, que contém este arquivo, web/, docs/ e tests/.
- ROOT: onde fica web/. Fora do executável é a própria pasta jarvis/. No
  executável, é a pasta interna onde o PyInstaller coloca web/.
- DATA: onde ficam config.json, dados/ e segredos/. Fora do executável é a
  pasta jarvis/, ao lado deste arquivo. No executável, é a pasta ao lado de
  JarvisAGV.exe.
"""
import json
import sys
from pathlib import Path

FROZEN = getattr(sys, 'frozen', False)
PACOTE = Path(__file__).resolve().parent
ROOT = Path(getattr(sys, '_MEIPASS', PACOTE)) if FROZEN else PACOTE
DATA = Path(sys.executable).resolve().parent if FROZEN else PACOTE
WEB = ROOT / 'web'
REQUIREMENTS = PACOTE / 'requirements.txt'

# Única definição do modelo usada na chamada ao Ollama (app.py importa daqui).
MODEL = 'qwen3:4b-instruct-2507-q4_K_M'


def read_config():
    file = DATA / 'config.json'
    if not file.exists():
        return {}
    try:
        data = json.loads(file.read_text(encoding='utf-8-sig'))
        if not isinstance(data, dict):
            raise ValueError()
        return data
    except (ValueError, OSError) as exc:
        raise RuntimeError('O responsável precisa corrigir o arquivo config.json.') from exc
