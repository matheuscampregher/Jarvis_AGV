"""Ponto de entrada único: python -m jarvis [comando].

Sem comando, inicia o servidor. Usado pelo Jarvis.py e pelo executável.
Os imports ficam dentro de cada comando para carregar só o necessário e usam
o nome absoluto `jarvis`, que funciona também como script do PyInstaller.
"""
import os
import sys

USO = """Uso: python -m jarvis [comando]

Comandos:
  servir             Inicia o Jarvis (padrão). Com --rede, aceita outros computadores da rede.
  configurar         Assistente de configuração da planilha.
  testar-planilha    Diagnóstico da leitura e dos relacionamentos da planilha.
  testar-voz         Gera teste-voz.mp3 com a voz natural.
  palma              Escuta o microfone e abre o Jarvis ao bater duas palmas.
  palma --calibrar   Mede o microfone e sugere o limiar das palmas.
"""


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    command = args.pop(0) if args else 'servir'

    if command in ('-h', '--help', 'ajuda'):
        print(USO)
        return 0
    if command == 'servir':
        if '--rede' in args:
            os.environ['JARVIS_REDE'] = '1'
        from jarvis import app
        return app.main() or 0
    if command == 'configurar':
        from jarvis import configurar_planilha
        return configurar_planilha.run()
    if command == 'testar-planilha':
        from jarvis import testar_planilha
        return testar_planilha.main()
    if command == 'testar-voz':
        from jarvis import testar_voz
        return testar_voz.main()
    if command == 'palma':
        from jarvis import palma
        return palma.main(args)

    print(f'Comando desconhecido: {command}\n')
    print(USO)
    return 2


if __name__ == '__main__':
    sys.exit(main())
