import gspread

from . import config
from .colunas import COLUNAS
from .google_auth import get_credentials
from .seguranca import neutralizar_formula

def adicionar_registro(reg: dict):
    ws = gspread.authorize(get_credentials()).open_by_key(config.SHEET_ID).worksheet(config.SHEET_TAB)
    if not ws.row_values(1):
        ws.append_row(COLUNAS)
    linha = []
    for coluna in COLUNAS:
        valor = reg.get(coluna)
        linha.append(neutralizar_formula("" if valor is None else valor))
    ws.append_row(linha, value_input_option="USER_ENTERED")
