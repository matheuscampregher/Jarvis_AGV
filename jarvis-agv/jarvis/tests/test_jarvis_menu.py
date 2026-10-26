"""Jarvis.py: único arquivo de entrada. Nada é instalado nem executado de verdade."""
import importlib.util
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('jarvis_entrada', RAIZ / 'Jarvis.py')
entrada = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entrada)


class EntradaTests(unittest.TestCase):
    def rodar(self, *args):
        saida = io.StringIO()
        with redirect_stdout(saida):
            codigo = entrada.main(list(args))
        return codigo, saida.getvalue()

    def test_unknown_shortcut_returns_usage_error(self):
        codigo, texto = self.rodar('inexistente')
        self.assertEqual(codigo, 2)
        self.assertIn('Use: python Jarvis.py', texto)

    def test_menu_command_lists_options_and_exits(self):
        saida = io.StringIO()
        with patch('builtins.input', return_value='0'), redirect_stdout(saida):
            self.assertEqual(entrada.main(['menu']), 0)
        texto = saida.getvalue()
        self.assertIn('Gerar executável', texto)
        self.assertIn('Ligar com palma', texto)

    def test_menu_rejects_invalid_option_then_exits(self):
        saida = io.StringIO()
        with patch('builtins.input', side_effect=['9', '0']), redirect_stdout(saida):
            self.assertEqual(entrada.main(['menu']), 0)
        self.assertIn('Opção inválida', saida.getvalue())

    def test_shortcuts_cover_every_menu_option(self):
        acoes = {funcao for _, funcao in entrada.ACOES.values()}
        self.assertTrue(acoes.issubset(set(entrada.ATALHOS.values())))
        self.assertEqual(sorted(entrada.ACOES), ['1', '2', '3', '4', '5', '6', '7', '8'])

    def test_commands_stop_when_environment_cannot_be_prepared(self):
        with patch.object(entrada, 'preparar_ambiente', return_value=False), \
                patch.object(entrada, 'executar') as executar, redirect_stdout(io.StringIO()):
            self.assertEqual(entrada.configurar(), 1)
            executar.assert_not_called()

    def test_environment_lives_outside_the_project_folder(self):
        """O ambiente fica em %LOCALAPPDATA% (ou ~/.local/share), não na pasta do ZIP."""
        self.assertFalse(str(entrada.AMBIENTE).startswith(str(entrada.RAIZ)))
        self.assertEqual(entrada.AMBIENTE.name, 'venv')
        self.assertEqual(entrada.AMBIENTE.parent.name, 'JarvisAGV')

    def test_requirements_are_installed_only_when_the_file_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            requisitos = Path(tmp) / 'requirements.txt'
            requisitos.write_text('edge-tts>=7.2,<8\n', encoding='utf-8')
            marca = Path(tmp) / 'requisitos-instalados.sha256'
            chamadas = []
            with patch.object(entrada, 'REQUISITOS', requisitos), \
                    patch.object(entrada, 'MARCA', marca), \
                    patch.object(entrada, 'executar', side_effect=lambda args: chamadas.append(args) or 0), \
                    redirect_stdout(io.StringIO()):
                self.assertEqual(entrada.instalar_requisitos(), 0)
                primeira = len(chamadas)
                self.assertEqual(entrada.instalar_requisitos(), 0)
                self.assertEqual(len(chamadas), primeira, 'não deveria reinstalar sem mudança')
                requisitos.write_text('edge-tts>=7.2,<8\nnumpy>=2\n', encoding='utf-8')
                self.assertEqual(entrada.instalar_requisitos(), 0)
                self.assertGreater(len(chamadas), primeira, 'deveria reinstalar após mudança')

    def test_missing_requirements_file_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(entrada, 'REQUISITOS', Path(tmp) / 'nao-existe.txt'), \
                redirect_stdout(io.StringIO()) as saida:
            self.assertEqual(entrada.instalar_requisitos(), 1)
        self.assertIn('Extraia o ZIP inteiro', saida.getvalue())

    def test_default_run_opens_the_configurator_only_when_config_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            ausente = Path(tmp) / 'config.json'
            comandos = []

            def falso_executar(args):
                comandos.append([str(a) for a in args])
                ausente.write_text('{}', encoding='utf-8')
                return 0

            with patch.object(entrada, 'pronto_para_usar', return_value=True), \
                    patch.object(entrada, 'CONFIG', ausente), \
                    patch.object(entrada, 'iniciar', return_value=0), \
                    patch.object(entrada, 'executar', side_effect=falso_executar), \
                    redirect_stdout(io.StringIO()):
                self.assertEqual(entrada.abrir(), 0)
            self.assertTrue(any('configurar' in c for c in comandos))

            comandos.clear()
            with patch.object(entrada, 'pronto_para_usar', return_value=True), \
                    patch.object(entrada, 'CONFIG', ausente), \
                    patch.object(entrada, 'iniciar', return_value=0), \
                    patch.object(entrada, 'executar', side_effect=falso_executar), \
                    redirect_stdout(io.StringIO()):
                self.assertEqual(entrada.abrir(), 0)
            self.assertEqual(comandos, [], 'com config.json presente não deve reconfigurar')

    def test_pyinstaller_bundles_web_from_inside_the_package(self):
        capturado = {}

        def falso_executar(args):
            capturado.setdefault('args', [str(a) for a in args])
            return 0

        with patch.object(entrada, 'pronto_para_usar', return_value=True), \
                patch.object(entrada, 'executar', side_effect=falso_executar), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(entrada.gerar_exe(), 0)
        separador = ';' if os.name == 'nt' else ':'
        esperado = f'{os.path.join("jarvis", "web")}{separador}web'
        todos = capturado['args']
        with patch.object(entrada, 'pronto_para_usar', return_value=True), \
                patch.object(entrada, 'executar', side_effect=lambda a: todos.extend(str(x) for x in a) or 0), \
                redirect_stdout(io.StringIO()):
            entrada.gerar_exe()
        self.assertIn(esperado, todos)
        self.assertIn(os.path.join('jarvis', '__main__.py'), todos)

    def test_commands_pass_arguments_as_a_list_so_spaces_and_accents_survive(self):
        """Caminhos como "C:\\Users\\Ana\\Área de Trabalho\\Jarvis AGV" não são reinterpretados."""
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp) / 'Área de Trabalho' / 'Jarvis AGV'
            pasta.mkdir(parents=True)
            recebido = {}

            def falso_run(args, cwd=None, **kwargs):
                recebido['args'] = args
                recebido['cwd'] = cwd
                return type('R', (), {'returncode': 0})()

            with patch.object(entrada, 'RAIZ', pasta), patch('subprocess.run', falso_run):
                self.assertEqual(entrada.executar([pasta / 'python', '-m', 'jarvis']), 0)
        self.assertIsInstance(recebido['args'], list)
        self.assertTrue(all(isinstance(a, str) for a in recebido['args']))
        self.assertIn('Área de Trabalho', recebido['args'][0])
        self.assertNotIn('"', recebido['args'][0])
        self.assertEqual(recebido['cwd'], str(pasta))

    def test_python_version_check_points_to_the_download_page(self):
        with patch.object(sys, 'version_info', (3, 8, 0)), redirect_stdout(io.StringIO()) as saida:
            self.assertFalse(entrada.checar_python())
        self.assertIn('python.org/downloads', saida.getvalue())
        with patch.object(sys, 'version_info', (3, 12, 0)), redirect_stdout(io.StringIO()):
            self.assertTrue(entrada.checar_python())


if __name__ == '__main__':
    unittest.main()
