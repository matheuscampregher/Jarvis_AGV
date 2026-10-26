"""JARVIS AGV - único arquivo para executar.

Sem argumentos, faz tudo em sequência: prepara o ambiente, instala o que falta,
abre o configurador na primeira vez e inicia o Jarvis. Funciona no Windows e no
Termux/Linux.

    python Jarvis.py              prepara o que falta e inicia o Jarvis
    python Jarvis.py menu         ferramentas avançadas
    python Jarvis.py iniciar      (também: instalar, configurar, testar, voz,
                                  rede, palma, exe)

O ambiente Python fica fora da pasta do projeto, para que mover ou recriar a
pasta não obrigue a instalar tudo de novo:
    Windows: %LOCALAPPDATA%\\JarvisAGV\\venv
    Termux/Linux: ~/.local/share/JarvisAGV/venv
"""
import hashlib
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
PACOTE = RAIZ / 'jarvis'
REQUISITOS = PACOTE / 'requirements.txt'
CONFIG = PACOTE / 'config.json'
WINDOWS = os.name == 'nt'
PYTHON_MINIMO = (3, 10)
LINK_PYTHON = 'https://www.python.org/downloads/'


def console_utf8():
    """Faz o console aceitar acentos (equivale ao chcp 65001 do Windows)."""
    if WINDOWS:
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass


def pasta_ambiente():
    if WINDOWS:
        base = os.environ.get('LOCALAPPDATA') or (Path.home() / 'AppData' / 'Local')
    else:
        base = os.environ.get('XDG_DATA_HOME') or (Path.home() / '.local' / 'share')
    return Path(base) / 'JarvisAGV' / 'venv'


AMBIENTE = pasta_ambiente()
PY_AMBIENTE = AMBIENTE / ('Scripts' if WINDOWS else 'bin') / ('python.exe' if WINDOWS else 'python')
MARCA = AMBIENTE / 'requisitos-instalados.sha256'


def executar(args):
    """Roda um comando na pasta do projeto e devolve o código de saída.

    Os argumentos vão em lista, então caminhos com espaço e acento não precisam
    de aspas e não são reinterpretados pelo shell.
    """
    return subprocess.run([str(a) for a in args], cwd=str(RAIZ)).returncode


def falha(mensagem):
    print(mensagem)
    return 1


def checar_python():
    if sys.version_info >= PYTHON_MINIMO:
        return True
    atual = '.'.join(str(n) for n in sys.version_info[:3])
    minimo = '.'.join(str(n) for n in PYTHON_MINIMO)
    print(f'Este Python é o {atual}, e o Jarvis precisa do {minimo} ou mais novo.')
    print(f'Baixe uma versão atual em {LINK_PYTHON} e execute este arquivo de novo.')
    if WINDOWS:
        print('Na instalação, marque a opção "Add python.exe to PATH".')
    return False


def preparar_ambiente(avisar=True):
    """Cria o ambiente se faltar. Devolve True quando ele está pronto."""
    if PY_AMBIENTE.exists():
        return True
    if avisar:
        print(f'Preparando o ambiente em {AMBIENTE} (só na primeira vez).')
    try:
        AMBIENTE.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return bool(falha(f'Não consegui criar a pasta do ambiente: {exc}'))
    if executar([sys.executable, '-m', 'venv', AMBIENTE]) != 0 or not PY_AMBIENTE.exists():
        print('Não consegui criar o ambiente Python.')
        if not WINDOWS:
            print('No Termux: pkg install python. No Debian/Ubuntu: sudo apt install python3-venv.')
        else:
            print(f'Reinstale o Python por {LINK_PYTHON}, marcando "Add python.exe to PATH".')
        return False
    return True


def assinatura_requisitos():
    try:
        return hashlib.sha256(REQUISITOS.read_bytes()).hexdigest()
    except OSError:
        return None


def instalar_requisitos(forcar=False):
    """Instala as dependências só quando requirements.txt mudou."""
    assinatura = assinatura_requisitos()
    if assinatura is None:
        return falha(f'Não encontrei {REQUISITOS}. Extraia o ZIP inteiro antes de executar.')
    try:
        instalada = MARCA.read_text(encoding='utf-8').strip()
    except OSError:
        instalada = ''
    if instalada == assinatura and not forcar:
        return 0
    print('Instalando as dependências (voz e leitura de planilhas). Precisa de internet.')
    if executar([PY_AMBIENTE, '-m', 'pip', 'install', '--upgrade', 'pip']) != 0:
        print('Aviso: não consegui atualizar o pip. Seguindo com a versão atual.')
    if executar([PY_AMBIENTE, '-m', 'pip', 'install', '--upgrade', '-r', REQUISITOS]) != 0:
        return falha('Falha ao instalar as dependências. Confira a internet e a mensagem acima.')
    try:
        MARCA.write_text(assinatura, encoding='utf-8')
    except OSError:
        print('Aviso: instalou, mas não consegui anotar a marca; a próxima execução vai reinstalar.')
    return 0


def instalar():
    print('\n=== Instalando o Jarvis AGV: voz e leitura de planilhas ===')
    if not checar_python() or not preparar_ambiente():
        return 1
    if instalar_requisitos(forcar=True) != 0:
        return 1
    if executar([PY_AMBIENTE, '-c', 'import edge_tts, google.auth, requests']) != 0:
        return falha('As dependências não ficaram completas. Veja a mensagem acima.')
    print('Instalação concluída: voz e conexão Google prontas.')
    print('Próximo passo: opção 2 (Configurar a planilha), ou apenas execute este arquivo.')
    return 0


