# Bot Telegram -> Google Drive + Planilha (sinalização viária)

Fluxo: o campo manda a foto (com carimbo de localização) -> o bot lê o local,
salva a foto no Drive, pergunta tipo / m² / material -> grava uma linha na planilha.

## Setup

1. `python -m venv .venv` e ative; depois `pip install -r requirements.txt`
2. `cp .env.example .env` (no Windows: `copy .env.example .env`) e preencha.
3. **Telegram**: no app, fale com @BotFather -> `/newbot` -> escolha nome e username
   (terminando em `bot`) -> copie o token para `TELEGRAM_TOKEN`.
4. **Google**: ative Drive API e Sheets API no Cloud Console, crie credencial OAuth
   "Desktop app", baixe como `credentials.json` e rode `python -m app.google_auth`.
5. Crie a pasta no Drive e a planilha (aba `Registros`); copie os IDs da URL para o `.env`.
6. Rode `python -m app.bot`, abra seu bot no Telegram e mande `/id`.
   Coloque o número em `ALLOWED_USER_IDS` e reinicie.

Não precisa de ngrok nem URL pública: o bot usa long polling.

## Estrutura

- `app/bot.py`: handlers do Telegram (foto, texto, comandos)
- `app/flow.py`: conversa (máquina de estados, independente do canal)
- `app/extractor.py`: lê a localização da imagem com modelo de visão
- `app/drive.py` / `app/sheets.py`: integrações Google
- `app/state.py`: SQLite com o estado de cada usuário

## Ideias para evoluir

- Aceitar a localização nativa do Telegram (o usuário compartilha o pin) como alternativa ao carimbo
- Ler o EXIF quando a foto vier como arquivo (o Telegram só preserva EXIF nesse caso)
- Docker + VPS pequena (polling não exige HTTPS)
- Postgres no lugar de SQLite, comando /desfazer, planilha de revisão antes do faturamento
- Quando liberarem o Helius: trocar `sheets.adicionar_registro` por um POST na API
