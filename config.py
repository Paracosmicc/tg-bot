import os
from dotenv import load_dotenv

load_dotenv()


def _clean_list(*values):
    return [v for v in values if v]


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

GROK_API_KEYS = _clean_list(
    os.getenv("GROK_API_KEY_1"),
    os.getenv("GROK_API_KEY_2"),
    os.getenv("GROK_API_KEY_3"),
    os.getenv("GROK_API_KEY_4"),
    os.getenv("GROK_API_KEY_5"),
)

GROK_MODEL = os.getenv("GROK_MODEL", "openai/gpt-oss-120b")




GROK_BASE_URL = os.getenv("GROK_BASE_URL", "https://api.x.ai/v1")

MONGODB_URI = os.getenv("MONGODB_URI", os.getenv("MONGO_URI", "mongodb://localhost:27017/vaidehi"))
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "vaidehi")


BOT_NAME = os.getenv("BOT_NAME", "Vaidehi")
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "12"))

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set. Copy .env.example to .env and fill it in.")

if not GROK_API_KEYS:
    raise RuntimeError("At least one GROK_API_KEY_n must be set in .env")
