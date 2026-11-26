"""Bot do Telegram com long polling. Rode com: python -m app.bot"""
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application, CommandHandler, ContextTypes, MessageHandler, filters,
)

from . import config, flow, state

ERRO = "Deu um erro aqui. Envie a foto novamente ou use /cancelar."
TZ = ZoneInfo("America/Sao_Paulo")
_tarefa_agendador: asyncio.Task | None = None


def _linhas_teclado(botoes: list) -> list[list[str]]:
    """Lista de textos vira um botão por linha; lista de listas já são as linhas do teclado."""
    return botoes if isinstance(botoes[0], list) else [[b] for b in botoes]


async def _notificar_supervisores(bot, texto: str):
    for sup_id in config.SUPERVISOR_USER_IDS:
        try:
            await bot.send_message(chat_id=sup_id, text=texto)
        except Exception as e:  # noqa: BLE001
            print(f"erro ao enviar relatório para supervisor {sup_id}:", repr(e))


async def _enviar(message, bot, replies: list[flow.Reply]):
    for r in replies:
        if r.buttons:
            markup = ReplyKeyboardMarkup(_linhas_teclado(r.buttons), one_time_keyboard=True, resize_keyboard=True)
        else:
            markup = ReplyKeyboardRemove()
        await message.reply_text(r.text, reply_markup=markup)
        if r.supervisor_text:
            await _notificar_supervisores(bot, r.supervisor_text)


async def _loop_relatorio_diario(app: Application):
    """Dispara às 21:00 (ou horário definido em RELATORIO_HORARIO) para fechar relatórios esquecidos."""
    if not config.RELATORIO_HORARIO:
        return
    hora, minuto = (int(p) for p in config.RELATORIO_HORARIO.split(":"))
    while True:
        agora = datetime.now(TZ)
        alvo = agora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
        if alvo <= agora:
            alvo += timedelta(days=1)
        await asyncio.sleep((alvo - agora).total_seconds())
        try:
            mensagens = await asyncio.to_thread(flow.fechar_relatorios_automaticos)
            for msg in mensagens:
                await _notificar_supervisores(app.bot, msg)
        except Exception as e:  # noqa: BLE001
            print("erro no fechamento automático de relatórios:", repr(e))


async def _post_init(app: Application):
    global _tarefa_agendador
    _tarefa_agendador = asyncio.create_task(_loop_relatorio_diario(app))


async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sem filtro de autorização: serve para descobrir seu ID e colocá-lo no .env."""
    await update.message.reply_text(f"Seu ID: {update.effective_user.id}")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Olá! Envie a foto do serviço (com a localização na imagem) para registrar.\n"
        "Ao fim do expediente, use /relatorio para enviar o resumo ao supervisor.\n"
        "Dica: envie como arquivo para não perder qualidade. Use /cancelar para desistir."
    )


async def cmd_relatorio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        replies = await asyncio.to_thread(flow.iniciar_relatorio, update.effective_user.id)
        await _enviar(update.message, context.bot, replies)
    except Exception as e:  # noqa: BLE001
        print("erro ao iniciar relatório:", repr(e))
        await update.message.reply_text(ERRO)


async def cmd_cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        replies = await asyncio.to_thread(flow.cancelar, update.effective_user.id)
        await _enviar(update.message, context.bot, replies)
    except Exception as e:  # noqa: BLE001
        print("erro ao cancelar:", repr(e))
        await update.message.reply_text(ERRO)


async def on_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user = update.effective_user
    try:
        tg_file = await (msg.photo[-1] if msg.photo else msg.document).get_file()
        if tg_file.file_size and tg_file.file_size > config.MAX_FOTO_MB * 1024 * 1024:
            return await msg.reply_text(f"Arquivo muito grande (máximo {config.MAX_FOTO_MB} MB).")

        await msg.reply_text("Foto recebida ✅")
        conteudo = bytes(await tg_file.download_as_bytearray())
        await msg.chat.send_action(ChatAction.TYPING)
        replies = await asyncio.to_thread(flow.receber_foto, user.id, user.full_name, conteudo)
        await _enviar(msg, context.bot, replies)
    except Exception as e:  # noqa: BLE001
        print("erro ao receber foto:", repr(e))
        await msg.reply_text(ERRO)


async def on_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    try:
        await msg.chat.send_action(ChatAction.TYPING)
        replies = await asyncio.to_thread(flow.receber_texto, update.effective_user.id, msg.text)
        await _enviar(msg, context.bot, replies)
    except Exception as e:  # noqa: BLE001
        print("erro no fluxo:", repr(e))
        await msg.reply_text(ERRO)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    print("erro não tratado:", repr(context.error))


def main():
    state.init()
    permitido = filters.User(user_id=list(config.ALLOWED_USER_IDS)) if config.ALLOWED_USER_IDS else filters.ALL

    app = Application.builder().token(config.TELEGRAM_TOKEN).post_init(_post_init).build()
    app.add_handler(CommandHandler("id", cmd_id))
    app.add_handler(CommandHandler("start", cmd_start, filters=permitido))
    app.add_handler(CommandHandler("relatorio", cmd_relatorio, filters=permitido))
    app.add_handler(CommandHandler("cancelar", cmd_cancelar, filters=permitido))
    app.add_handler(MessageHandler((filters.PHOTO | filters.Document.IMAGE) & permitido, on_foto))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & permitido, on_texto))
    app.add_error_handler(on_error)

    if not config.ALLOWED_USER_IDS:
        print("AVISO: ALLOWED_USER_IDS vazio, qualquer pessoa pode usar este bot.")
    destino = f"pasta '{config.DADOS_DIR}'" if config.ARMAZENAMENTO == "local" else "Drive e Google Sheets"
    print(f"Armazenamento: {config.ARMAZENAMENTO} ({destino})")
    if config.RELATORIO_HORARIO:
        print(f"Fechamento automático de relatórios ativo às {config.RELATORIO_HORARIO}")
    print("Bot rodando (Ctrl+C para parar)...")
    app.run_polling()


if __name__ == "__main__":
    main()