def pronto_para_usar():
    """Garante Python, ambiente e dependências antes de qualquer comando."""
    if not checar_python() or not preparar_ambiente():
        return False
    return instalar_requisitos() == 0


def comando_jarvis(*args):
    if not pronto_para_usar():
        return 1
    return executar([PY_AMBIENTE, '-m', 'jarvis', *args])


def configurar():
    return comando_jarvis('configurar')


def testar():
    return comando_jarvis('testar-planilha')


def voz():
    return comando_jarvis('testar-voz')


def palma():
    return comando_jarvis('palma')


def iniciar(*extra):
    print(f'\nIniciando o Jarvis AGV na pasta: {RAIZ}')
    if comando_jarvis('servir', *extra) != 0:
        print('O programa encontrou um erro. Veja a mensagem acima.')
        return 1
    return 0


def rede():
    print('Modo rede: os alunos abrem http://IP-DESTE-COMPUTADOR:8000 (a porta 8000 precisa estar liberada).')
    return iniciar('--rede')


def abrir():
    """O caminho de quem só quer usar: prepara, configura se preciso e inicia."""
    if not pronto_para_usar():
        return 1
    if not CONFIG.exists():
        print('\nPrimeira vez: vou abrir o configurador da planilha.')
        if executar([PY_AMBIENTE, '-m', 'jarvis', 'configurar']) != 0:
            return falha('A configuração não foi concluída. Execute este arquivo de novo.')
        if not CONFIG.exists():
            return falha('A planilha não foi configurada. Execute este arquivo de novo quando puder concluir.')
    print('Ferramentas avançadas: python Jarvis.py menu')
    return iniciar()


def gerar_exe():
    if not pronto_para_usar():
        return 1
    print('\n=== Gerando o executável (PyInstaller) ===')
    if executar([PY_AMBIENTE, '-m', 'pip', 'install', '--upgrade', '-r', REQUISITOS, 'pyinstaller']) != 0:
        return falha('Falha ao preparar o PyInstaller. Veja as mensagens acima.')
    separador = ';' if WINDOWS else ':'
    comando = [
        PY_AMBIENTE, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--name', 'JarvisAGV',
        '--paths', '.', '--add-data', f'{os.path.join("jarvis", "web")}{separador}web',
        '--collect-all', 'edge_tts', '--hidden-import', 'edge_tts',
        '--hidden-import', 'google.oauth2.service_account',
        '--hidden-import', 'google.auth.transport.requests',
        '--collect-all', 'google.auth', '--collect-all', 'certifi',
        os.path.join('jarvis', '__main__.py'),
    ]
    if executar(comando) != 0:
        return falha('Falha ao gerar o executável. Veja as mensagens acima.')
    nome = 'JarvisAGV.exe' if WINDOWS else 'JarvisAGV'
    print(f'\nExecutável gerado em dist/JarvisAGV/{nome}.')
    print('Copie config.json e a pasta dados (modo 2) ou segredos (modo 3) para o lado do executável,')
    print('somente no computador servidor. O Ollama e o modelo continuam separados.')
    print('Não distribua as pastas dados e segredos aos alunos.')
    return 0


ACOES = {
    '1': ('Instalar ou atualizar', instalar),
    '2': ('Configurar a planilha', configurar),
    '3': ('Testar a planilha', testar),
    '4': ('Testar a voz', voz),
    '5': ('Iniciar o Jarvis neste computador', iniciar),
    '6': ('Iniciar o Jarvis na rede da escola', rede),
    '7': ('Ligar com palma (escutador do microfone)', palma),
    '8': ('Gerar executável (avançado)', gerar_exe),
}
ATALHOS = {
    'instalar': instalar, 'configurar': configurar, 'testar': testar, 'voz': voz,
    'iniciar': iniciar, 'rede': rede, 'palma': palma, 'exe': gerar_exe, 'abrir': abrir,
}


def mostrar_menu():
    print('=' * 58)
    print('  JARVIS AGV - ferramentas')
    print('=' * 58)
    print()
    for numero, (texto, _) in ACOES.items():
        print(f'  {numero} - {texto}')
    print('  0 - Sair')
    print()


def menu():
    while True:
        mostrar_menu()
        try:
            escolha = input('Escolha uma opção: ').strip()
        except EOFError:
            return 0
        if escolha == '0':
            return 0
        acao = ACOES.get(escolha)
        if acao is None:
            print('Opção inválida. Digite um número do menu.\n')
            continue
        acao[1]()
        print()


def main(argv=None):
    console_utf8()
    argumentos = sys.argv[1:] if argv is None else list(argv)
    try:
        if not argumentos:
            return abrir()
        primeiro = argumentos[0].lower()
        if primeiro == 'menu':
            return menu()
        if primeiro in ATALHOS:
            return ATALHOS[primeiro]()
        print(f'Opção desconhecida: {argumentos[0]}')
        print('Use: python Jarvis.py [menu | instalar | configurar | testar | voz '
              '| iniciar | rede | palma | exe]')
        return 2
    except KeyboardInterrupt:
        print('\nInterrompido.')
        return 130


if __name__ == '__main__':
    sys.exit(main())
