"""Máquina de estados da conversa (não depende do Telegram).

Fluxo de cadastro de serviço:
AGUARDANDO_FOTO -> (foto) -> ROTULO -> FOTO_EXTRA -> [LOCAL] -> TIPO
                -> [ACAO -> CATEGORIA -> [MODELO]]  (só se o sinal for vertical)
                -> [TAMANHO] -> [MATERIAL] -> CONFIRMA -> salva no registros.csv

Fluxo de envio do relatório diário (/relatorio ou botão):
AGUARDANDO_FOTO -> REL_VEICULO -> REL_AJUDANTES -> REL_CONFIRMA -> salva em relatorios.csv e envia
"""
import math
import uuid
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from . import armazenamento, catalogo, config, extractor, relatorio, seguranca, state

TIPO_VERTICAL = "Sinal vertical (placa)"
TIPOS = ["Sinal horizontal (chão)", TIPO_VERTICAL, "Outro"]
ACOES_SERVICO = list(relatorio.ACOES_PLACA)  # ["Implantação", "Substituição", "Remoção"]

CATEGORIAS = ["Endereçamento", "Sinalização de trânsito"]
ENDERECAMENTO = CATEGORIAS[0]
SERIES_PLACA = {"B": 6, "S": 5, "L": 5}
MODELOS_PLACA = [f"{serie}{n}" for serie, ate in SERIES_PLACA.items() for n in range(1, ate + 1)]
ROTULOS = {"Antes": "antes", "Depois": "depois"}
PULAR = "Pular"
CONFIRMAR = "✅ Confirmar"
DESCARTAR = "❌ Descartar"

BTN_RELATORIO = "📋 Enviar relatório do dia"
SEM_AJUDANTES = "Sem ajudantes"
ENVIAR_RELATORIO = "📤 Enviar relatório"
CANCELAR_RELATORIO = "❌ Cancelar envio"

TZ = ZoneInfo("America/Sao_Paulo")
_CONFIANCA = {"baixa": 0, "media": 1, "alta": 2}
TIPO_PELA_FOTO = {"horizontal": TIPOS[0], "vertical": TIPO_VERTICAL}

_PENDENTES: dict[str, list[tuple[bytes, str]]] = {}


@dataclass
class Reply:
    text: str
    buttons: list[str] | list[list[str]] | None = None
    supervisor_text: str | None = None


# ---------- mensagens ----------
def _pergunta_tipo() -> Reply:
    return Reply("Qual o tipo de sinalização?", TIPOS)


def _pergunta_acao() -> Reply:
    return Reply(
        "Qual serviço foi realizado na placa?\n"
        "• Implantação (antes sem placa -> depois com)\n"
        "• Substituição (antes placa antiga -> depois nova)\n"
        "• Remoção (antes com placa -> depois sem)",
        ACOES_SERVICO,
    )


def _pergunta_categoria() -> Reply:
    return Reply("É placa de endereçamento ou de sinalização de trânsito?", CATEGORIAS)


def _pergunta_modelo() -> Reply:
    linhas = [[m for m in MODELOS_PLACA if m.startswith(serie)] for serie in SERIES_PLACA]
    return Reply("Qual o tipo da placa de endereçamento?", linhas)


def _pergunta_tamanho() -> Reply:
    return Reply("Qual o tamanho em m²? (ex: 12,5)")


