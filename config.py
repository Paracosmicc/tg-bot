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

REDIS_URI = os.getenv("REDIS_URI", "")
REDIS_CACHE_TTL = int(os.getenv("REDIS_CACHE_TTL", "604800"))  # 7 days in seconds


BOT_NAME = os.getenv("BOT_NAME", "Vaidehi")
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "12"))
DM_MESSAGE_LIMIT = int(os.getenv("DM_MESSAGE_LIMIT", "25"))
DM_WINDOW_SECONDS = int(os.getenv("DM_WINDOW_SECONDS", "28800"))  # 8 hours in seconds (8 * 3600)

# Sticker reply settings
STICKER_REPLY_PROBABILITY = float(os.getenv("STICKER_REPLY_PROBABILITY", "0.05"))
_default_packs = "LuKucing,WraptBlayJeux_by_fStikBot,pack_1b50d_by_TgEmojis_bot"
_raw_packs = os.getenv("STICKER_PACKS", _default_packs).split(",")
STICKER_PACKS = []
for p in _raw_packs:
    cleaned_p = p.strip()
    if "addstickers/" in cleaned_p:
        cleaned_p = cleaned_p.split("addstickers/")[-1].strip("/")
    if cleaned_p:
        STICKER_PACKS.append(cleaned_p)
STICKER_FILE_IDS = [s.strip() for s in os.getenv("STICKERS", "").split(",") if s.strip()]



# Random flirty behavior settings (1% random chime chance in groups, periodic drop-in every 2 hours)
RANDOM_CHIME_PROBABILITY = float(os.getenv("RANDOM_CHIME_PROBABILITY", "0.02"))
RANDOM_JOB_INTERVAL_MINUTES = int(os.getenv("RANDOM_JOB_INTERVAL_MINUTES", "120"))

# Admin & Owner Settings
ADMIN_USERNAMES = [u.strip().lstrip("@").lower() for u in os.getenv("ADMIN_USERNAMES", "Holaa_amigoooo").split(",") if u.strip()]
_admin_ids_raw = os.getenv("ADMIN_USER_IDS", "")
ADMIN_USER_IDS = [int(i.strip()) for i in _admin_ids_raw.split(",") if i.strip().isdigit()]


def is_admin(user) -> bool:
    """Check if a Telegram user is authorized as bot admin/owner."""
    if not user:
        return False
    if user.id in ADMIN_USER_IDS:
        return True
    if user.username and user.username.lstrip("@").lower() in ADMIN_USERNAMES:
        return True
    return False


# Bot Uptime Tracking
from datetime import datetime, timezone
BOT_START_TIME = datetime.now(timezone.utc)


def get_uptime_str() -> str:
    """Return formatted uptime string (e.g. '2d 5h 12m 30s')."""
    now = datetime.now(timezone.utc)
    delta = now - BOT_START_TIME
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0 or days > 0:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set. Copy .env.example to .env and fill it in.")

if not GROK_API_KEYS:
    raise RuntimeError("At least one GROK_API_KEY_n must be set in .env")

