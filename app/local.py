"""Armazenamento local: fotos em dados/fotos/ e registros em dados/registros.csv (append)."""
import csv
import threading
from pathlib import Path

from . import config
from .colunas import COLUNAS
from .seguranca import neutralizar_formula
from datetime import datetime

_lock = threading.Lock()  # os handlers rodam em threads: evita duas gravações ao mesmo tempo


def _pasta_dados() -> Path:
    pasta = Path(config.DADOS_DIR)
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def _pasta_fotos() -> Path:
    pasta = _pasta_dados() / "fotos"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def salvar_foto(conteudo: bytes, nome: str, mime: str) -> dict:
    """Grava a foto em dados/fotos/ e devolve {'id': nome do arquivo, 'link': caminho relativo}."""
    nome = Path(nome).name  # nunca aceita subpastas
    (_pasta_fotos() / nome).write_bytes(conteudo)
    return {"id": nome, "link": f"fotos/{nome}"}


def apagar_foto(foto_id: str):
    """Apaga uma foto de registro descartado."""
    (_pasta_fotos() / Path(foto_id).name).unlink(missing_ok=True)


def _formatar(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float):  # números: vírgula decimal para o Excel em português abrir certo
        return str(valor).replace(".", config.CSV_DECIMAL)
    if isinstance(valor, str):
        return neutralizar_formula(valor)  # CSV aberto no Excel também executa fórmulas
    return str(valor)


def _cabecalho_atual(caminho: Path) -> list[str]:
    with open(caminho, newline="", encoding="utf-8-sig") as f:
        return next(csv.reader(f, delimiter=config.CSV_DELIMITADOR), [])


def adicionar_registro(reg: dict):
    linha = [_formatar(reg.get(coluna)) for coluna in COLUNAS]
    caminho = _pasta_dados() / "registros.csv"
    with _lock:
        if caminho.exists() and caminho.stat().st_size > 0 and _cabecalho_atual(caminho) != COLUNAS:
            caminho.rename(caminho.with_name(f"registros_antigo_{datetime.now():%Y%m%d_%H%M%S}.csv"))
        novo = not caminho.exists() or caminho.stat().st_size == 0
        with open(caminho, "w" if novo else "a", newline="",
                  encoding="utf-8-sig" if novo else "utf-8") as f:
            escritor = csv.writer(f, delimiter=config.CSV_DELIMITADOR)
            if novo:
                escritor.writerow(COLUNAS)
            escritor.writerow(linha)