def _pergunta_material() -> Reply:
    return Reply("Qual o material utilizado? (ex: tinta acrílica, termoplástico, placa ACM)")


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
    acao = f"Serviço: {d['acao_servico']}\n" if d.get("acao_servico") else ""
    vertical = ""
    if d.get("categoria_vertical"):
        vertical = f"Categoria: {d['categoria_vertical']}"
        if d.get("modelo_placa"):
            vertical += f" | Modelo: {d['modelo_placa']}"
        vertical += "\n"
    padrao = d.get("do_catalogo", [])
    if d.get("tamanho_m2") is None:
        tamanho = "sem metragem (placa de formato padrão)"
    else:
        tamanho = f"{d['tamanho_m2']} m²" + (" (padrão)" if "tamanho" in padrao else "")

    if not d.get("material"):
        material = "sem material (placa de formato padrão)"
    else:
        material = d["material"] + (" (padrão)" if "material" in padrao else "")
    return (
        f"Tipo: {d.get('tipo_sinal')}{' (lido da foto)' if d.get('tipo_automatico') else ''}\n"
        f"{acao}"
        f"{vertical}"
        f"Rua: {d.get('rua') or '-'} | Bairro: {d.get('bairro') or '-'}\n"
        f"Tamanho: {tamanho}\n"
        f"Material: {material}\n"
        f"Fotos: {_descricao_fotos(d.get('fotos_enviadas', {}))}"
    )


def _pergunta_confirma(d: dict) -> list[Reply]:
    return [Reply(f"Confira o registro:\n\n{_resumo(d)}", [CONFIRMAR, DESCARTAR])]


# ---------- dados ----------
def _registro_final(data: dict) -> dict:
    fotos = data.get("fotos_enviadas", {})
    reg = dict(data)
    reg["fotos"] = _descricao_fotos(fotos)
    reg["padrao_catalogo"] = "+".join(data.get("do_catalogo", []))
    reg["link_foto_antes"] = fotos.get("antes", {}).get("link", "")
    reg["link_foto_depois"] = fotos.get("depois", {}).get("link", "")
    reg["tipo_automatico"] = "sim" if data.get("tipo_automatico") else "não"
    return reg


def _mesclar_local(data: dict, loc: dict):
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
    leitura = str(loc.get("orientacao") or "").strip().lower()
    if leitura in TIPO_PELA_FOTO and not data.get("tipo_detectado"):
        data["tipo_detectado"] = TIPO_PELA_FOTO[leitura]
    conf = loc.get("confianca") if loc.get("confianca") in _CONFIANCA else "baixa"
    atual = data.get("confianca_extracao", "baixa")
    data["confianca_extracao"] = max(atual, conf, key=_CONFIANCA.get)


def _descartar_fotos(data: dict):
    fotos = list(data.get("fotos_enviadas", {}).values())
    if data.get("pendente"):
        fotos.append(data["pendente"])
    for foto in fotos:
        try:
            armazenamento.apagar_foto(foto["id"])
        except Exception as e:  # noqa: BLE001
            print("não consegui apagar a foto:", repr(e))


def _ler_localizacao(uid: str, data: dict):
    for conteudo, mime in reversed(_PENDENTES.pop(uid, [])):
        _mesclar_local(data, extractor.extrair_localizacao(conteudo, mime))
        if data.get("rua") or data.get("latitude") is not None:
            break


def _avancar(uid: str, data: dict) -> list[Reply]:
    padrao = catalogo.buscar(data.get("tipo_sinal"), data.get("categoria_vertical"), data.get("modelo_placa"))
    usados = data.setdefault("do_catalogo", [])
    if data.get("tamanho_m2") is None and padrao["tamanho_m2"] is not None:
        data["tamanho_m2"] = padrao["tamanho_m2"]
        usados.append("tamanho")
    if not data.get("material") and padrao["material"]:
        data["material"] = padrao["material"]
        usados.append("material")

    placa = data.get("tipo_sinal") == TIPO_VERTICAL
    if not placa and data.get("tamanho_m2") is None:
        state.save(uid, "TAMANHO", data)
        return [_pergunta_tamanho()]
    if not placa and not data.get("material"):
        state.save(uid, "MATERIAL", data)
        return [_pergunta_material()]
    state.save(uid, "CONFIRMA", data)
    return _pergunta_confirma(data)


def _depois_do_tipo(uid: str, data: dict) -> list[Reply]:
    if data["tipo_sinal"] == TIPO_VERTICAL:
        state.save(uid, "ACAO", data)
        return [_pergunta_acao()]
    return _avancar(uid, data)


