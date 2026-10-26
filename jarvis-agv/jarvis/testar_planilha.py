"""Diagnóstico de leitura e relacionamentos, executado somente no servidor."""
import sys
from .sheets import SheetsError, snapshot


def main():
    print('JARVIS AGV - Teste de Google Planilhas\n')
    try:
        data = snapshot(force=True)
    except SheetsError as exc:
        print(f'ERRO [{exc.code}]: {exc}')
        print('Abra docs/GUIA-GOOGLE-PLANILHAS.html para conferir a configuração.')
        return 1
    print('Conexão e relacionamentos verificados.')
    for key, value in data['counts'].items():
        print(f'{key}: {value}')
    for warning in data.get('warnings', []):
        print('AVISO:', warning)
    print('\nPrimeiras aulas ativas:')
    days = ('segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo')
    for row in data['rows'][:3]:
        print(f"{days[row['dia']]} {row['inicio']}–{row['fim']}: {row['professor']} / {row['materia']} / turma {row['turma']} / {row['sala']}")
    if not data['rows']:
        print('Nenhuma aula ativa. Cadastre linhas na aba de aulas ou marque ativo como verdadeiro.')
    print('\nExecute Jarvis.py, opção 5 (Iniciar), e pergunte: quais aulas da turma 1 DS segunda das 7:30 às 8:20?')
    return 0


if __name__ == '__main__':
    sys.exit(main())
