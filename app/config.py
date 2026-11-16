import os

from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
ALLOWED_USER_IDS = {int(x) for x in os.getenv("ALLOWED_USER_IDS", "").split(",") if x.strip()}

# Sem chave, o bot não lê a foto e pede o endereço digitado (útil para testar o resto)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

# 'local' = fotos e CSV neste PC | 'google' = Drive e planilha
ARMAZENAMENTO = os.getenv("ARMAZENAMENTO", "local").strip().lower()
if ARMAZENAMENTO not in {"local", "google"}:
    raise ValueError("ARMAZENAMENTO deve ser 'local' ou 'google'")

# Modo local
DADOS_DIR = os.getenv("DADOS_DIR", "dados")
CSV_DELIMITADOR = os.getenv("CSV_DELIMITADOR", ";")  # ';' abre direto no Excel em português
CSV_DECIMAL = os.getenv("CSV_DECIMAL", ",")

# Modo google
DRIVE_FOLDER_NAME = os.getenv("DRIVE_FOLDER_NAME", "Sinalizacao - Fotos")
SHEET_ID = os.getenv("SHEET_ID", "")
SHEET_TAB = os.getenv("SHEET_TAB", "Registros")
if ARMAZENAMENTO == "google" and not SHEET_ID:
    raise ValueError("Defina SHEET_ID no .env para usar ARMAZENAMENTO=google")

DB_PATH = os.getenv("DB_PATH", "bot.db")
MAX_FOTO_MB = int(os.getenv("MAX_FOTO_MB", "10"))
