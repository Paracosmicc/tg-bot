import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")


def _clean_list(*values):
    cleaned = []
    for v in values:
        if v and isinstance(v, str) and v.strip():
            cleaned.append(v.strip())
    return list(dict.fromkeys(cleaned))  # Deduplicate preserving order


_raw_keys = []
grok_env_keys = os.getenv("GROK_API_KEYS")
if grok_env_keys:
    _raw_keys.extend(grok_env_keys.split(","))

for i in range(1, 9):
    val = os.getenv(f"GROK_API_KEY_{i}")
    if val:
        _raw_keys.append(val)

GROK_API_KEYS = _clean_list(*_raw_keys)

GROK_MODEL = os.getenv("GROK_MODEL", "openai/gpt-oss-120b")




GROK_BASE_URL = os.getenv("GROK_BASE_URL", "https://api.x.ai/v1")

MONGODB_URI = os.getenv("MONGODB_URI", os.getenv("MONGO_URI", "mongodb://localhost:27017/vaidehi"))
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "vaidehi")


BOT_NAME = os.getenv("BOT_NAME", "Vaidehi")
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "12"))

# Random flirty behavior settings
RANDOM_CHIME_PROBABILITY = float(os.getenv("RANDOM_CHIME_PROBABILITY", "0.05"))
RANDOM_JOB_INTERVAL_MINUTES = int(os.getenv("RANDOM_JOB_INTERVAL_MINUTES", "120"))

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set. Copy .env.example to .env and fill it in.")

if not GROK_API_KEYS:
    raise RuntimeError("At least one GROK_API_KEY_n must be set in .env")
