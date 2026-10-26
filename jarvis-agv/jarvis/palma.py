"""Abre o Jarvis ao bater duas palmas.

Privacidade: nenhum áudio é gravado, salvo ou enviado para fora. De cada bloco
curto do microfone só se calcula o pico (um número), em memória. O bloco é
descartado em seguida; não existe arquivo de áudio nem envio pela rede.

Como funciona a detecção:
- Palma é um som que sobe muito rápido e cai rápido. Um bloco cujo pico passa
  do limiar, vindo de um bloco silencioso, abre um candidato.
- O candidato só conta como palma se o som cair abaixo do limiar de queda
  dentro de `queda_ms`. Fala e música não caem tão rápido e são descartadas.
- A cauda também precisa durar ao menos `duracao_minima_ms`. É isso que separa
  uma palma de um clique de teclado: a palma ainda soa por umas dezenas de
  milissegundos, o clique termina em poucos milissegundos.
- Duas palmas separadas por `intervalo_minimo_ms` a `intervalo_maximo_ms`,
  dentro de `janela_ms`, acionam o Jarvis.
- Depois de acionar, espera `espera_apos_acionar_s` antes de aceitar outra
  sequência, para não abrir várias janelas.

Os valores ficam em config.json, na seção "palma", e podem ser ajustados sem
mexer no código.
"""
import os
import socket
import subprocess
import sys
import time
import webbrowser

from .settings import DATA, FROZEN, read_config

URL = 'http://127.0.0.1:8000'
PORTA = 8000

PADROES = {
    'limiar': 0.25,              # fração do máximo (0 a 1) para considerar um pico
    'limiar_queda': 0.12,        # abaixo disso o som é considerado terminado
    'queda_ms': 150,             # a palma precisa cair dentro deste tempo
    'duracao_minima_ms': 20,     # cauda mínima; abaixo disso é clique de teclado
    'intervalo_minimo_ms': 150,  # tempo mínimo entre as duas palmas
    'intervalo_maximo_ms': 700,  # tempo máximo entre as duas palmas
    'janela_ms': 1500,           # as duas palmas precisam caber nesta janela
    'espera_apos_acionar_s': 10,
    'taxa_hz': 16000,
    'bloco': 128,                # 8 ms a 16 kHz
    'dispositivo': None,         # None usa o microfone padrão do sistema
}


def ler_ajustes(config=None):
    """Junta os padrões com a seção "palma" do config.json."""
    if config is None:
        try:
            config = read_config()
        except RuntimeError:
            config = {}
    secao = config.get('palma') if isinstance(config, dict) else None
    ajustes = dict(PADROES)
    if isinstance(secao, dict):
        for chave, padrao in PADROES.items():
            if chave not in secao:
                continue
            valor = secao[chave]
            if chave == 'dispositivo':
                ajustes[chave] = valor if isinstance(valor, (int, str)) else None
            elif isinstance(valor, bool) or not isinstance(valor, (int, float)):
                print(f'config.json: palma.{chave} inválido; usando {padrao}.')
            elif valor <= 0:
                print(f'config.json: palma.{chave} precisa ser maior que zero; usando {padrao}.')
            else:
                ajustes[chave] = type(padrao)(valor) if padrao is not None else valor
    return ajustes