def _seguir_para_tipo(uid: str, data: dict) -> list[Reply]:
    tipo = data.get("tipo_detectado")
    if not tipo:
        state.save(uid, "TIPO", data)
        return [_pergunta_tipo()]
    data["tipo_sinal"] = tipo
    data["tipo_automatico"] = True
    return [Reply(f"🔎 Tipo identificado na foto: {tipo}")] + _depois_do_tipo(uid, data)


def _depois_das_fotos(uid: str, data: dict) -> list[Reply]:
    _ler_localizacao(uid, data)
    if not data.get("rua") and data.get("latitude") is None:
        state.save(uid, "LOCAL", data)
        return [Reply("Não consegui ler a localização nas fotos. Digite no formato: Rua X, Bairro Y")]
    local = _texto_local(data.get("rua"), data.get("bairro"), data.get("latitude"), data.get("longitude"))
    return [Reply(f"📍 Local lido: {local}")] + _seguir_para_tipo(uid, data)


# ---------- relatório diário (baseado em registros.csv e relatorios.csv) ----------
def iniciar_relatorio(user_id: int) -> list[Reply]:
    uid = str(user_id)
    s = state.get(uid)
    if s["step"] != "AGUARDANDO_FOTO":
        return [Reply("Você tem um registro em andamento. Conclua ou use /cancelar antes de gerar o relatório.")]

    pendentes = relatorio.listar_pendentes_usuario(uid)
    if not pendentes:
        return [Reply("Você não tem serviços pendentes hoje no CSV para enviar no relatório.")]

    state.save(uid, "REL_VEICULO", {"qtd_servicos": len(pendentes)})
    return [Reply(
        f"Você tem {len(pendentes)} serviço(s) registrado(s) hoje.\n\n"
        "Qual veículo você está utilizando? (ex: Strada ABC-1234)"
    )]


def fechar_relatorios_automaticos() -> list[str]:
    """Chamado às 21h: lê o registros.csv de hoje e fecha relatórios que faltaram."""
    por_usuario = relatorio.listar_pendentes_csv(somente_hoje=True)
    mensagens_supervisor = []

    for uid, servicos in por_usuario.items():
        resumo = relatorio.consolidar(
            servicos,
            veiculo="Não informado (fechamento automático 21h)",
            ajudantes="Não informado (fechamento automático 21h)",
            modo_envio="automatico_21h",
        )
        texto = relatorio.formatar_mensagem(resumo)
        try:
            relatorio.salvar_historico_csv(resumo)
        except Exception as e:  # noqa: BLE001
            print("erro ao salvar CSV do relatório automático:", repr(e))
            continue  # se o CSV estava travado, não marca como enviado
        try:
            relatorio.enviar_email(resumo, texto)
        except Exception as e:  # noqa: BLE001
            print("erro ao enviar e-mail do relatório automático:", repr(e))

        if state.get(uid)["step"].startswith("REL_"):
            state.reset(uid)
        mensagens_supervisor.append(texto)

    return mensagens_supervisor


# ---------- entradas ----------
def cancelar(user_id: int) -> list[Reply]:
    uid = str(user_id)
    _PENDENTES.pop(uid, None)
    _descartar_fotos(state.get(uid)["data"])
    state.reset(uid)
    botoes = [BTN_RELATORIO] if relatorio.listar_pendentes_usuario(uid) else None
    return [Reply("Cancelado. Envie uma nova foto quando quiser.", botoes)]


