"""Assistente local de configuração. Nunca envia ou imprime a chave privada."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

from .settings import DATA
from .sheets import LAYOUT_TABS, SCHOOL_SHEET_ID, SCHOOL_TABS, MAX_WORKBOOK_BYTES, SheetsError, load_account, read_workbook, snapshot, spreadsheet_id


def save_configuration(link, source, tabs=None, layout='relacional'):
    sid = spreadsheet_id(link)
    if layout not in LAYOUT_TABS:
        raise SheetsError('Escolha o formato Horarios ou relacional.', 'sheets_config')
    source = Path(source).expanduser().resolve()
    account = load_account(source)
    secrets = DATA / 'segredos'
    secrets.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = secrets / 'conta-google.json'
    config = DATA / 'config.json'
    # Mantém uma cópia local para recuperar uma configuração anterior.
    if target.exists() and source != target.resolve():
        shutil.copy2(target, secrets / 'conta-google.anterior.json')
    if config.exists():
        shutil.copy2(config, DATA / 'config.anterior.json')
    payload = {'google_sheets': {'spreadsheet_id': sid, 'credentials_file': 'segredos/conta-google.json', 'cache_seconds': 60, 'layout': layout, 'tabs': tabs or LAYOUT_TABS[layout]}}
    for path, content in ((target, json.dumps(account, ensure_ascii=False, indent=2)), (config, json.dumps(payload, ensure_ascii=False, indent=2))):
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
                temporary = stream.name
                stream.write(content + '\n')
            os.replace(temporary, path)
            if os.name != 'nt':
                path.chmod(0o600)
        finally:
            if temporary and Path(temporary).exists():
                Path(temporary).unlink()
    return account['client_email']


def _save_files(payload, extra=()):
    config = DATA / 'config.json'
    if config.exists():
        shutil.copy2(config, DATA / 'config.anterior.json')
    for path, content in (*extra, (config, (json.dumps(payload, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))):
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='wb', dir=path.parent, delete=False) as stream:
                temporary = stream.name
                stream.write(content)
            os.replace(temporary, path)
            if os.name != 'nt':
                path.chmod(0o600)
        finally:
            if temporary and Path(temporary).exists():
                Path(temporary).unlink()


def save_public_configuration(link, tabs=None, layout='horarios'):
    if layout not in LAYOUT_TABS:
        raise SheetsError('Formato inválido.', 'sheets_config')
    selected = tabs or (SCHOOL_TABS if layout == 'horarios' else LAYOUT_TABS[layout])
    _save_files({'google_sheets': {'mode': 'public', 'spreadsheet_id': spreadsheet_id(link),
                                 'layout': layout, 'tabs': selected, 'cache_seconds': 60}})


def save_file_configuration(source, tabs=None, layout='horarios'):
    if layout not in LAYOUT_TABS:
        raise SheetsError('Formato inválido.', 'sheets_config')
    selected = tabs or (SCHOOL_TABS if layout == 'horarios' else LAYOUT_TABS[layout])
    source = Path(source).expanduser().resolve()
    with source.open('rb') as stream:
        content = stream.read(MAX_WORKBOOK_BYTES + 1)
    read_workbook(content, selected)
    target = DATA / 'dados' / 'grade.xlsx'
    if target.exists() and source != target.resolve():
        shutil.copy2(target, target.with_name('grade.anterior.xlsx'))
    _save_files({'google_sheets': {'mode': 'file', 'workbook_file': 'dados/grade.xlsx',
                                 'layout': layout, 'tabs': selected, 'cache_seconds': 60}},
                ((target, content),))


def choose_file(extension='json'):
    label = 'Excel (.xlsx)' if extension == 'xlsx' else 'JSON da conta Google'
    text = input(f'Caminho do arquivo {label} (ou Enter para escolher o arquivo): ').strip().strip('"')
    if text:
        return text
    try:
        from tkinter import Tk, filedialog, TclError
    except ImportError:
        return input(f'Cole o caminho completo do arquivo {label}: ').strip().strip('"')
    try:
        window = Tk()
        window.withdraw()
        try:
            return filedialog.askopenfilename(title='Selecione o arquivo ' + label, filetypes=[(label, '*.' + extension)])
        finally:
            window.destroy()
    except (TclError, RuntimeError):
        return input(f'Cole o caminho completo do arquivo {label}: ').strip().strip('"')


def main():
    print('JARVIS AGV - Conectar Google Planilhas\n')
    print('A planilha deve estar salva no formato Google Planilhas, com cabeçalhos na linha 1.')
    print('Este programa só lê os dados e não altera o compartilhamento.\n')
    print('1 - Pelo link: sem Cloud, cartão ou JSON; exige leitura e download liberados pelo link.')
    print('    Qualquer pessoa com esse link também poderá ler os dados.')
    print('2 - Arquivo Excel local: sem Cloud e sem liberar a planilha; atualização manual.')
    print('3 - Conta de serviço: mantém a conexão privada; usa o JSON Google da versão anterior.')
    mode = input('Modo de acesso [1]: ').strip() or '1'
    if mode not in ('1', '2', '3'):
        raise SheetsError('Escolha o modo 1, 2 ou 3.', 'sheets_config')
    link, source = '', None
    if mode != '2':
        print('\nPlanilha sugerida: Banco de dados Jarvis')
        print('https://docs.google.com/spreadsheets/d/' + SCHOOL_SHEET_ID + '/edit')
        link = input('Cole o link da planilha ou pressione Enter para usar essa: ').strip() or SCHOOL_SHEET_ID
        spreadsheet_id(link)
    if mode == '2':
        print('\nNo Google Planilhas: Arquivo > Fazer download > Microsoft Excel (.xlsx).')
        print('Selecione esse arquivo. Ele contém todas as abas; não use CSV.')
        source = choose_file('xlsx')
    elif mode == '3':
        source = choose_file()
    if mode != '1' and not source:
        print('Nenhum arquivo selecionado. Configuração cancelada.')
        return 1
    print('\n1 - Sua estrutura: Horário DS1, Disciplinas, Turmas, Professores (padrão)')
    print('2 - Modelo antigo: cinco abas agv_* com IDs')
    choice = input('Formato [1]: ').strip() or '1'
    if choice not in ('1', '2'):
        raise SheetsError('Formato inválido. Execute novamente e escolha 1 ou 2.', 'sheets_config')
    layout = 'horarios' if choice == '1' else 'relacional'
    tabs = dict(SCHOOL_TABS if layout == 'horarios' else LAYOUT_TABS[layout])
    print('\nAbas esperadas:', ', '.join(tabs.values()))
    if input('Se os nomes forem diferentes, digite N. Caso contrário, Enter: ').strip().lower() == 'n':
        for name, default in list(tabs.items()):
            tabs[name] = input(f'Nome da aba de {name} [{default}]: ').strip() or default
    if mode == '1':
        save_public_configuration(link, tabs, layout)
        print('\nConfiguração salva. Testando a leitura pelo link, sem login ou JSON...')
        print('Não é necessário abrir Google Cloud. O compartilhamento não foi alterado.')
    elif mode == '2':
        save_file_configuration(source, tabs, layout)
        print('\nCópia salva em dados/grade.xlsx. Testando o arquivo local...')
        print('Quando editar no Google, baixe outro XLSX e selecione-o novamente no modo 2.')
    else:
        email = save_configuration(link, source, tabs, layout)
        print('\nConfiguração salva. No Google Planilhas, clique em Compartilhar.')
        print('Adicione este e-mail como LEITOR:')
        print(email)
        print('Mantenha o acesso geral RESTRITO. Não use Publicar na Web.')
        input('\nDepois de compartilhar, pressione Enter para testar a conexão...')
    data = snapshot(force=True)
    print('\nLeitura confirmada. Aulas ativas:', data['counts']['aulas'])
    for warning in data.get('warnings', []):
        print('AVISO:', warning)
    if not data['counts']['aulas']:
        print('A estrutura está correta, mas ainda não há aulas ativas cadastradas.')
    print('Agora execute Jarvis.py, opção 5 (Iniciar). Se o Jarvis já estava aberto, reinicie-o.')
    return 0


def run():
    """Executa o assistente tratando os erros esperados. Devolve o código de saída."""
    try:
        return main()
    except SheetsError as exc:
        print(f'\nNão foi possível concluir [{exc.code}]: {exc}')
        print('Corrija a configuração e execute Jarvis.py, opção 3 (Testar planilha). Consulte docs/GUIA-GOOGLE-PLANILHAS.html.')
    except (OSError, UnicodeError):
        print('\nNão foi possível salvar os arquivos. Confira o caminho e a permissão da pasta.')
    except (KeyboardInterrupt, EOFError):
        print('\nConfiguração interrompida.')
    return 1


if __name__ == '__main__':
    sys.exit(run())