class Detector:
    """Recebe o pico de cada bloco e diz quando a sequência de palmas aconteceu.

    Trabalha só com números, para poder ser testado sem microfone.
    """

    def __init__(self, ajustes=None):
        self.a = dict(PADROES)
        self.a.update(ajustes or {})
        self.bloco_ms = 1000.0 * self.a['bloco'] / self.a['taxa_hz']
        self.anterior = 0.0
        self.candidato_em = None   # instante (ms) do início do pico em análise
        self.ultima_palma = None   # instante (ms) da última palma confirmada
        self.bloqueado_ate = 0.0
        self.palmas = 0

    def _confirmar_palma(self, instante):
        """Registra uma palma e devolve True se completou a sequência."""
        self.palmas += 1
        anterior = self.ultima_palma
        self.ultima_palma = instante
        if anterior is None:
            return False
        intervalo = instante - anterior
        if not self.a['intervalo_minimo_ms'] <= intervalo <= self.a['intervalo_maximo_ms']:
            # Fora do intervalo: esta palma passa a ser a primeira de uma nova dupla.
            return False
        if intervalo > self.a['janela_ms']:
            return False
        self.bloqueado_ate = instante + self.a['espera_apos_acionar_s'] * 1000
        self.ultima_palma = None
        return True

    def alimentar(self, pico, instante_ms):
        """Processa um bloco. Devolve True quando o Jarvis deve abrir."""
        acionou = False
        if instante_ms < self.bloqueado_ate:
            self.anterior = pico
            self.candidato_em = None
            self.ultima_palma = None
            return False
        limiar = self.a['limiar']
        if self.candidato_em is None:
            # Subida rápida: bloco alto vindo de um bloco baixo.
            if pico >= limiar and self.anterior < limiar * 0.5:
                self.candidato_em = instante_ms
        else:
            if pico < self.a['limiar_queda']:
                duracao = instante_ms - self.candidato_em
                if duracao >= self.a['duracao_minima_ms']:
                    acionou = self._confirmar_palma(self.candidato_em)
                # Cauda curta demais: clique de teclado, mouse ou estalo.
                self.candidato_em = None
            elif instante_ms - self.candidato_em > self.a['queda_ms']:
                # Não caiu a tempo: som contínuo (fala, música, ruído).
                self.candidato_em = None
        # Esquece uma palma solitária que ficou velha. A margem de queda_ms existe
        # porque a segunda palma só é confirmada quando o som dela cai: o início
        # dela pode estar dentro do intervalo mesmo que a confirmação chegue depois.
        limite = self.a['intervalo_maximo_ms'] + self.a['queda_ms']
        if self.ultima_palma is not None and instante_ms - self.ultima_palma > limite:
            self.ultima_palma = None
        self.anterior = pico
        return acionou


def servidor_de_pe(porta=PORTA, timeout=0.4):
    with socket.socket() as s:
        s.settimeout(timeout)
        return s.connect_ex(('127.0.0.1', porta)) == 0


def iniciar_servidor():
    """Sobe o Jarvis sem que ele abra o navegador (quem abre é esta função)."""
    novo = dict(os.environ)
    novo['JARVIS_SEM_NAVEGADOR'] = '1'
    # No executável, rodar o próprio .exe já inicia o servidor.
    comando = [sys.executable] if FROZEN else [sys.executable, '-m', 'jarvis', 'servir']
    pasta = DATA if FROZEN else DATA.parent
    try:
        subprocess.Popen(comando, cwd=str(pasta), env=novo)
    except OSError as exc:
        print('Não consegui iniciar o Jarvis:', exc)
        return False
    for _ in range(40):  # até ~20 s
        if servidor_de_pe():
            return True
        time.sleep(0.5)
    print('O Jarvis não respondeu na porta 8000 em 20 segundos.')
    return False


def acionar():
    """Abre o Jarvis: inicia o servidor se preciso e chama o navegador."""
    if servidor_de_pe():
        print('Jarvis já está de pé; trazendo a janela para a frente.')
    else:
        print('Iniciando o Jarvis...')
        if not iniciar_servidor():
            return False
    webbrowser.open(URL)
    return True


def _abrir_microfone(ajustes):
    """Devolve (sounddevice, erro). O erro já é uma mensagem pronta."""
    try:
        import sounddevice
    except ImportError:
        return None, ('A biblioteca sounddevice não está instalada.\n'
                      'Execute Jarvis.py, opção 1 (Instalar), e tente de novo.')
    except OSError as exc:
        return None, ('A biblioteca de áudio do sistema (PortAudio) não foi encontrada.\n'
                      f'Detalhe: {exc}')
    try:
        sounddevice.check_input_settings(
            device=ajustes['dispositivo'], channels=1,
            samplerate=ajustes['taxa_hz'], dtype='float32')
    except Exception as exc:
        return None, ('Não encontrei um microfone disponível para o Jarvis.\n'
                      'Conecte um microfone e confira as permissões do sistema.\n'
                      f'Detalhe: {exc}')
    return sounddevice, None


def _nome_do_microfone(sounddevice, ajustes):
    """Nome da entrada em uso, só para a mensagem na tela."""
    try:
        alvo = ajustes['dispositivo']
        if alvo is None:
            alvo = sounddevice.default.device[0]
        return sounddevice.query_devices(alvo)['name']
    except Exception:
        return 'entrada padrão do sistema'