def receber_foto(user_id: int, nome: str, conteudo: bytes) -> list[Reply]:
    uid = str(user_id)
    s = state.get(uid)
    step, data = s["step"], s["data"]

    if step == "ROTULO":
        return [Reply("Antes de enviar outra foto, me diga: a foto anterior é do antes ou do depois?",
                      list(ROTULOS))]
    if step.startswith("REL_"):
        return [Reply("Você está preenchendo o relatório do dia. Responda à pergunta ou envie /cancelar.")]
    if step not in ("AGUARDANDO_FOTO", "FOTO_EXTRA"):
        return [Reply("Você tem um registro em andamento. Conclua, ou envie /cancelar para recomeçar.")]

    if len(conteudo) > config.MAX_FOTO_MB * 1024 * 1024:
        return [Reply(f"Arquivo muito grande (máximo {config.MAX_FOTO_MB} MB).")]
    mime = seguranca.detectar_mime(conteudo)
    if mime is None:
        return [Reply("Formato não suportado. Envie uma foto em JPG, PNG ou WEBP.")]

    ext = {"image/png": "png", "image/webp": "webp"}.get(mime, "jpg")
    arquivo = f"{datetime.now(TZ):%Y%m%d_%H%M%S}_{uid}_{uuid.uuid4().hex[:6]}.{ext}"
    foto = armazenamento.salvar_foto(conteudo, arquivo, mime)

    if step == "AGUARDANDO_FOTO":
        _PENDENTES[uid] = [(conteudo, mime)]
        data = {"fotos_enviadas": {}, "pendente": foto,
                "usuario": seguranca.limpar_texto(f"{nome} ({uid})")}
        state.save(uid, "ROTULO", data)
        return [_pergunta_rotulo()]

    _PENDENTES.setdefault(uid, []).append((conteudo, mime))
    data["fotos_enviadas"][data.pop("faltando")] = foto
    return _depois_das_fotos(uid, data)


