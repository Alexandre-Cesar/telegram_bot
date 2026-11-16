"""Máquina de estados da conversa (não depende do Telegram).

AGUARDANDO_FOTO -> (foto) -> ROTULO -> FOTO_EXTRA -> [LOCAL] -> TIPO -> TAMANHO
                -> MATERIAL -> CONFIRMA -> salva

Um registro = uma placa, com até duas fotos (antes e depois), ambas opcionais mas
com pelo menos uma. Cada função devolve uma lista de Reply; quem de fato envia é o
bot (app/bot.py).
"""
import math
import uuid
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from . import armazenamento, config, extractor, seguranca, state

TIPOS = ["Sinal horizontal (chão)", "Sinal vertical (placa)", "Outro"]
ROTULOS = {"Antes": "antes", "Depois": "depois"}  # texto do botão -> chave interna
PULAR = "Pular"
CONFIRMAR = "✅ Confirmar"
DESCARTAR = "❌ Descartar"
TZ = ZoneInfo("America/Sao_Paulo")
_CONFIANCA = {"baixa": 0, "media": 1, "alta": 2}


@dataclass
class Reply:
    text: str
    buttons: list[str] | None = None  # vira teclado de botões no Telegram


# ---------- mensagens ----------
def _pergunta_tipo() -> Reply:
    return Reply("Qual o tipo de sinalização?", TIPOS)


def _pergunta_rotulo() -> Reply:
    return Reply("Essa foto é do antes ou do depois?", list(ROTULOS))


def _texto_local(rua, bairro, lat, lon) -> str:
    partes = [p for p in (rua, bairro) if p]
    if lat is not None and lon is not None:
        partes.append(f"({lat}, {lon})")
    return " - ".join(partes) or "?"


def _descricao_fotos(fotos: dict) -> str:
    if "antes" in fotos and "depois" in fotos:
        return "antes e depois"
    return "só depois" if "depois" in fotos else "só antes"


def _resumo(d: dict) -> str:
    return (
        f"Tipo: {d.get('tipo_sinal')}\n"
        f"Rua: {d.get('rua') or '-'} | Bairro: {d.get('bairro') or '-'}\n"
        f"Tamanho: {d.get('tamanho_m2')} m²\n"
        f"Material: {d.get('material')}\n"
        f"Fotos: {_descricao_fotos(d.get('fotos_enviadas', {}))}"
    )


def _pergunta_confirma(d: dict) -> list[Reply]:
    return [Reply(f"Confira o registro:\n\n{_resumo(d)}", [CONFIRMAR, DESCARTAR])]


# ---------- dados ----------
def _registro_final(data: dict) -> dict:
    """Monta a linha que vai para o CSV/planilha a partir do estado da conversa."""
    fotos = data.get("fotos_enviadas", {})
    reg = dict(data)
    reg["fotos"] = _descricao_fotos(fotos)
    reg["link_foto_antes"] = fotos.get("antes", {}).get("link", "")
    reg["link_foto_depois"] = fotos.get("depois", {}).get("link", "")
    return reg


def _mesclar_local(data: dict, loc: dict):
    """Junta a localização lida numa foto ao que já se sabe (a 1ª foto não precisa ter tudo)."""
    lat = seguranca.coordenada(loc.get("latitude"), -90, 90)
    lon = seguranca.coordenada(loc.get("longitude"), -180, 180)
    if lat is None or lon is None:
        lat = lon = None
    for campo in ("rua", "bairro", "cidade"):
        valor = seguranca.limpar_texto(loc.get(campo))
        if valor and not data.get(campo):
            data[campo] = valor
    if lat is not None and data.get("latitude") is None:
        data["latitude"], data["longitude"] = lat, lon
    conf = loc.get("confianca") if loc.get("confianca") in _CONFIANCA else "baixa"
    atual = data.get("confianca_extracao", "baixa")
    data["confianca_extracao"] = max(atual, conf, key=_CONFIANCA.get)


def _descartar_fotos(data: dict):
    """Apaga (local ou Drive) todas as fotos de um registro que não foi concluído."""
    fotos = list(data.get("fotos_enviadas", {}).values())
    if data.get("pendente"):
        fotos.append(data["pendente"])
    for foto in fotos:
        try:
            armazenamento.apagar_foto(foto["id"])
        except Exception as e:  # noqa: BLE001
            print("não consegui apagar a foto:", repr(e))


def _depois_das_fotos(uid: str, data: dict) -> list[Reply]:
    """Fim da etapa de fotos: segue para o tipo, ou pede o endereço se nada foi lido."""
    if not data.get("rua") and data.get("latitude") is None:
        state.save(uid, "LOCAL", data)
        return [Reply("Não consegui ler a localização nas fotos. Digite no formato: Rua X, Bairro Y")]
    state.save(uid, "TIPO", data)
    local = _texto_local(data.get("rua"), data.get("bairro"), data.get("latitude"), data.get("longitude"))
    return [Reply(f"📍 Local lido: {local}"), _pergunta_tipo()]


# ---------- entradas ----------
def cancelar(user_id: int) -> list[Reply]:
    uid = str(user_id)
    _descartar_fotos(state.get(uid)["data"])
    state.reset(uid)
    return [Reply("Registro cancelado. Envie uma nova foto quando quiser.")]


