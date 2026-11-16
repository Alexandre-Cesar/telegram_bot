"""Escolhe onde salvar, conforme ARMAZENAMENTO no .env: 'local' (padrão) ou 'google'.

Os módulos do Google só são importados no modo 'google', então no modo 'local'
nenhuma biblioteca do Google é carregada.
"""
from . import config


def salvar_foto(conteudo: bytes, nome: str, mime: str) -> dict:
    """Devolve {'id': ..., 'link': ...}."""
    if config.ARMAZENAMENTO == "google":
        from . import drive
        return drive.upload_foto(conteudo, nome, mime)
    from . import local
    return local.salvar_foto(conteudo, nome, mime)


def apagar_foto(foto_id: str):
    if config.ARMAZENAMENTO == "google":
        from . import drive
        return drive.apagar(foto_id)
    from . import local
    return local.apagar_foto(foto_id)


def adicionar_registro(reg: dict):
    if config.ARMAZENAMENTO == "google":
        from . import sheets
        return sheets.adicionar_registro(reg)
    from . import local
    return local.adicionar_registro(reg)
