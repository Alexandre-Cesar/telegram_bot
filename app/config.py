import os

from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
ALLOWED_USER_IDS = {int(x) for x in os.getenv("ALLOWED_USER_IDS", "").split(",") if x.strip()}

# Supervisores que recebem o relatório no Telegram (separados por vírgula)
SUPERVISOR_USER_IDS = {int(x) for x in os.getenv("SUPERVISOR_USER_IDS", "").split(",") if x.strip()}

# Horário do fechamento automático diário (formato HH:MM, vazio desativa)
RELATORIO_HORARIO = os.getenv("RELATORIO_HORARIO", "21:00").strip()

# E-mail opcional para enviar o relatório ao supervisor (via SMTP padrão do Python)
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASS = os.getenv("SMTP_PASS", "").strip()
RELATORIO_EMAIL_DESTINO = [
    e.strip() for e in os.getenv("RELATORIO_EMAIL_DESTINO", "").split(",") if e.strip()
]

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

# Catálogo de placas padrão (tamanho e material pré-definidos); editável com o bot rodando
CATALOGO_PATH = os.getenv("CATALOGO_PATH", "catalogo_placas.csv")
CATALOGO_DELIMITADOR = os.getenv("CATALOGO_DELIMITADOR", ";")

DB_PATH = os.getenv("DB_PATH", "bot.db")
MAX_FOTO_MB = int(os.getenv("MAX_FOTO_MB", "10"))