def receber_foto(user_id: int, nome: str, conteudo: bytes) -> list[Reply]:
    uid = str(user_id)
    s = state.get(uid)
    step, data = s["step"], s["data"]

    # foto fora de hora: não apaga nada, só orienta
    if step == "ROTULO":
        return [Reply("Antes de enviar outra foto, me diga: a foto anterior é do antes ou do depois?",
                      list(ROTULOS))]
    if step not in ("AGUARDANDO_FOTO", "FOTO_EXTRA"):
        return [Reply("Você tem um registro em andamento. Conclua, ou envie /cancelar para recomeçar.")]

    if len(conteudo) > config.MAX_FOTO_MB * 1024 * 1024:
        return [Reply(f"Arquivo muito grande (máximo {config.MAX_FOTO_MB} MB).")]
    mime = seguranca.detectar_mime(conteudo)  # tipo real, não o declarado pelo cliente
    if mime is None:
        return [Reply("Formato não suportado. Envie uma foto em JPG, PNG ou WEBP.")]

    loc = extractor.extrair_localizacao(conteudo, mime)
    ext = {"image/png": "png", "image/webp": "webp"}.get(mime, "jpg")
    arquivo = f"{datetime.now(TZ):%Y%m%d_%H%M%S}_{uid}_{uuid.uuid4().hex[:6]}.{ext}"
    foto = armazenamento.salvar_foto(conteudo, arquivo, mime)

    if step == "AGUARDANDO_FOTO":  # primeira foto: novo registro, falta saber se é antes ou depois
        data = {"fotos_enviadas": {}, "pendente": foto,
                "usuario": seguranca.limpar_texto(f"{nome} ({uid})")}
        _mesclar_local(data, loc)
        state.save(uid, "ROTULO", data)
        return [_pergunta_rotulo()]

    # FOTO_EXTRA: esta é a foto que faltava (o rótulo é o oposto da primeira)
    data["fotos_enviadas"][data.pop("faltando")] = foto
    _mesclar_local(data, loc)
    return _depois_das_fotos(uid, data)


def receber_texto(user_id: int, texto: str) -> list[Reply]:
    uid = str(user_id)
    texto = texto.strip()
    s = state.get(uid)
    step, data = s["step"], s["data"]

    if step == "AGUARDANDO_FOTO":
        return [Reply("Envie a foto do serviço (antes ou depois) com a localização na imagem para começar.")]

    if step == "ROTULO":
        rotulo = ROTULOS.get(texto)
        if not rotulo:
            return [_pergunta_rotulo()]
        data["fotos_enviadas"][rotulo] = data.pop("pendente")
        data["faltando"] = "depois" if rotulo == "antes" else "antes"
        state.save(uid, "FOTO_EXTRA", data)
        return [Reply(f"Tem a foto do {data['faltando']}? Envie agora ou toque em Pular.", [PULAR])]

    if step == "FOTO_EXTRA":
        if texto == PULAR:
            data.pop("faltando", None)
            return _depois_das_fotos(uid, data)
        return [Reply(f"Envie a foto do {data['faltando']} ou toque em Pular.", [PULAR])]

    if step == "LOCAL":
        rua, _, bairro = texto.partition(",")
        rua, bairro = seguranca.limpar_texto(rua), seguranca.limpar_texto(bairro)
        if not rua:
            return [Reply("Não entendi. Digite no formato: Rua X, Bairro Y")]
        data.update(rua=rua, bairro=bairro)
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
            valor = float(texto.replace(",", "."))
        except ValueError:
            valor = None
        if valor is None or not math.isfinite(valor) or not (0 < valor <= 100000):
            return [Reply("Não entendi. Envie só o número em m², ex: 12,5")]
        data["tamanho_m2"] = round(valor, 2)
        state.save(uid, "MATERIAL", data)
        return [Reply("Qual o material utilizado? (ex: tinta acrílica, termoplástico, placa ACM)")]

    if step == "MATERIAL":
        material = seguranca.limpar_texto(texto, 80)
        if not material:
            return [Reply("Não entendi. Digite o material utilizado.")]
        data["material"] = material
        state.save(uid, "CONFIRMA", data)
        return _pergunta_confirma(data)

    if step == "CONFIRMA":
        if texto == CONFIRMAR:
            data["registrado_em"] = datetime.now(TZ).strftime("%d/%m/%Y %H:%M:%S")
            try:
                armazenamento.adicionar_registro(_registro_final(data))
            except PermissionError:  # no Windows, o Excel trava o CSV enquanto está aberto
                return [Reply(
                    "Não consegui gravar no arquivo. Se o CSV estiver aberto no Excel, feche-o "
                    "e toque em Confirmar de novo.", [CONFIRMAR, DESCARTAR])]
            state.reset(uid)
            return [Reply("✅ Registro salvo! Pode enviar a próxima foto.")]
        if texto == DESCARTAR:
            return cancelar(user_id)
        return _pergunta_confirma(data)

    state.reset(uid)
    return [Reply("Algo saiu do fluxo, vamos recomeçar. Envie a foto do serviço.")]