def receber_texto(user_id: int, texto: str) -> list[Reply]:
    uid = str(user_id)
    texto = texto.strip()
    s = state.get(uid)
    step, data = s["step"], s["data"]

    if step == "AGUARDANDO_FOTO":
        if texto == BTN_RELATORIO:
            return iniciar_relatorio(user_id)
        botoes = [BTN_RELATORIO] if relatorio.listar_pendentes_usuario(uid) else None
        return [Reply("Envie a foto do serviço (antes ou depois) com a localização na imagem para começar.", botoes)]

    # --- Etapas do Relatório Diário ---
    if step == "REL_VEICULO":
        veiculo = seguranca.limpar_texto(texto, 80)
        if not veiculo:
            return [Reply("Digite o veículo utilizado hoje (ex: Strada ABC-1234).")]
        data["veiculo"] = veiculo
        state.save(uid, "REL_AJUDANTES", data)
        return [Reply("Quais são os ajudantes de hoje? (digite os nomes ou toque em Sem ajudantes)", [SEM_AJUDANTES])]

    if step == "REL_AJUDANTES":
        ajudantes = seguranca.limpar_texto(texto, 120)
        if not ajudantes:
            return [Reply("Digite os nomes dos ajudantes ou toque em Sem ajudantes.", [SEM_AJUDANTES])]
        data["ajudantes"] = ajudantes
        pendentes = relatorio.listar_pendentes_usuario(uid)
        if not pendentes:
            state.reset(uid)
            return [Reply("Não há mais serviços pendentes para relatar.")]
        previa = relatorio.formatar_mensagem(
            relatorio.consolidar(pendentes, data["veiculo"], data["ajudantes"], modo_envio="manual")
        )
        state.save(uid, "REL_CONFIRMA", data)
        return [Reply(f"Confira o relatório antes de enviar ao supervisor:\n\n{previa}",
                      [ENVIAR_RELATORIO, CANCELAR_RELATORIO])]

    if step == "REL_CONFIRMA":
        if texto == CANCELAR_RELATORIO:
            state.reset(uid)
            return [Reply("Envio do relatório cancelado. Seus registros do dia continuam salvos.", [BTN_RELATORIO])]
        if texto != ENVIAR_RELATORIO:
            return [Reply("Toque em Enviar relatório ou Cancelar envio.", [ENVIAR_RELATORIO, CANCELAR_RELATORIO])]

        pendentes = relatorio.listar_pendentes_usuario(uid)
        if not pendentes:
            state.reset(uid)
            return [Reply("Nenhum serviço pendente encontrado.")]

        resumo = relatorio.consolidar(pendentes, data["veiculo"], data["ajudantes"], modo_envio="manual")
        msg_final = relatorio.formatar_mensagem(resumo)
        try:
            relatorio.salvar_historico_csv(resumo)
        except PermissionError:
            return [Reply(
                "Não consegui gravar em relatorios.csv (se ele estiver aberto no Excel, feche-o e tente novamente).",
                [ENVIAR_RELATORIO, CANCELAR_RELATORIO],
            )]
        aviso_email = ""
        if relatorio.email_configurado():
            try:
                relatorio.enviar_email(resumo, msg_final)
                aviso_email = " e por e-mail"
            except Exception as e:  # noqa: BLE001
                print("falha ao enviar e-mail do relatório:", repr(e))
                aviso_email = " (falha no envio por e-mail, verifique o console)"

        state.reset(uid)
        return [Reply(
            f"✅ Relatório enviado com sucesso{aviso_email}!\nBom descanso!",
            supervisor_text=msg_final,
        )]

    # --- Etapas do Cadastro de Placa/Serviço ---
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
        return _seguir_para_tipo(uid, data)

    if step == "TIPO":
        if texto not in TIPOS:
            return [_pergunta_tipo()]
        data["tipo_sinal"] = texto
        return _depois_do_tipo(uid, data)

    if step == "ACAO":
        if texto not in ACOES_SERVICO:
            return [_pergunta_acao()]
        data["acao_servico"] = texto
        state.save(uid, "CATEGORIA", data)
        return [_pergunta_categoria()]

    if step == "CATEGORIA":
        if texto not in CATEGORIAS:
            return [_pergunta_categoria()]
        data["categoria_vertical"] = texto
        if texto == ENDERECAMENTO:
            state.save(uid, "MODELO", data)
            return [_pergunta_modelo()]
        return _avancar(uid, data)

    if step == "MODELO":
        modelo = texto.upper().replace(" ", "")
        if modelo not in MODELOS_PLACA:
            return [_pergunta_modelo()]
        data["modelo_placa"] = modelo
        return _avancar(uid, data)

    if step == "TAMANHO":
        try:
            valor = float(texto.replace(",", "."))
        except ValueError:
            valor = None
        if valor is None or not math.isfinite(valor) or not (0 < valor <= 100000):
            return [Reply("Não entendi. Envie só o número em m², ex: 12,5")]
        data["tamanho_m2"] = round(valor, 2)
        return _avancar(uid, data)

    if step == "MATERIAL":
        material = seguranca.limpar_texto(texto, 80)
        if not material:
            return [Reply("Não entendi. Digite o material utilizado.")]
        data["material"] = material
        return _avancar(uid, data)

    if step == "CONFIRMA":
        if texto == CONFIRMAR:
            data["registrado_em"] = datetime.now(TZ).strftime("%d/%m/%Y %H:%M:%S")
            try:
                armazenamento.adicionar_registro(_registro_final(data))
            except PermissionError:
                return [Reply(
                    "Não consegui gravar no arquivo. Se o CSV estiver aberto no Excel, feche-o "
                    "e toque em Confirmar de novo.", [CONFIRMAR, DESCARTAR])]
            state.reset(uid)
            qtd = len(relatorio.listar_pendentes_usuario(uid))
            return [Reply(
                f"✅ Registro salvo! ({qtd} serviço(s) acumulado(s) para o relatório de hoje).\n"
                "Envie a próxima foto ou feche o relatório ao encerrar o turno.",
                [BTN_RELATORIO],
            )]
        if texto == DESCARTAR:
            return cancelar(user_id)
        return _pergunta_confirma(data)

    state.reset(uid)
    return [Reply("Algo saiu do fluxo, vamos recomeçar. Envie a foto do serviço.")]
