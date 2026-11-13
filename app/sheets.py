import gspread

from . import config
from .google_auth import get_credentials

COLUNAS = [
    "registrado_em", "usuario", "tipo_sinal", "rua", "bairro", "cidade",
    "latitude", "longitude", "tamanho_m2", "material", "link_foto", "confianca_extracao",
]


def adicionar_registro(reg: dict):
    ws = gspread.authorize(get_credentials()).open_by_key(config.SHEET_ID).worksheet(config.SHEET_TAB)
    if not ws.row_values(1):
        ws.append_row(COLUNAS)
    ws.append_row([reg.get(c, "") for c in COLUNAS], value_input_option="USER_ENTERED")
