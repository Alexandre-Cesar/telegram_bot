"""Lê dados/registros.csv, consolida o relatório do dia, grava dados/relatorios.csv e envia."""
import csv
import smtplib
import threading
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config
from .colunas import COLUNAS_RELATORIO
from .seguranca import neutralizar_formula

TZ = ZoneInfo("America/Sao_Paulo")
_lock = threading.Lock()

ACOES_PLACA = ("Implantação", "Substituição", "Remoção")


def _caminho_registros() -> Path:
    return Path(config.DADOS_DIR) / "registros.csv"


def _caminho_relatorios() -> Path:
    pasta = Path(config.DADOS_DIR)
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta / "relatorios.csv"


def _parse_data_hora(texto: str) -> datetime | None:
    try:
        return datetime.strptime(texto.strip(), "%d/%m/%Y %H:%M:%S")
    except (ValueError, AttributeError):
        return None


def _parse_m2(valor: str) -> float | None:
    if not valor or not valor.strip():
        return None
    try:
        return float(valor.strip().replace(config.CSV_DECIMAL, ".").replace(",", "."))
    except ValueError:
        return None


def _ultimos_fechamentos_por_uid() -> dict[str, datetime]:
    """Lê relatorios.csv e descobre até qual horário cada usuário (uid) já enviou relatório."""
    caminho = _caminho_relatorios()
    if not caminho.exists() or caminho.stat().st_size == 0:
        return {}

    ultimos: dict[str, datetime] = {}
    with open(caminho, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f, delimiter=config.CSV_DELIMITADOR):
            usuario = row.get("usuario", "")
            # formato salvo pelo bot: "Nome Sobrenome (12345678)"
            uid = usuario.rsplit("(", 1)[-1].rstrip(")") if "(" in usuario else usuario
            dt = _parse_data_hora(row.get("ultimo_registro_incluido", "")) or _parse_data_hora(row.get("enviado_em", ""))
            if uid and dt and (uid not in ultimos or dt > ultimos[uid]):
                ultimos[uid] = dt
    return ultimos


def listar_pendentes_csv(uid: str | None = None, somente_hoje: bool = True) -> dict[str, list[dict]]:
    """Lê registros.csv e devolve {uid: [linhas]} dos serviços que ainda não entraram em relatório."""
    caminho = _caminho_registros()
    if not caminho.exists() or caminho.stat().st_size == 0:
        return {}

    hoje_str = datetime.now(TZ).strftime("%d/%m/%Y")
    ultimos = _ultimos_fechamentos_por_uid()
    agrupado: dict[str, list[dict]] = {}

    with open(caminho, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f, delimiter=config.CSV_DELIMITADOR):
            reg_em = row.get("registrado_em", "").strip()
            if somente_hoje and not reg_em.startswith(hoje_str):
                continue

            dt_reg = _parse_data_hora(reg_em)
            if not dt_reg:
                continue

            usuario = row.get("usuario", "")
            row_uid = usuario.rsplit("(", 1)[-1].rstrip(")") if "(" in usuario else usuario
            if uid and row_uid != str(uid):
                continue

            # Pula registros que já entraram em um relatório anterior desse encarregado
            if row_uid in ultimos and dt_reg <= ultimos[row_uid]:
                continue

            item = dict(row)
            item["tamanho_m2_num"] = _parse_m2(row.get("tamanho_m2", ""))
            agrupado.setdefault(row_uid, []).append(item)

    return agrupado


def listar_pendentes_usuario(uid: str) -> list[dict]:
    return listar_pendentes_csv(uid=str(uid), somente_hoje=True).get(str(uid), [])


