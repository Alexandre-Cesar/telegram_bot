"""Validações e limpeza de tudo que vem de fora (foto, texto digitado, texto lido pelo modelo).

Só usa a biblioteca padrão (sem Pillow) para não depender de arquivos compilados.
"""
import math
import re


def detectar_mime(conteudo: bytes) -> str | None:
    """Descobre o tipo real pelos primeiros bytes, ignorando o que o cliente declarou."""
    if conteudo[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if conteudo[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if conteudo[:4] == b"RIFF" and conteudo[8:12] == b"WEBP":
        return "image/webp"
    return None


def limpar_texto(valor, limite: int = 120) -> str | None:
    """Remove caracteres de controle, normaliza espaços e limita o tamanho."""
    if valor is None:
        return None
    texto = re.sub(r"[\x00-\x1f\x7f]", " ", str(valor))
    texto = " ".join(texto.split())
    return texto[:limite] or None


def coordenada(valor, minimo: float, maximo: float) -> float | None:
    """Converte para número e descarta o que estiver fora da faixa válida."""
    if isinstance(valor, str):
        valor = valor.replace(",", ".")
    try:
        n = float(valor)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(n) or not (minimo <= n <= maximo):
        return None
    return n


_PERIGOSO = re.compile(r"^[=+\-@\t\r\n]")


def neutralizar_formula(valor):
    """Evita injeção de fórmula na planilha: texto que começa com = + - @ vira texto puro.

    Números (como a latitude -15.8, que é float) passam intactos.
    """
    if isinstance(valor, str) and _PERIGOSO.match(valor.lstrip(" ")):
        return "'" + valor
    return valor