def calibrar(ajustes=None, segundos=20):
    """Mostra o que o microfone capta e sugere um limiar.

    Serve para quando as palmas não são detectadas: aqui dá para ver se o
    microfone está ouvindo e com que força chega cada palma.
    """
    ajustes = ajustes or ler_ajustes()
    sounddevice, erro = _abrir_microfone(ajustes)
    if erro:
        print(erro)
        return 1
    import numpy

    print(f'Microfone: {_nome_do_microfone(sounddevice, ajustes)}')
    print(f'Limiar atual: {ajustes["limiar"]}.')
    print(f'Bata palmas algumas vezes. Medindo por {segundos} segundos; Ctrl+C encerra antes.')
    print('Nenhum áudio é gravado nem enviado: só o pico de cada bloco é calculado.\n')
    maior = 0.0
    picos = []
    inicio = time.monotonic()
    ultimo_aviso = 0.0
    try:
        with sounddevice.InputStream(device=ajustes['dispositivo'], channels=1,
                                     samplerate=ajustes['taxa_hz'], dtype='float32',
                                     blocksize=ajustes['bloco']) as stream:
            while time.monotonic() - inicio < segundos:
                bloco, _ = stream.read(ajustes['bloco'])
                pico = float(numpy.max(numpy.abs(bloco))) if len(bloco) else 0.0
                maior = max(maior, pico)
                agora = time.monotonic()
                # Uma linha a cada 120 ms, para a tela não virar uma cascata.
                if pico >= 0.05 and agora - ultimo_aviso > 0.12:
                    ultimo_aviso = agora
                    picos.append(pico)
                    marca = '#' * min(40, int(pico * 40))
                    passou = 'passa do limiar' if pico >= ajustes['limiar'] else ''
                    print(f'  pico {pico:.3f} {marca} {passou}')
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print('A medição parou por um erro:', exc)
        return 1
    print()
    if not picos:
        print(f'Nenhum som acima de 0.05 chegou (maior pico: {maior:.3f}).')
        print('O microfone pode estar mudo, com volume baixo, ou bloqueado em')
        print('Configurações do Windows > Privacidade > Microfone.')
        return 1
    altos = sorted(picos, reverse=True)[:10]
    media = sum(altos) / len(altos)
    sugerido = round(max(0.08, min(0.8, media * 0.45)), 2)
    print(f'Maior pico: {maior:.3f}. Média dos dez maiores: {media:.3f}.')
    if maior < ajustes['limiar']:
        print('Nenhuma palma passou do limiar atual: é por isso que nada acontece.')
    print(f'Limiar sugerido: {sugerido}')
    print('Para usar, acrescente ao config.json, ao lado de "google_sheets":')
    print(f'  "palma": {{ "limiar": {sugerido} }}')
    return 0


def escutar(ajustes=None, detector=None, parar=None):
    """Laço principal. Devolve o código de saída."""
    ajustes = ajustes or ler_ajustes()
    sounddevice, erro = _abrir_microfone(ajustes)
    if erro:
        print(erro)
        return 1
    import numpy

    detector = detector or Detector(ajustes)
    print(f'Microfone: {_nome_do_microfone(sounddevice, ajustes)}')
    print(f'Escutando o microfone. Bata duas palmas para abrir o Jarvis ({URL}).')
    print(f'Limiar {ajustes["limiar"]}, intervalo de {ajustes["intervalo_minimo_ms"]} '
          f'a {ajustes["intervalo_maximo_ms"]} ms. Ctrl+C encerra.')
    print('Nenhum áudio é gravado nem enviado: só o pico de cada bloco é calculado.')
    inicio = time.monotonic()
    try:
        with sounddevice.InputStream(device=ajustes['dispositivo'], channels=1,
                                     samplerate=ajustes['taxa_hz'], dtype='float32',
                                     blocksize=ajustes['bloco']) as stream:
            while parar is None or not parar():
                bloco, _ = stream.read(ajustes['bloco'])
                # Só o pico sai daqui; o bloco é descartado na próxima volta.
                pico = float(numpy.max(numpy.abs(bloco))) if len(bloco) else 0.0
                instante = (time.monotonic() - inicio) * 1000
                if detector.alimentar(pico, instante):
                    print('Duas palmas detectadas.')
                    acionar()
    except KeyboardInterrupt:
        print('\nEncerrado.')
    except Exception as exc:
        print('O escutador de palmas parou por um erro:', exc)
        return 1
    return 0


def main(args=None):
    args = list(args or [])
    if '--calibrar' in args or '--testar' in args:
        print('\n=== Jarvis AGV: medindo o microfone ===')
        return calibrar()
    print('\n=== Jarvis AGV: abrir com duas palmas ===')
    return escutar()


if __name__ == '__main__':
    sys.exit(main())
