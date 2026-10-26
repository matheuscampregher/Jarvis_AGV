"""Detector de palmas (item 5). Não usa microfone nem numpy: alimenta picos.

Cada evento é descrito por início, pico e duração da cauda, e o detector recebe
um pico por bloco, como aconteceria com o microfone.
"""
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from jarvis import palma

PADROES = palma.PADROES
BLOCO_MS = 1000.0 * PADROES['bloco'] / PADROES['taxa_hz']


def simular(eventos, duracao_ms=3000, ajustes=None, detector=None):
    """Roda o detector sobre uma linha do tempo de picos.

    eventos: lista de (inicio_ms, pico, cauda_ms). Entre eventos, o pico é o
    piso de silêncio.
    """
    detector = detector or palma.Detector(ajustes)
    acionamentos = []
    instante = 0.0
    while instante < duracao_ms:
        pico = 0.005
        for inicio, altura, cauda in eventos:
            if inicio <= instante < inicio + cauda:
                # Queda linear até o fim da cauda; o formato exato não importa,
                # o que conta é passar do limiar e cair dentro da cauda.
                restante = 1 - (instante - inicio) / cauda
                pico = max(pico, altura * restante)
        if detector.alimentar(pico, instante):
            acionamentos.append(instante)
        instante += BLOCO_MS
    return acionamentos, detector


PALMA = 0.9
CAUDA_PALMA = 60.0


class DetectorTests(unittest.TestCase):
    def test_two_claps_in_range_trigger_once(self):
        acionamentos, _ = simular([(300, PALMA, CAUDA_PALMA), (650, PALMA, CAUDA_PALMA)])
        self.assertEqual(len(acionamentos), 1)

    def test_a_single_clap_does_not_trigger(self):
        acionamentos, _ = simular([(300, PALMA, CAUDA_PALMA)])
        self.assertEqual(acionamentos, [])

    def test_keyboard_click_is_rejected_because_the_tail_is_too_short(self):
        """Clique alto mas curtíssimo: não é palma."""
        curtos = [(300, 0.6, 6.0), (520, 0.6, 6.0), (700, 0.6, 6.0)]
        acionamentos, detector = simular(curtos)
        self.assertEqual(acionamentos, [])
        self.assertEqual(detector.palmas, 0)

    def test_sustained_sound_is_rejected(self):
        """Fala ou música: passa do limiar e não cai dentro de queda_ms."""
        acionamentos, detector = simular([(300, 0.8, 1200.0)])
        self.assertEqual(acionamentos, [])
        self.assertEqual(detector.palmas, 0)

    def test_interval_outside_the_range_does_not_trigger(self):
        for intervalo in (80, 120, 760, 1200):
            with self.subTest(intervalo=intervalo):
                acionamentos, _ = simular([(300, PALMA, CAUDA_PALMA),
                                           (300 + intervalo, PALMA, CAUDA_PALMA)])
                self.assertEqual(acionamentos, [], f'intervalo {intervalo} ms não deveria acionar')

    def test_interval_inside_the_range_triggers_including_the_edges(self):
        for intervalo in (160, 350, 690):
            with self.subTest(intervalo=intervalo):
                acionamentos, _ = simular([(300, PALMA, CAUDA_PALMA),
                                           (300 + intervalo, PALMA, CAUDA_PALMA)])
                self.assertEqual(len(acionamentos), 1, f'intervalo {intervalo} ms deveria acionar')

    def test_a_third_clap_does_not_trigger_again_during_the_wait(self):
        """Depois de acionar, espera 10 s antes de aceitar outra sequência."""
        eventos = [(300, PALMA, CAUDA_PALMA), (650, PALMA, CAUDA_PALMA),
                   (1500, PALMA, CAUDA_PALMA), (1850, PALMA, CAUDA_PALMA)]
        acionamentos, _ = simular(eventos, duracao_ms=4000)
        self.assertEqual(len(acionamentos), 1)

    def test_a_new_sequence_works_after_the_wait(self):
        espera = PADROES['espera_apos_acionar_s'] * 1000
        eventos = [(300, PALMA, CAUDA_PALMA), (650, PALMA, CAUDA_PALMA),
                   (700 + espera, PALMA, CAUDA_PALMA), (1050 + espera, PALMA, CAUDA_PALMA)]
        acionamentos, _ = simular(eventos, duracao_ms=espera + 2500)
        self.assertEqual(len(acionamentos), 2)

    def test_three_claps_count_the_last_pair(self):
        eventos = [(300, PALMA, CAUDA_PALMA), (1300, PALMA, CAUDA_PALMA), (1650, PALMA, CAUDA_PALMA)]
        acionamentos, _ = simular(eventos, duracao_ms=2500)
        self.assertEqual(len(acionamentos), 1)

    def test_a_higher_threshold_ignores_a_weak_clap(self):
        acionamentos, _ = simular([(300, 0.3, CAUDA_PALMA), (650, 0.3, CAUDA_PALMA)],
                                  ajustes={'limiar': 0.6})
        self.assertEqual(acionamentos, [])


