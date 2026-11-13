"""Máquina de estados da conversa (não depende do Telegram).

AGUARDANDO_FOTO -> (foto) -> [LOCAL] -> TIPO -> TAMANHO -> MATERIAL -> salva

Cada função devolve uma lista de Reply; quem de fato envia é o bot (app/bot.py).
Isso facilita testar e trocar de canal (Telegram, WhatsApp...) no futuro.
"""
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from . import drive, extractor, sheets, state

TIPOS = ["Sinal horizontal (chão)", "Sinal vertical (placa)", "Outro"]
TZ = ZoneInfo("America/Sao_Paulo")


@dataclass
class Reply:
    text: str
    buttons: list[str] | None = None  # vira teclado de botões no Telegram


def _pergunta_tipo() -> Reply:
    return Reply("Qual o tipo de sinalização?", TIPOS)


def _texto_local(loc: dict) -> str:
    partes = [p for p in (loc.get("rua"), loc.get("bairro")) if p]
    if loc.get("latitude") is not None and loc.get("longitude") is not None:
        partes.append(f"({loc['latitude']}, {loc['longitude']})")
    return " - ".join(partes) or "?"


def _resumo(d: dict) -> str:
    return (
        f"Tipo: {d.get('tipo_sinal')}\n"
        f"Rua: {d.get('rua') or '-'} | Bairro: {d.get('bairro') or '-'}\n"
        f"Tamanho: {d.get('tamanho_m2')} m²\n"
        f"Material: {d.get('material')}"
    )


def cancelar(user_id: int) -> list[Reply]:
    state.reset(str(user_id))
    return [Reply("Registro cancelado. Envie uma nova foto quando quiser.")]


def receber_foto(user_id: int, nome: str, conteudo: bytes, mime: str) -> list[Reply]:
    uid = str(user_id)
    loc = extractor.extrair_localizacao(conteudo, mime)

    ext = {"image/png": "png", "image/webp": "webp", "image/gif": "gif"}.get(mime, "jpg")
    arquivo = f"{datetime.now(TZ):%Y%m%d_%H%M%S}_{uid}.{ext}"
    link = drive.upload_foto(conteudo, arquivo, mime)

    data = {
        "rua": loc["rua"], "bairro": loc["bairro"], "cidade": loc["cidade"],
        "latitude": loc["latitude"], "longitude": loc["longitude"],
        "confianca_extracao": loc["confianca"], "link_foto": link,
        "usuario": f"{nome} ({uid})",
    }

    if not loc["rua"] and loc["latitude"] is None:
        state.save(uid, "LOCAL", data)
        return [Reply("Não consegui ler a localização na foto. Digite no formato: Rua X, Bairro Y")]

    state.save(uid, "TIPO", data)
    return [Reply(f"📍 Local lido: {_texto_local(loc)}"), _pergunta_tipo()]


def receber_texto(user_id: int, texto: str) -> list[Reply]:
    uid = str(user_id)
    texto = texto.strip()
    s = state.get(uid)
    step, data = s["step"], s["data"]

    if step == "AGUARDANDO_FOTO":
        return [Reply("Envie a foto do serviço com a localização na imagem para começar.")]

    if step == "LOCAL":
        rua, _, bairro = texto.partition(",")
        data.update(rua=rua.strip(), bairro=bairro.strip())
        state.save(uid, "TIPO", data)
        return [_pergunta_tipo()]

    if step == "TIPO":
        if texto not in TIPOS:
            return [_pergunta_tipo()]
        data["tipo_sinal"] = texto
        state.save(uid, "TAMANHO", data)
        return [Reply("Qual o tamanho em m²? (ex: 12,5)")]

    if step == "TAMANHO":
        try:
            data["tamanho_m2"] = float(texto.replace(",", "."))
        except ValueError:
            return [Reply("Não entendi. Envie só o número em m², ex: 12,5")]
        state.save(uid, "MATERIAL", data)
        return [Reply("Qual o material utilizado? (ex: tinta acrílica, termoplástico, placa ACM)")]

    if step == "MATERIAL":
        data["material"] = texto
        data["registrado_em"] = datetime.now(TZ).strftime("%d/%m/%Y %H:%M:%S")
        sheets.adicionar_registro(data)
        state.reset(uid)
        return [Reply(f"✅ Registro salvo!\n\n{_resumo(data)}\n\nPode enviar a próxima foto.")]

    state.reset(uid)
    return [Reply("Algo saiu do fluxo, vamos recomeçar. Envie a foto do serviço.")]
