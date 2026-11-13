"""Bot do Telegram com long polling. Rode com: python -m app.bot"""
import asyncio

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    Application, CommandHandler, ContextTypes, MessageHandler, filters,
)

from . import config, flow, state

MIMES_OK = {"image/jpeg", "image/png", "image/webp", "image/gif"}
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
    await _enviar(update.message, flow.cancelar(update.effective_user.id))


async def on_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user = update.effective_user
    try:
        if msg.photo:  # foto comum: o Telegram comprime; pegamos a maior resolução
            tg_file, mime = await msg.photo[-1].get_file(), "image/jpeg"
        else:  # enviada como arquivo: qualidade original
            tg_file, mime = await msg.document.get_file(), msg.document.mime_type or "image/jpeg"

        if mime not in MIMES_OK:
            return await msg.reply_text("Formato não suportado. Envie JPG, PNG ou WEBP.")

        await msg.reply_text("Foto recebida, lendo a localização...")
        conteudo = bytes(await tg_file.download_as_bytearray())
        # funções do fluxo fazem I/O bloqueante (Anthropic, Drive): rodam em thread
        replies = await asyncio.to_thread(flow.receber_foto, user.id, user.full_name, conteudo, mime)
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


def main():
    state.init()
    permitido = filters.User(user_id=list(config.ALLOWED_USER_IDS)) if config.ALLOWED_USER_IDS else filters.ALL

    app = Application.builder().token(config.TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("id", cmd_id))
    app.add_handler(CommandHandler("start", cmd_start, filters=permitido))
    app.add_handler(CommandHandler("cancelar", cmd_cancelar, filters=permitido))
    app.add_handler(MessageHandler((filters.PHOTO | filters.Document.IMAGE) & permitido, on_foto))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & permitido, on_texto))

    print("Bot rodando (Ctrl+C para parar)...")
    app.run_polling()


if __name__ == "__main__":
    main()
