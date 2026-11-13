import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
ALLOWED_USER_IDS = {int(x) for x in os.getenv("ALLOWED_USER_IDS", "").split(",") if x.strip()}

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

DRIVE_FOLDER_NAME = os.getenv("DRIVE_FOLDER_NAME", "Sinalizacao - Fotos")
SHEET_ID = os.environ["SHEET_ID"]
SHEET_TAB = os.getenv("SHEET_TAB", "Registros")

DB_PATH = os.getenv("DB_PATH", "bot.db")