def consolidar(servicos: list[dict], veiculo: str, ajudantes: str, modo_envio: str = "manual") -> dict:
    """Calcula os totais a partir das linhas lidas do registros.csv."""
    implantacoes = sum(1 for s in servicos if s.get("acao_servico") == "Implantação")
    substituicoes = sum(1 for s in servicos if s.get("acao_servico") == "Substituição")
    remocoes = sum(1 for s in servicos if s.get("acao_servico") == "Remoção")
    outros = len(servicos) - (implantacoes + substituicoes + remocoes)
    total_m2 = round(sum(s["tamanho_m2_num"] for s in servicos if s.get("tamanho_m2_num") is not None), 2)

    locais = []
    for s in servicos:
        rua = (s.get("rua") or "").lstrip("'")
        bairro = (s.get("bairro") or "").lstrip("'")
        loc = f"{rua} ({bairro})" if rua and bairro else (rua or bairro)
        if loc and loc not in locais:
            locais.append(loc)

    agora_str = datetime.now(TZ).strftime("%d/%m/%Y %H:%M:%S")
    ultimo_reg = servicos[-1].get("registrado_em", agora_str) if servicos else agora_str
    data_ref = ultimo_reg.split(" ")[0] if " " in ultimo_reg else datetime.now(TZ).strftime("%d/%m/%Y")
    usuario = servicos[0].get("usuario", "-") if servicos else "-"

    return {
        "enviado_em": agora_str,
        "data_referencia": data_ref,
        "modo_envio": modo_envio,
        "usuario": usuario,
        "veiculo": veiculo,
        "ajudantes": ajudantes,
        "total_servicos": len(servicos),
        "implantacoes": implantacoes,
        "substituicoes": substituicoes,
        "remocoes": remocoes,
        "outros_servicos": outros,
        "total_m2": total_m2,
        "ruas_atendidas": " | ".join(locais) if locais else "-",
        "ultimo_registro_incluido": ultimo_reg,
        "lista_locais": locais,
    }


def formatar_mensagem(resumo: dict) -> str:
    cabecalho = "📋 RELATÓRIO DIÁRIO DE SINALIZAÇÃO"
    if resumo["modo_envio"] == "automatico_21h":
        cabecalho += " (ENVIO AUTOMÁTICO)"

    m2_str = f"{resumo['total_m2']} m²".replace(".", ",")
    ruas = "\n".join(f"  • {loc}" for loc in resumo["lista_locais"][:15]) or "  • Não informado"
    if len(resumo["lista_locais"]) > 15:
        ruas += f"\n  • ... (+{len(resumo['lista_locais']) - 15} locais)"

    linhas = [
        cabecalho,
        f"📅 Data: {resumo['data_referencia']}",
        f"👷 Encarregado: {resumo['usuario']}",
        f"🚚 Veículo: {resumo['veiculo']}",
        f"🤝 Ajudantes: {resumo['ajudantes']}",
        "",
        f"📊 RESUMO DO DIA ({resumo['total_servicos']} serviço(s)):",
        f"  🟢 Implantações: {resumo['implantacoes']}",
        f"  🔄 Substituições: {resumo['substituicoes']}",
        f"  🔴 Remoções: {resumo['remocoes']}",
    ]
    if resumo["outros_servicos"] > 0:
        linhas.append(f"  🛣️ Sinalização horizontal / outros: {resumo['outros_servicos']}")
    if resumo["total_m2"] > 0:
        linhas.append(f"  📐 Metragem total registrada: {m2_str}")
    linhas.extend(["", "📍 Locais atendidos:", ruas])
    return "\n".join(linhas)


def salvar_historico_csv(resumo: dict):
    """Grava o relatório em dados/relatorios.csv (mesmo padrão ';' e ',' para o Excel)."""
    caminho = _caminho_relatorios()

    def _fmt(v):
        if v is None:
            return ""
        if isinstance(v, float):
            return str(v).replace(".", config.CSV_DECIMAL)
        if isinstance(v, str):
            return neutralizar_formula(v)
        return str(v)

    linha = [_fmt(resumo.get(col)) for col in COLUNAS_RELATORIO]
    with _lock:
        novo = not caminho.exists() or caminho.stat().st_size == 0
        with open(caminho, "w" if novo else "a", newline="",
                  encoding="utf-8-sig" if novo else "utf-8") as f:
            escritor = csv.writer(f, delimiter=config.CSV_DELIMITADOR)
            if novo:
                escritor.writerow(COLUNAS_RELATORIO)
            escritor.writerow(linha)


def email_configurado() -> bool:
    return bool(config.SMTP_HOST and config.SMTP_USER and config.SMTP_PASS and config.RELATORIO_EMAIL_DESTINO)


def enviar_email(resumo: dict, texto: str):
    if not email_configurado():
        return
    msg = EmailMessage()
    msg["Subject"] = f"Relatório Sinalização - {resumo['data_referencia']} - {resumo['usuario']}"
    msg["From"] = config.SMTP_USER
    msg["To"] = ", ".join(config.RELATORIO_EMAIL_DESTINO)
    msg.set_content(texto)

    if config.SMTP_PORT == 465:
        with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as srv:
            srv.login(config.SMTP_USER, config.SMTP_PASS)
            srv.send_message(msg)
    else:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as srv:
            srv.starttls()
            srv.login(config.SMTP_USER, config.SMTP_PASS)
            srv.send_message(msg)