class AjustesTests(unittest.TestCase):
    def test_defaults_are_used_without_a_palma_section(self):
        self.assertEqual(palma.ler_ajustes({}), PADROES)
        self.assertEqual(palma.ler_ajustes({'palma': 'texto'}), PADROES)

    def test_values_from_config_replace_the_defaults(self):
        ajustes = palma.ler_ajustes({'palma': {'limiar': 0.5, 'intervalo_maximo_ms': 900}})
        self.assertEqual(ajustes['limiar'], 0.5)
        self.assertEqual(ajustes['intervalo_maximo_ms'], 900)
        self.assertEqual(ajustes['queda_ms'], PADROES['queda_ms'])

    def test_invalid_values_fall_back_with_a_message(self):
        with redirect_stdout(io.StringIO()) as saida:
            ajustes = palma.ler_ajustes({'palma': {'limiar': 'alto', 'queda_ms': -5, 'bloco': True}})
        self.assertEqual(ajustes['limiar'], PADROES['limiar'])
        self.assertEqual(ajustes['queda_ms'], PADROES['queda_ms'])
        self.assertEqual(ajustes['bloco'], PADROES['bloco'])
        texto = saida.getvalue()
        self.assertIn('palma.limiar', texto)
        self.assertIn('palma.queda_ms', texto)

    def test_device_can_be_a_name_or_a_number(self):
        self.assertEqual(palma.ler_ajustes({'palma': {'dispositivo': 2}})['dispositivo'], 2)
        self.assertEqual(palma.ler_ajustes({'palma': {'dispositivo': 'Microfone'}})['dispositivo'], 'Microfone')
        self.assertIsNone(palma.ler_ajustes({'palma': {'dispositivo': []}})['dispositivo'])

    def test_a_broken_config_does_not_stop_the_listener(self):
        with patch.object(palma, 'read_config', side_effect=RuntimeError('config inválido')):
            self.assertEqual(palma.ler_ajustes(), PADROES)


class SemMicrofoneTests(unittest.TestCase):
    def test_listener_exits_with_a_clear_message_and_no_crash(self):
        with patch.object(palma, '_abrir_microfone',
                          return_value=(None, 'Não encontrei um microfone disponível para o Jarvis.')), \
                redirect_stdout(io.StringIO()) as saida:
            self.assertEqual(palma.escutar(), 1)
        self.assertIn('microfone', saida.getvalue())

    def test_missing_library_is_reported_as_such(self):
        with patch.dict(sys.modules, {'sounddevice': None}), redirect_stdout(io.StringIO()):
            modulo, erro = palma._abrir_microfone(PADROES)
        self.assertIsNone(modulo)
        self.assertTrue(erro)
        self.assertIn('sounddevice', erro)

    def test_this_environment_has_no_microphone_and_says_so(self):
        """Confirma que a mensagem de erro real aparece onde não há áudio."""
        modulo, erro = palma._abrir_microfone(PADROES)
        if modulo is not None:
            self.skipTest('este ambiente tem microfone')
        self.assertTrue(erro.strip())
        self.assertNotIn('Traceback', erro)


class AcionarTests(unittest.TestCase):
    def test_an_already_running_server_only_opens_the_browser(self):
        with patch.object(palma, 'servidor_de_pe', return_value=True), \
                patch.object(palma, 'iniciar_servidor') as iniciar, \
                patch.object(palma, 'webbrowser') as navegador, \
                redirect_stdout(io.StringIO()):
            self.assertTrue(palma.acionar())
        iniciar.assert_not_called()
        navegador.open.assert_called_once_with(palma.URL)

    def test_a_stopped_server_is_started_before_the_browser(self):
        ordem = []
        with patch.object(palma, 'servidor_de_pe', return_value=False), \
                patch.object(palma, 'iniciar_servidor', side_effect=lambda: ordem.append('servidor') or True), \
                patch.object(palma, 'webbrowser') as navegador, \
                redirect_stdout(io.StringIO()):
            navegador.open.side_effect = lambda url: ordem.append('navegador')
            self.assertTrue(palma.acionar())
        self.assertEqual(ordem, ['servidor', 'navegador'])

    def test_the_browser_is_not_opened_when_the_server_fails(self):
        with patch.object(palma, 'servidor_de_pe', return_value=False), \
                patch.object(palma, 'iniciar_servidor', return_value=False), \
                patch.object(palma, 'webbrowser') as navegador, \
                redirect_stdout(io.StringIO()):
            self.assertFalse(palma.acionar())
        navegador.open.assert_not_called()

    def test_the_started_server_is_told_not_to_open_the_browser_itself(self):
        capturado = {}

        class FalsoPopen:
            def __init__(self, comando, cwd=None, env=None):
                capturado['comando'] = comando
                capturado['env'] = env

        with patch.object(palma.subprocess, 'Popen', FalsoPopen), \
                patch.object(palma, 'servidor_de_pe', return_value=True), \
                redirect_stdout(io.StringIO()):
            self.assertTrue(palma.iniciar_servidor())
        self.assertEqual(capturado['env']['JARVIS_SEM_NAVEGADOR'], '1')
        self.assertIn('jarvis', capturado['comando'])


class PrivacidadeTests(unittest.TestCase):
    def test_no_audio_is_written_or_sent(self):
        """O módulo não grava arquivo de áudio nem faz requisição de rede."""
        fonte = (Path(__file__).resolve().parents[1] / 'palma.py').read_text(encoding='utf-8')
        for proibido in ('write_bytes', 'wave', 'soundfile', 'urllib', 'requests', '.wav', '.mp3'):
            self.assertNotIn(proibido, fonte, f'palma.py não deveria usar {proibido}')

    def test_the_detector_only_receives_numbers(self):
        detector = palma.Detector()
        self.assertFalse(detector.alimentar(0.01, 0.0))
        # Guarda só números: nenhum bloco de áudio fica em memória.
        for valor in vars(detector).values():
            self.assertIsInstance(valor, (int, float, dict, type(None)))


if __name__ == '__main__':
    unittest.main()
