"""Ponto de entrada único (python -m jarvis) e fonte única de configuração."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from jarvis import __main__ as cli
from jarvis import app, settings


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        out = io.StringIO()
        with redirect_stdout(out):
            code = cli.main(list(args))
        return code, out.getvalue()

    def test_help_lists_every_command(self):
        code, text = self.run_cli('--help')
        self.assertEqual(code, 0)
        for name in ('servir', 'configurar', 'testar-planilha', 'testar-voz'):
            self.assertIn(name, text)

    def test_unknown_command_fails_with_usage(self):
        code, text = self.run_cli('inexistente')
        self.assertEqual(code, 2)
        self.assertIn('Comando desconhecido', text)

    def test_default_command_starts_server(self):
        with patch.object(app, 'main', return_value=0) as serve:
            self.assertEqual(cli.main([]), 0)
        serve.assert_called_once()

    def test_server_exit_code_reaches_the_caller(self):
        """Porta ocupada, por exemplo, precisa virar código de saída 1."""
        with patch.object(app, 'main', return_value=1):
            self.assertEqual(cli.main(['servir']), 1)
        with patch.object(app, 'main', return_value=None):
            self.assertEqual(cli.main(['servir']), 0)

    def test_palma_command_runs_the_listener(self):
        from jarvis import palma
        with patch.object(palma, 'main', return_value=3) as escutar:
            self.assertEqual(cli.main(['palma']), 3)
        escutar.assert_called_once()

    def test_network_flag_sets_environment(self):
        with patch.dict(os.environ, {}, clear=False), patch.object(app, 'main', return_value=0):
            os.environ.pop('JARVIS_REDE', None)
            cli.main(['servir', '--rede'])
            self.assertEqual(os.environ.get('JARVIS_REDE'), '1')

    def test_subcommands_return_their_exit_code(self):
        from jarvis import configurar_planilha, testar_planilha, testar_voz
        for module, attr, command in ((configurar_planilha, 'run', 'configurar'), (testar_planilha, 'main', 'testar-planilha'), (testar_voz, 'main', 'testar-voz')):
            with patch.object(module, attr, return_value=7):
                self.assertEqual(cli.main([command]), 7, command)


class SettingsTests(unittest.TestCase):
    def test_project_folders_and_single_model_definition(self):
        self.assertTrue((settings.ROOT / 'web' / 'index.html').is_file())
        self.assertEqual(settings.WEB, settings.ROOT / 'web')
        self.assertIs(app.MODEL, settings.MODEL)
        self.assertEqual(settings.DATA, settings.ROOT)  # fora do executável
        # web/, docs/ e tests/ moraram para dentro do pacote jarvis/.
        self.assertEqual(settings.PACOTE.name, 'jarvis')
        self.assertTrue(settings.REQUIREMENTS.is_file())
        self.assertTrue((settings.PACOTE / 'docs').is_dir())
        # Na raiz fica só o arquivo de entrada (mais o leia-me e o .gitignore).
        raiz = settings.PACOTE.parent
        self.assertEqual(sorted(p.name for p in raiz.iterdir() if p.is_file()),
                         ['.gitignore', 'Jarvis.py', 'LEIA-PRIMEIRO.txt'])


if __name__ == '__main__':
    unittest.main()
