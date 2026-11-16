"""Bot do Telegram com long polling. Rode com: python -m app.bot"""
import asyncio

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    Application, CommandHandler, ContextTypes, MessageHandler, filters,
)

from . import config, flow, state

ERRO = "Deu um erro aqui. Envie a foto novamente ou use /cancelar."


async def _enviar(message, replies: list[flow.Reply]):
    for r in replies:
        if r.buttons:
            markup = ReplyKeyboardMarkup([[b] for b in r.buttons], one_time_keyboard=True, resize_keyboard=True)
        else:
            markup = ReplyKeyboardRemove()
        await message.reply_text(r.text, reply_markup=markup)


async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sem filtro de autorização: serve para descobrir seu ID e colocá-lo no .env."""
    await update.message.reply_text(f"Seu ID: {update.effective_user.id}")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Olá! Envie a foto do serviço (com a localização na imagem) para registrar.\n"
        "Dica: envie como arquivo para não perder qualidade. Use /cancelar para desistir."
    )


async def cmd_cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        replies = await asyncio.to_thread(flow.cancelar, update.effective_user.id)
        await _enviar(update.message, replies)
    except Exception as e:  # noqa: BLE001
        print("erro ao cancelar:", repr(e))
        await update.message.reply_text(ERRO)


async def on_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user = update.effective_user
    try:
        # foto comum: o Telegram comprime (pegamos a maior resolução); arquivo: qualidade original
        tg_file = await (msg.photo[-1] if msg.photo else msg.document).get_file()
        if tg_file.file_size and tg_file.file_size > config.MAX_FOTO_MB * 1024 * 1024:
            return await msg.reply_text(f"Arquivo muito grande (máximo {config.MAX_FOTO_MB} MB).")

        await msg.reply_text("Foto recebida, lendo a localização...")
        conteudo = bytes(await tg_file.download_as_bytearray())
        # as funções do fluxo fazem I/O bloqueante (Gemini, Drive): rodam em thread
        replies = await asyncio.to_thread(flow.receber_foto, user.id, user.full_name, conteudo)
        await _enviar(msg, replies)
    except Exception as e:  # noqa: BLE001
        print("erro ao receber foto:", repr(e))
        await msg.reply_text(ERRO)


async def on_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    try:
        replies = await asyncio.to_thread(flow.receber_texto, update.effective_user.id, msg.text)
        await _enviar(msg, replies)
    except Exception as e:  # noqa: BLE001
        print("erro no fluxo:", repr(e))
        await msg.reply_text(ERRO)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    print("erro não tratado:", repr(context.error))


def main():
    state.init()
    permitido = filters.User(user_id=list(config.ALLOWED_USER_IDS)) if config.ALLOWED_USER_IDS else filters.ALL

    app = Application.builder().token(config.TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("id", cmd_id))
    app.add_handler(CommandHandler("start", cmd_start, filters=permitido))
    app.add_handler(CommandHandler("cancelar", cmd_cancelar, filters=permitido))
    app.add_handler(MessageHandler((filters.PHOTO | filters.Document.IMAGE) & permitido, on_foto))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & permitido, on_texto))
    app.add_error_handler(on_error)

    if not config.ALLOWED_USER_IDS:
        print("AVISO: ALLOWED_USER_IDS vazio, qualquer pessoa pode usar este bot.")
    destino = f"pasta '{config.DADOS_DIR}'" if config.ARMAZENAMENTO == "local" else "Drive e Google Sheets"
    print(f"Armazenamento: {config.ARMAZENAMENTO} ({destino})")
    print("Bot rodando (Ctrl+C para parar)...")
    app.run_polling()


if __name__ == "__main__":
    main()
